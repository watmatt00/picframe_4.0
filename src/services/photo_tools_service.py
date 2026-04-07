"""
PicFrame 4.0 - Photo Tools Service.

Scan-then-apply operations for photo library maintenance:
- Filename cleaning: strip Google Photos ID tokens and numbered-dup suffixes
- Duplicate detection: hash-based exact deduplication
- Video management: list and remove video files Pi3D cannot display

All mutating operations are cloud-first (rclone before local) to prevent
the next sync cycle from restoring deleted/renamed files.

Design note: This service contains only business logic.  Both the JWT API
routes (mobile-ready) and the LAN dashboard routes call into it directly,
so adding these features to the iOS app later requires zero refactoring.
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from src.services.source_manager import source_manager
from src.utils.rclone import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    rclone_deletefile_raw,
    rclone_movefile_raw,
)

logger = logging.getLogger(__name__)

THUMB_CACHE_DIR = Path("/tmp/pfthumb")

# Regex patterns for filename issues
_RE_GOOGLE_ID = re.compile(r"\s*\{[^}]+\}")      # " {AByz57...}"
_RE_NUMBERED_SUFFIX = re.compile(r"\s*\(\d+\)$")  # " (0)", " (54)"


# ---------------------------------------------------------------------------
# Shared models
# ---------------------------------------------------------------------------

class FileInfo(BaseModel):
    filename: str
    size_bytes: int
    modified_epoch: int


class BatchResult(BaseModel):
    succeeded: list[str] = []
    failed: list[dict] = []    # [{"filename": ..., "error": ...}]
    total: int = 0


# ---------------------------------------------------------------------------
# Filename cleaning
# ---------------------------------------------------------------------------

class FilenameFix(BaseModel):
    original: str
    proposed: str
    reasons: list[str]  # e.g. ["google_id", "numbered_suffix", "ext_case"]


class FilenameScanResult(BaseModel):
    source_id: str
    fixes: list[FilenameFix]
    total_files_scanned: int


def _clean_stem(stem: str) -> tuple[str, list[str]]:
    """Strip known junk patterns from a filename stem.

    Returns (cleaned_stem, list_of_reason_codes).
    """
    reasons: list[str] = []
    cleaned = stem

    if _RE_GOOGLE_ID.search(cleaned):
        cleaned = _RE_GOOGLE_ID.sub("", cleaned).strip()
        reasons.append("google_id")

    if _RE_NUMBERED_SUFFIX.search(cleaned):
        cleaned = _RE_NUMBERED_SUFFIX.sub("", cleaned).strip()
        reasons.append("numbered_suffix")

    return cleaned, reasons


def _proposed_filename(original: str, local_path: Path) -> Optional[FilenameFix]:
    """Compute a clean filename for *original*, or return None if already clean."""
    p = Path(original)
    stem = p.stem
    ext = p.suffix

    reasons: list[str] = []

    # Extension case normalisation
    new_ext = ext.lower()
    if new_ext != ext:
        reasons.append("ext_case")

    cleaned_stem, stem_reasons = _clean_stem(stem)
    reasons.extend(stem_reasons)

    if not reasons:
        return None  # nothing to fix

    proposed = cleaned_stem + new_ext

    # Collision avoidance: if proposed name already exists (and is different),
    # append _1, _2, ...
    if proposed != original:
        candidate = Path(local_path) / proposed
        counter = 1
        while candidate.exists() and candidate.name != original:
            proposed = f"{cleaned_stem}_{counter}{new_ext}"
            candidate = Path(local_path) / proposed
            counter += 1

    return FilenameFix(original=original, proposed=proposed, reasons=reasons)


def scan_filenames(source_id: str) -> FilenameScanResult:
    """Return a list of files with naming issues and their proposed clean names."""
    source = source_manager.get_source(source_id)
    if not source:
        raise ValueError(f"Source '{source_id}' not found")

    local_path = Path(source.local_path).expanduser()
    fixes: list[FilenameFix] = []
    total = 0

    for f in sorted(local_path.rglob("*")):
        if not f.is_file():
            continue
        # Scan all files, not just images — videos with bad names should be caught too
        total += 1
        fix = _proposed_filename(f.name, local_path)
        if fix:
            fixes.append(fix)

    return FilenameScanResult(source_id=source_id, fixes=fixes, total_files_scanned=total)


async def apply_filenames(source_id: str, fixes: list[FilenameFix]) -> BatchResult:
    """Rename files: cloud-first, then local.  Evicts thumbnail cache on success."""
    source = source_manager.get_source(source_id)
    if not source:
        raise ValueError(f"Source '{source_id}' not found")

    local_path = Path(source.local_path).expanduser()
    result = BatchResult(total=len(fixes))

    for fix in fixes:
        if fix.original == fix.proposed:
            continue

        local_file = local_path / fix.original
        if not local_file.is_file():
            result.failed.append({"filename": fix.original, "error": "File not found locally"})
            continue

        # Path traversal guard
        try:
            local_file.resolve().relative_to(local_path.resolve())
        except ValueError:
            result.failed.append({"filename": fix.original, "error": "Path traversal detected"})
            continue

        # STEP 1: rename on cloud (must succeed first)
        if source.rclone_remote:
            cloud_result = await rclone_movefile_raw(
                source.rclone_remote, fix.original, fix.proposed
            )
            if not cloud_result.success:
                result.failed.append({
                    "filename": fix.original,
                    "error": f"Cloud rename failed: {cloud_result.error}",
                })
                continue

        # STEP 2: rename local (atomic via Path.rename)
        new_local = local_path / fix.proposed
        try:
            local_file.rename(new_local)
        except Exception as exc:
            result.failed.append({"filename": fix.original, "error": f"Local rename failed: {exc}"})
            continue

        # Evict thumbnail cache
        for stale in THUMB_CACHE_DIR.glob(f"{source_id}_{fix.original}_*.jpg"):
            stale.unlink(missing_ok=True)

        logger.info(f"Renamed '{fix.original}' -> '{fix.proposed}' in source '{source_id}'")
        result.succeeded.append(fix.original)

    return result


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

class DupGroup(BaseModel):
    files: list[FileInfo]
    keep_suggestion: str   # filename of the copy we suggest keeping
    md5: str


class DupScanResult(BaseModel):
    source_id: str
    groups: list[DupGroup]
    total_files_scanned: int
    duplicate_count: int   # total files that are duplicates (not counting the kept copy)


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _pick_keeper(infos: list[tuple[Path, FileInfo]]) -> str:
    """Choose which file to keep: prefer the one without Google ID or numbered suffix."""
    def score(item: tuple[Path, FileInfo]) -> int:
        name = item[1].filename
        s = 0
        if _RE_GOOGLE_ID.search(name):
            s += 10  # higher = worse
        if _RE_NUMBERED_SUFFIX.search(Path(name).stem):
            s += 5
        return s

    best = min(infos, key=score)
    return best[1].filename


def scan_duplicates(source_id: str) -> DupScanResult:
    """Find exact (byte-for-byte) duplicate files using size-then-MD5 grouping."""
    source = source_manager.get_source(source_id)
    if not source:
        raise ValueError(f"Source '{source_id}' not found")

    local_path = Path(source.local_path).expanduser()

    # Collect all files
    all_files: list[tuple[Path, int]] = []
    for f in local_path.rglob("*"):
        if f.is_file():
            all_files.append((f, f.stat().st_size))

    total = len(all_files)

    # Group by size first (fast pre-filter)
    size_buckets: dict[int, list[Path]] = {}
    for path, size in all_files:
        size_buckets.setdefault(size, []).append(path)

    # Hash only files that share a size
    hash_buckets: dict[str, list[tuple[Path, FileInfo]]] = {}
    for size, paths in size_buckets.items():
        if len(paths) < 2:
            continue
        for path in paths:
            try:
                digest = _md5(path)
            except Exception as exc:
                logger.warning(f"Could not hash {path}: {exc}")
                continue
            st = path.stat()
            info = FileInfo(
                filename=path.name,
                size_bytes=st.st_size,
                modified_epoch=int(st.st_mtime),
            )
            hash_buckets.setdefault(digest, []).append((path, info))

    # Build groups
    groups: list[DupGroup] = []
    dup_count = 0
    for digest, items in hash_buckets.items():
        if len(items) < 2:
            continue
        keeper = _pick_keeper(items)
        group_infos = [info for _, info in items]
        groups.append(DupGroup(
            files=group_infos,
            keep_suggestion=keeper,
            md5=digest,
        ))
        dup_count += len(items) - 1  # all but the kept copy are duplicates

    groups.sort(key=lambda g: g.files[0].filename)

    return DupScanResult(
        source_id=source_id,
        groups=groups,
        total_files_scanned=total,
        duplicate_count=dup_count,
    )


async def apply_duplicates(source_id: str, to_delete: list[str]) -> BatchResult:
    """Delete specified files: cloud-first, then local. Evicts thumbnail cache."""
    source = source_manager.get_source(source_id)
    if not source:
        raise ValueError(f"Source '{source_id}' not found")

    local_path = Path(source.local_path).expanduser()
    result = BatchResult(total=len(to_delete))

    for filename in to_delete:
        local_file = local_path / filename
        if not local_file.is_file():
            result.failed.append({"filename": filename, "error": "File not found locally"})
            continue

        try:
            local_file.resolve().relative_to(local_path.resolve())
        except ValueError:
            result.failed.append({"filename": filename, "error": "Path traversal detected"})
            continue

        # STEP 1: delete from cloud
        if source.rclone_remote:
            cloud_result = await rclone_deletefile_raw(source.rclone_remote, filename)
            if not cloud_result.success:
                result.failed.append({
                    "filename": filename,
                    "error": f"Cloud delete failed: {cloud_result.error}",
                })
                continue

        # STEP 2: delete local
        try:
            local_file.unlink()
        except Exception as exc:
            result.failed.append({"filename": filename, "error": f"Local delete failed: {exc}"})
            continue

        for stale in THUMB_CACHE_DIR.glob(f"{source_id}_{filename}_*.jpg"):
            stale.unlink(missing_ok=True)

        logger.info(f"Deleted duplicate '{filename}' from source '{source_id}'")
        result.succeeded.append(filename)

    return result


# ---------------------------------------------------------------------------
# Video management
# ---------------------------------------------------------------------------

class VideoScanResult(BaseModel):
    source_id: str
    videos: list[FileInfo]
    total_size_bytes: int


def scan_videos(source_id: str) -> VideoScanResult:
    """List all video files in the source directory."""
    source = source_manager.get_source(source_id)
    if not source:
        raise ValueError(f"Source '{source_id}' not found")

    local_path = Path(source.local_path).expanduser()
    videos: list[FileInfo] = []
    total_bytes = 0

    for f in sorted(local_path.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        st = f.stat()
        videos.append(FileInfo(
            filename=f.name,
            size_bytes=st.st_size,
            modified_epoch=int(st.st_mtime),
        ))
        total_bytes += st.st_size

    return VideoScanResult(
        source_id=source_id,
        videos=videos,
        total_size_bytes=total_bytes,
    )


async def apply_videos(source_id: str, to_delete: list[str]) -> BatchResult:
    """Delete specified video files: cloud-first, then local."""
    source = source_manager.get_source(source_id)
    if not source:
        raise ValueError(f"Source '{source_id}' not found")

    local_path = Path(source.local_path).expanduser()
    result = BatchResult(total=len(to_delete))

    for filename in to_delete:
        local_file = local_path / filename
        if not local_file.is_file():
            result.failed.append({"filename": filename, "error": "File not found locally"})
            continue

        try:
            local_file.resolve().relative_to(local_path.resolve())
        except ValueError:
            result.failed.append({"filename": filename, "error": "Path traversal detected"})
            continue

        # Validate it's actually a video extension (user-supplied list)
        if local_file.suffix.lower() not in VIDEO_EXTENSIONS:
            result.failed.append({"filename": filename, "error": "Not a video file"})
            continue

        # STEP 1: delete from cloud
        if source.rclone_remote:
            cloud_result = await rclone_deletefile_raw(source.rclone_remote, filename)
            if not cloud_result.success:
                result.failed.append({
                    "filename": filename,
                    "error": f"Cloud delete failed: {cloud_result.error}",
                })
                continue

        # STEP 2: delete local
        try:
            local_file.unlink()
        except Exception as exc:
            result.failed.append({"filename": filename, "error": f"Local delete failed: {exc}"})
            continue

        logger.info(f"Deleted video '{filename}' from source '{source_id}'")
        result.succeeded.append(filename)

    return result
