"""
WanderWall - Sources Storage.

JSON-based storage for photo source configurations.
This is a thin wrapper around source_manager for compatibility.
"""

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

