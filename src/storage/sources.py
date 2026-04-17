"""
PicFrame 4.0 - Sources Storage.

JSON-based storage for photo source configurations.
This is a thin wrapper around source_manager for compatibility.
"""

from pathlib import Path

from src.services.source_manager import PhotoSource, source_manager


def list_sources() -> list[PhotoSource]:
    """List all configured photo sources."""
    return source_manager.list_sources()


def get_source(source_id: str) -> PhotoSource | None:
    """Get a source by ID."""
    return source_manager.get_source(source_id)


def create_source(name: str, rclone_remote: str | None = None) -> PhotoSource:
    """Create a new photo source."""
    return source_manager.create_source(name, rclone_remote)


def delete_source(source_id: str) -> bool:
    """Delete a photo source."""
    return source_manager.delete_source(source_id)


def get_photo_count(source_id: str) -> int:
    """
    Get the number of photos in a source.

    Args:
        source_id: Source to count

    Returns:
        Number of image files
    """
    source = source_manager.get_source(source_id)
    if not source:
        return 0

    local_path = Path(source.local_path).expanduser()
    if not local_path.exists():
        return 0

    # Count image files
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    count = 0
    for file in local_path.rglob("*"):
        if file.is_file() and file.suffix.lower() in image_extensions:
            count += 1

    return count
