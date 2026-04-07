"""
PicFrame 4.0 - Photo Tools Service.

Scan-then-apply operations for photo library maintenance:
- Filename cleaning: strip Google Photos ID tokens, numbered-dup suffixes,
  and rename UUID/hex-hash filenames to YYYYMMDD_HHMMSS using EXIF date
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
import struct
from datetime import datetime
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

# UUID: 8-4-4-4-12 hex groups (iOS Camera Roll exports)
_RE_UUID = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"
    r"-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
# Hex hash: 32+ contiguous hex chars with no other word chars (Google Photos)
_RE_HEX_HASH = re.compile(r"^[0-9a-fA-F]{32,}$")

# EXIF tag for DateTimeOriginal
_EXIF_TAG_DATETIME_ORIGINAL = 36867
_EXIF_DATE_FMT = "%Y:%m:%d %H:%M:%S"


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
    reasons: list[str]      # e.g. ["google_id", "numbered_suffix", "ext_case", "uuid_name"]
    needs_review: bool = False  # True when proposed name came from mtime, not EXIF


class FilenameScanResult(BaseModel):
    source_id: str
    fixes: list[FilenameFix]
    total_files_scanned: int


def _date_stem_from_file(path: Path) -> tuple[str, bool]:
    """Return (YYYYMMDD_HHMMSS, needs_review).

    Tries EXIF DateTimeOriginal first (JPEG via Pillow, HEIC via pillow-heif).
    Falls back to file mtime with needs_review=True so the UI can flag it.
    """
    # --- JPEG / PNG via Pillow ---
    if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        try:
            from PIL import Image  # noqa: PLC0415
            with Image.open(path) as img:
                exif = img._getexif() or {}
            val = exif.get(_EXIF_TAG_DATETIME_ORIGINAL)
            if val:
                dt = datetime.strptime(val, _EXIF_DATE_FMT)
                return dt.strftime("%Y%m%d_%H%M%S"), False
        except Exception as exc:
            logger.debug(f"Pillow EXIF read failed for {path.name}: {exc}")

    # --- HEIC via pillow-heif ---
    if path.suffix.lower() == ".heic":
        try:
            import pillow_heif  # noqa: PLC0415
            heif = pillow_heif.open_heif(path)
            raw_exif = heif.info.get("exif", b"")
            # Parse minimal EXIF: find DateTimeOriginal (tag 36867) in IFD
            dt_str = _parse_exif_bytes_for_datetime(raw_exif)
            if dt_str:
                dt = datetime.strptime(dt_str, _EXIF_DATE_FMT)
                return dt.strftime("%Y%m%d_%H%M%S"), False
        except Exception as exc:
            logger.debug(f"pillow-heif EXIF read failed for {path.name}: {exc}")

    # --- mtime fallback ---
    dt = datetime.fromtimestamp(path.stat().st_mtime)
    return dt.strftime("%Y%m%d_%H%M%S"), True


def _parse_exif_bytes_for_datetime(raw: bytes) -> Optional[str]:
    """Extract DateTimeOriginal string from raw EXIF bytes (minimal IFD parser)."""
    if not raw or len(raw) < 8:
        return None
    try:
        # EXIF header: "Exif\x00\x00" then TIFF header
        offset = 0
        if raw[:6] == b"Exif\x00\x00":
            offset = 6
        tiff = raw[offset:]
        if len(tiff) < 8:
            return None
        byte_order = tiff[:2]
        if byte_order == b"II":
            endian = "<"
        elif byte_order == b"MM":
            endian = ">"
        else:
            return None
        ifd_offset = struct.unpack(endian + "I", tiff[4:8])[0]
        if ifd_offset + 2 > len(tiff):
            return None
        num_entries = struct.unpack(endian + "H", tiff[ifd_offset:ifd_offset + 2])[0]
        pos = ifd_offset + 2
        for _ in range(num_entries):
            if pos + 12 > len(tiff):
                break
            tag = struct.unpack(endian + "H", tiff[pos:pos + 2])[0]
            type_ = struct.unpack(endian + "H", tiff[pos + 2:pos + 4])[0]
            count = struct.unpack(endian + "I", tiff[pos + 4:pos + 8])[0]
            value_raw = tiff[pos + 8:pos + 12]
            if tag == _EXIF_TAG_DATETIME_ORIGINAL and type_ == 2:
                # ASCII string — value is an offset if count > 4
                if count > 4:
                    str_offset = struct.unpack(endian + "I", value_raw)[0]
                    val = tiff[str_offset:str_offset + count - 1].decode("ascii", errors="ignore")
                else:
                    val = value_raw[:count - 1].decode("ascii", errors="ignore")
                return val if len(val) == 19 else None
            # Also check SubExifIFD (tag 34665) for nested IFD
            if tag == 34665:
                sub_offset = struct.unpack(endian + "I", value_raw)[0]
                result = _parse_ifd(tiff, sub_offset, endian)
                if result:
                    return result
            pos += 12
    except Exception:
        pass
    return None


def _parse_ifd(tiff: bytes, ifd_offset: int, endian: str) -> Optional[str]:
    """Parse a TIFF IFD for DateTimeOriginal."""
    try:
        if ifd_offset + 2 > len(tiff):
            return None
        num_entries = struct.unpack(endian + "H", tiff[ifd_offset:ifd_offset + 2])[0]
        pos = ifd_offset + 2
        for _ in range(num_entries):
            if pos + 12 > len(tiff):
                break
            tag = struct.unpack(endian + "H", tiff[pos:pos + 2])[0]
            type_ = struct.unpack(endian + "H", tiff[pos + 2:pos + 4])[0]
            count = struct.unpack(endian + "I", tiff[pos + 4:pos + 8])[0]
            value_raw = tiff[pos + 8:pos + 12]
            if tag == _EXIF_TAG_DATETIME_ORIGINAL and type_ == 2:
                if count > 4:
                    str_offset = struct.unpack(endian + "I", value_raw)[0]
                    val = tiff[str_offset:str_offset + count - 1].decode("ascii", errors="ignore")
                else:
                    val = value_raw[:count - 1].decode("ascii", errors="ignore")
                return val if len(val) == 19 else None
            pos += 12
    except Exception:
        pass
    return None


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
    new_ext = ext.lower()

    reasons: list[str] = []
    needs_review = False

    # --- UUID or hex-hash stem: rename to YYYYMMDD_HHMMSS ---
    if _RE_UUID.match(stem) or _RE_HEX_HASH.match(stem):
        reason = "uuid_name" if _RE_UUID.match(stem) else "hex_hash"
        reasons.append(reason)
        if new_ext != ext:
            reasons.append("ext_case")

        date_stem, needs_review = _date_stem_from_file(local_path / original)
        proposed = _unique_name(date_stem, new_ext, original, local_path)
        return FilenameFix(
            original=original,
            proposed=proposed,
            reasons=reasons,
            needs_review=needs_review,
        )

    # --- Standard stem cleaning (Google ID, numbered suffix, ext case) ---
    if new_ext != ext:
        reasons.append("ext_case")

    cleaned_stem, stem_reasons = _clean_stem(stem)
    reasons.extend(stem_reasons)

    if not reasons:
        return None  # nothing to fix

    proposed = _unique_name(cleaned_stem, new_ext, original, local_path)
    return FilenameFix(original=original, proposed=proposed, reasons=reasons)


def _unique_name(stem: str, ext: str, original: str, local_path: Path) -> str:
    """Return stem+ext, appending _1, _2, ... if that name already exists."""
    proposed = stem + ext
    if proposed == original:
        return proposed
    candidate = local_path / proposed
    counter = 1
    while candidate.exists() and candidate.name != original:
        proposed = f"{stem}_{counter}{ext}"
        candidate = local_path / proposed
        counter += 1
    return proposed


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
