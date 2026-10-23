"""
WanderWall - Photo Tools Service.

Scan-then-apply operations for photo library maintenance:
- Filename cleaning: strip Google Photos ID tokens, numbered-dup suffixes,
  and rename UUID/hex-hash filenames to YYYYMMDD_HHMMSS using EXIF date
- Duplicate detection: hash-based exact deduplication
- Video management: list and remove video files Pi3D cannot display
- Corrupt photo finder: empty files and photos Pillow can't decode (PL-127)
- Rotate photos: left/right/180, or apply the EXIF orientation (PL-126)

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
from src.utils import thumbnails
from src.utils.rclone import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    rclone_deletefile_raw,
    rclone_movefile_raw,
)

logger = logging.getLogger(__name__)


# Regex patterns for filename issues
_RE_GOOGLE_ID = re.compile(r"\s*\{[^}]+\}")      # " {AByz57...}"
_RE_NUMBERED_SUFFIX = re.compile(r"\s*\(\d+\)$")  # " (0)", " (54)"
_RE_SPECIAL_CHARS = re.compile(r"[^A-Za-z0-9_.\-]")  # anything the strict rename rule rejects

# Stems longer than this are considered machine-generated and renamed to YYYYMMDD_HHMMSS
_LONG_NAME_THRESHOLD = 20

# EXIF tags
_EXIF_TAG_DATETIME_ORIGINAL = 36867
_EXIF_TAG_ORIENTATION = 274
_EXIF_DATE_FMT = "%Y:%m:%d %H:%M:%S"

# Magic bytes for wrong-extension detection (read only first 12 bytes per file)
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_GIF_MAGIC = b"GIF8"
_HEIC_BRANDS = {b"heic", b"heix", b"mif1", b"msf1"}


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
    reasons: list[str]      # e.g. ["google_id", "numbered_suffix", "ext_case", "long_name", "spaces"]
    needs_review: bool = False  # True when proposed name came from mtime, not EXIF
    exif_date: Optional[str] = None        # "YYYY-MM-DD HH:MM" for display, None if unavailable
    exif_orientation: Optional[int] = None  # EXIF tag 274 value; 1 = normal


class FilenameScanResult(BaseModel):
    source_id: str
    fixes: list[FilenameFix]
    total_files_scanned: int


class FileBrowserEntry(BaseModel):
    filename: str
    exif_date: Optional[str] = None
    exif_orientation: Optional[int] = None


class FileBrowserResult(BaseModel):
    source_id: str
    files: list[FileBrowserEntry]
    total: int


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


def _detect_actual_ext(path: Path) -> Optional[str]:
    """Return the correct lowercase extension based on magic bytes, or None if already correct.

    Reads only the first 12 bytes. Returns None for unrecognized types (no false flags).
    """
    try:
        header = path.read_bytes()[:12]
    except OSError:
        return None

    if header[:3] == _JPEG_MAGIC:
        correct = ".jpg"
    elif header[:8] == _PNG_MAGIC:
        correct = ".png"
    elif header[:4] == _GIF_MAGIC:
        correct = ".gif"
    elif header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        correct = ".webp"
    elif header[4:8] == b"ftyp" and header[8:12] in _HEIC_BRANDS:
        correct = ".heic"
    else:
        return None  # unrecognized — don't flag

    declared = path.suffix.lower()
    if declared == ".jpeg":
        declared = ".jpg"
    return correct if correct != declared else None


def _parse_exif_bytes_for_orientation(raw: bytes) -> Optional[int]:
    """Extract Orientation (tag 274) from raw EXIF bytes. Returns int or None."""
    if not raw or len(raw) < 8:
        return None
    try:
        offset = 6 if raw[:6] == b"Exif\x00\x00" else 0
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
            if tag == _EXIF_TAG_ORIENTATION:
                # Type SHORT (3), count 1 — value is inline in first 2 bytes of value field
                return struct.unpack(endian + "H", tiff[pos + 8:pos + 10])[0]
            pos += 12
    except Exception:
        pass
    return None


def _read_exif_display(path: Path) -> tuple[Optional[str], Optional[int]]:
    """Return (date_str, orientation) for display in the Filename Cleaner table.

    date_str is formatted as 'YYYY-MM-DD HH:MM' (seconds omitted for space).
    orientation is the raw EXIF tag 274 value (1=normal, 6=90°CW, etc.).
    Returns (None, None) on failure or unsupported format.
    """
    date_str: Optional[str] = None
    orientation: Optional[int] = None
    suffix = path.suffix.lower()

    try:
        if suffix in {".jpg", ".jpeg", ".png"}:
            from PIL import Image  # noqa: PLC0415
            with Image.open(path) as img:
                exif = img._getexif() or {}
            raw_date = exif.get(_EXIF_TAG_DATETIME_ORIGINAL)
            if raw_date:
                dt = datetime.strptime(raw_date, _EXIF_DATE_FMT)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            orientation = exif.get(_EXIF_TAG_ORIENTATION)

        elif suffix in {".heic", ".heif"}:
            import pillow_heif  # noqa: PLC0415
            heif = pillow_heif.open_heif(path)
            raw_exif = heif.info.get("exif", b"")
            raw_date = _parse_exif_bytes_for_datetime(raw_exif)
            if raw_date:
                dt = datetime.strptime(raw_date, _EXIF_DATE_FMT)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            orientation = _parse_exif_bytes_for_orientation(raw_exif)

    except Exception as exc:
        logger.debug(f"EXIF display read failed for {path.name}: {exc}")

    return date_str, orientation


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

    if ' ' in cleaned:
        cleaned = re.sub(r' +', '_', cleaned)
        reasons.append("spaces")

    # e.g. "Mom_&_Dad_+_#1" -> "Mom_Dad_1"; may leave "" (caller falls back to a date stem)
    if _RE_SPECIAL_CHARS.search(cleaned):
        cleaned = _RE_SPECIAL_CHARS.sub("_", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        reasons.append("special_chars")

    return cleaned, reasons


def _proposed_filename(original: str, local_path: Path) -> Optional[FilenameFix]:
    """Compute a clean filename for *original*, or return None if already clean."""
    p = Path(original)
    stem = p.stem
    ext = p.suffix
    new_ext = ext.lower()

    reasons: list[str] = []
    needs_review = False

    # --- Long stem: rename to YYYYMMDD_HHMMSS ---
    if len(stem) > _LONG_NAME_THRESHOLD:
        reasons.append("long_name")
        # Also check magic bytes — UUID file might have a mislabeled extension too
        actual_ext = _detect_actual_ext(local_path / original)
        if actual_ext is not None:
            reasons.append("wrong_ext")
            new_ext = actual_ext
        elif new_ext != ext:
            reasons.append("ext_case")

        date_stem, needs_review = _date_stem_from_file(local_path / original)
        proposed = _unique_name(date_stem, new_ext, original, local_path)
        exif_date, exif_orientation = _read_exif_display(local_path / original)
        return FilenameFix(
            original=original,
            proposed=proposed,
            reasons=reasons,
            needs_review=needs_review,
            exif_date=exif_date,
            exif_orientation=exif_orientation,
        )

    # --- Standard stem cleaning (Google ID, numbered suffix, ext case) ---
    # Check for wrong extension via magic bytes (overrides ext_case if also wrong type)
    actual_ext = _detect_actual_ext(local_path / original)
    if actual_ext is not None:
        reasons.append("wrong_ext")
        new_ext = actual_ext  # use the correct extension in proposed name
    elif new_ext != ext:
        reasons.append("ext_case")

    cleaned_stem, stem_reasons = _clean_stem(stem)
    reasons.extend(stem_reasons)

    if not reasons:
        return None  # nothing to fix

    if not cleaned_stem:
        # Nothing usable left (e.g. "&&&.jpg"): name it by date like long names
        cleaned_stem, needs_review = _date_stem_from_file(local_path / original)

    proposed = _unique_name(cleaned_stem, new_ext, original, local_path)
    exif_date, exif_orientation = _read_exif_display(local_path / original)
    return FilenameFix(
        original=original,
        proposed=proposed,
        reasons=reasons,
        needs_review=needs_review,
        exif_date=exif_date,
        exif_orientation=exif_orientation,
    )


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


def scan_files(source_id: str) -> FileBrowserResult:
    """Return all files in a source with EXIF dates, for manual renaming."""
    source = source_manager.get_source(source_id)
    if not source:
        raise ValueError(f"Source '{source_id}' not found")
    local_path = Path(source.local_path).expanduser()
    files: list[FileBrowserEntry] = []
    for f in sorted(local_path.rglob("*")):
        if not f.is_file():
            continue
        exif_date, exif_orientation = _read_exif_display(f)
        files.append(FileBrowserEntry(
            filename=f.name,
            exif_date=exif_date,
            exif_orientation=exif_orientation,
        ))
    return FileBrowserResult(source_id=source_id, files=files, total=len(files))


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
        thumbnails.evict(source_id, fix.original)

        logger.info(f"Renamed '{fix.original}' -> '{fix.proposed}' in source '{source_id}'")
        result.succeeded.append(fix.original)

    return result


async def rename_file(source_id: str, original: str, proposed: str) -> BatchResult:
    """Rename a single file by name. Cloud-first. Intended for the manual rename card."""
    fix = FilenameFix(original=original, proposed=proposed, reasons=["manual"])
    return await apply_filenames(source_id, [fix])


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

        thumbnails.evict(source_id, filename)

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


# ---------------------------------------------------------------------------
# Shared: resolve a user-supplied filename inside a source
# ---------------------------------------------------------------------------

def _source_file(local_path: Path, filename: str) -> Path:
    """The file `filename` inside local_path; ValueError if it's missing or outside it."""
    local_file = local_path / filename
    try:
        local_file.resolve().relative_to(local_path.resolve())
    except ValueError:
        raise ValueError("Path traversal detected")
    if not local_file.is_file():
        raise ValueError("File not found locally")
    return local_file


