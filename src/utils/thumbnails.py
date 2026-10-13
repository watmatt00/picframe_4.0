"""
PicFrame 4.0 - Shared thumbnail generation and cache.

Used by the app's thumbnail endpoint (GET /sources/{id}/photos/thumbnail), the
dashboard's Tools tab thumbnails and the photo tools (cache eviction).
"""

import asyncio
import glob
import io
from pathlib import Path

# Persistent (survives reboots, unlike the old /tmp/pfthumb). Entries are named
# "<prefix><source_id>_<filename>_<mtime>.jpg" and evicted on rename/delete and
# when a file's mtime changes.
THUMB_CACHE_DIR = Path.home() / ".picframe" / "thumbs"

# Max thumbnails decoded at once: a grid opens many requests in parallel, and a few
# full-size decodes at a time are faster on a Pi than many competing for RAM and CPU.
_SEMAPHORE = asyncio.Semaphore(2)


def cache_path(source_id: str, filename: str, mtime: int, prefix: str = "") -> Path:
    """Cache file for one version (mtime) of a photo."""
    key = filename.replace("/", "_")
    return THUMB_CACHE_DIR / f"{prefix}{source_id}_{key}_{mtime}.jpg"


def evict(source_id: str, filename: str) -> None:
    """Delete every cached thumbnail (app and dashboard sizes) of a photo."""
    key = glob.escape(filename.replace("/", "_"))
    sid = glob.escape(source_id)
    for pattern in (f"{sid}_{key}_*.jpg", f"dash_{sid}_{key}_*.jpg"):
        for stale in THUMB_CACHE_DIR.glob(pattern):
            stale.unlink(missing_ok=True)


def _render(local_file: Path, size: tuple[int, int], quality: int) -> bytes:
    """Decode a photo and return a JPEG thumbnail (runs in a worker thread)."""
    from PIL import Image, ImageOps  # noqa: PLC0415 — lazy import, Pillow is optional at startup

    try:
        import pillow_heif  # noqa: PLC0415
        pillow_heif.register_heif_opener()
    except ImportError:
        pass  # HEIC support optional; JPEG/PNG still work

    with Image.open(local_file) as img:
        # thumbnail() before convert(): for JPEGs it decodes at reduced scale (draft
        # mode); converting first would decode the full image.
        img.thumbnail(size, Image.LANCZOS)
        img = ImageOps.exif_transpose(img).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()


async def get_thumbnail(
    local_file: Path,
    source_id: str,
    filename: str,
    size: tuple[int, int],
    quality: int,
    prefix: str = "",
) -> bytes:
    """
    Return a cached JPEG thumbnail, generating it off the event loop if needed.

    Raises whatever Pillow raises for unreadable files.
    """
    mtime = int(local_file.stat().st_mtime)
    path = cache_path(source_id, filename, mtime, prefix)
    if path.exists():
        return path.read_bytes()

    async with _SEMAPHORE:
        # Another request may have made it while this one waited
        if path.exists():
            return path.read_bytes()
        loop = asyncio.get_running_loop()
        jpeg_bytes = await loop.run_in_executor(None, _render, local_file, size, quality)

    THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Drop thumbnails of older versions of this file (same size prefix)
    key = glob.escape(filename.replace("/", "_"))
    for stale in THUMB_CACHE_DIR.glob(f"{glob.escape(prefix + source_id)}_{key}_*.jpg"):
        stale.unlink(missing_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(jpeg_bytes)
    tmp.rename(path)  # atomic
    return jpeg_bytes