def _open_image_support() -> None:
    """Let Pillow open HEIC/HEIF when pillow-heif is installed (it is on the frames)."""
    try:
        import pillow_heif  # noqa: PLC0415
        pillow_heif.register_heif_opener()
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Corrupt / unreadable photo finder (PL-127)
# ---------------------------------------------------------------------------

class CorruptFile(BaseModel):
    filename: str
    size_bytes: int
    error: str


class CorruptScanResult(BaseModel):
    source_id: str
    files: list[CorruptFile]
    total_files_scanned: int
    skipped: int = 0   # files that couldn't be checked (e.g. HEIC without pillow-heif)


def _check_image(path: Path) -> Optional[str]:
    """Why this photo can't be shown, or None if it decodes. Decodes at reduced scale."""
    from PIL import Image  # noqa: PLC0415

    if path.stat().st_size == 0:
        return "Empty file (0 bytes)"
    try:
        with Image.open(path) as img:
            img.verify()  # structure and checksums, without decoding pixels
        with Image.open(path) as img:
            img.draft("RGB", (320, 320))  # JPEG: decode at 1/8 scale, still reads the whole stream
            img.load()                    # catches truncated or damaged image data
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"[:200]
    return None


def scan_corrupt(source_id: str) -> CorruptScanResult:
    """List photos in the source that are empty or that Pillow can't open or decode."""
    source = source_manager.get_source(source_id)
    if not source:
        raise ValueError(f"Source '{source_id}' not found")
    _open_image_support()
    heif_ok = ".heic" in _registered_extensions()

    local_path = Path(source.local_path).expanduser()
    found: list[CorruptFile] = []
    scanned = skipped = 0
    for f in sorted(local_path.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if f.suffix.lower() in {".heic", ".heif"} and not heif_ok:
            skipped += 1
            continue
        scanned += 1
        error = _check_image(f)
        if error:
            found.append(CorruptFile(
                filename=f.relative_to(local_path).as_posix(),
                size_bytes=f.stat().st_size,
                error=error,
            ))
    return CorruptScanResult(source_id=source_id, files=found, total_files_scanned=scanned, skipped=skipped)


def _registered_extensions() -> set[str]:
    """File extensions Pillow can open right now."""
    from PIL import Image  # noqa: PLC0415
    return {ext.lower() for ext, fmt in Image.registered_extensions().items() if fmt in Image.OPEN}


async def apply_corrupt(source_id: str, to_delete: list[str]) -> BatchResult:
    """Delete the chosen unreadable photos: cloud first, then the frame."""
    source = source_manager.get_source(source_id)
    if not source:
        raise ValueError(f"Source '{source_id}' not found")

    local_path = Path(source.local_path).expanduser()
    result = BatchResult(total=len(to_delete))
    for filename in to_delete:
        try:
            local_file = _source_file(local_path, filename)
        except ValueError as exc:
            result.failed.append({"filename": filename, "error": str(exc)})
            continue
        if local_file.suffix.lower() not in IMAGE_EXTENSIONS:
            result.failed.append({"filename": filename, "error": "Not a photo"})
            continue
        if source.rclone_remote:
            cloud = await rclone_deletefile_raw(source.rclone_remote, filename)
            if not cloud.success:
                result.failed.append({"filename": filename, "error": f"Cloud delete failed: {cloud.error}"})
                continue
        try:
            local_file.unlink()
        except Exception as exc:
            result.failed.append({"filename": filename, "error": f"Local delete failed: {exc}"})
            continue
        thumbnails.evict(source_id, filename)
        logger.info(f"Deleted unreadable photo '{filename}' from source '{source_id}'")
        result.succeeded.append(filename)
    return result


# ---------------------------------------------------------------------------
# Rotate photos (PL-126)
# ---------------------------------------------------------------------------

# How to turn a photo, as seen on screen: degrees clockwise, or "auto" to apply
# the EXIF orientation to the pixels (and reset the tag)
ROTATIONS = {"right": 90, "180": 180, "left": 270, "auto": 0}
_ROTATE_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".heic": "HEIF", ".heif": "HEIF"}


class RotateItem(BaseModel):
    filename: str
    rotate: str   # "left", "right", "180" or "auto"


def _rotate_to(path: Path, rotate: str, dest: Path) -> None:
    """Write `path` turned as asked to `dest`, with the EXIF orientation reset to normal."""
    from PIL import Image, ImageOps  # noqa: PLC0415

    fmt = _ROTATE_FORMATS[path.suffix.lower()]
    with Image.open(path) as img:
        exif = img.getexif()
        icc = img.info.get("icc_profile")
        upright = ImageOps.exif_transpose(img)   # what the frame and thumbnails show today
        degrees = ROTATIONS[rotate]
        out = upright.rotate(-degrees, expand=True) if degrees else upright
        exif[_EXIF_TAG_ORIENTATION] = 1
        kwargs: dict = {"exif": exif.tobytes()}
        if icc:
            kwargs["icc_profile"] = icc
        if fmt == "JPEG":
            kwargs["quality"] = 95
            if out.mode not in ("RGB", "L", "CMYK"):
                out = out.convert("RGB")
        out.save(dest, format=fmt, **kwargs)


async def rotate_photos(source_id: str, items: list[RotateItem]) -> BatchResult:
    """
    Turn photos left, right or 180°, or bake their EXIF orientation into the pixels.

    Each rotated photo goes to the album's cloud folder first, then replaces the
    copy on the frame, so the next sync keeps it. JPEGs are re-encoded at quality 95.
    """
    import asyncio  # noqa: PLC0415
    import os  # noqa: PLC0415
    import uuid  # noqa: PLC0415

    from src.utils.rclone import rclone_copyto  # noqa: PLC0415

    source = source_manager.get_source(source_id)
    if not source:
        raise ValueError(f"Source '{source_id}' not found")
    _open_image_support()

    local_path = Path(source.local_path).expanduser()
    result = BatchResult(total=len(items))
    for item in items:
        filename = item.filename
        if item.rotate not in ROTATIONS:
            result.failed.append({"filename": filename, "error": f"Unknown rotation '{item.rotate}'"})
            continue
        try:
            local_file = _source_file(local_path, filename)
        except ValueError as exc:
            result.failed.append({"filename": filename, "error": str(exc)})
            continue
        suffix = local_file.suffix.lower()
        if suffix not in _ROTATE_FORMATS:
            result.failed.append({"filename": filename, "error": "Only JPEG, PNG and HEIC photos can be rotated"})
            continue
        if suffix in {".heic", ".heif"} and ".heic" not in _registered_extensions():
            result.failed.append({"filename": filename, "error": "HEIC support (pillow-heif) isn't installed"})
            continue

        tmp = local_file.with_name(f".rotate-{uuid.uuid4().hex}{suffix}")
        try:
            await asyncio.to_thread(_rotate_to, local_file, item.rotate, tmp)
            if source.rclone_remote:
                cloud = await rclone_copyto(tmp, f"{source.rclone_remote}/{filename}")
                if not cloud.success:
                    result.failed.append({"filename": filename, "error": f"Cloud upload failed: {cloud.error}"})
                    continue
            os.replace(tmp, local_file)
        except Exception as exc:
            result.failed.append({"filename": filename, "error": f"Rotate failed: {exc}"})
            continue
        finally:
            tmp.unlink(missing_ok=True)
        thumbnails.evict(source_id, filename)
        logger.info(f"Rotated '{filename}' ({item.rotate}) in source '{source_id}'")
        result.succeeded.append(filename)
    return result
