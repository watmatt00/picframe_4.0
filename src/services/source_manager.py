"""
PicFrame 4.0 - Source Manager.

Manages photo sources (folders) and their configurations.
"""

import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
import yaml

logger = logging.getLogger(__name__)

# Default sources config location
SOURCES_PATH = Path.home() / ".picframe" / "sources.yaml"


class PhotoSource(BaseModel):
    """A photo source configuration."""
    id: str
    name: str
    local_path: str
    rclone_remote: Optional[str] = None
    enabled: bool = True


class SourceManager:
    """
    Manages photo source configurations.

    Sources are stored in ~/.picframe/sources.yaml.
    """

    def __init__(self, sources_path: Path = SOURCES_PATH):
        self._path = sources_path

    def _load_sources(self) -> list[PhotoSource]:
        """Load sources from YAML file."""
        if not self._path.exists():
            return []

        try:
            with open(self._path) as f:
                data = yaml.safe_load(f) or {}
            return [PhotoSource(**s) for s in data.get("sources", [])]
        except Exception as e:
            logger.error(f"Failed to load sources: {e}")
            return []

    def _save_sources(self, sources: list[PhotoSource]):
        """Save sources to YAML file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        data = {"sources": [s.model_dump() for s in sources]}

        with open(self._path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False)

    def list_sources(self) -> list[PhotoSource]:
        """
        List all configured photo sources.

        Returns:
            List of PhotoSource configurations
        """
        return self._load_sources()

    def get_source(self, source_id: str) -> Optional[PhotoSource]:
        """
        Get a specific source by ID.

        Args:
            source_id: Source identifier

        Returns:
            PhotoSource if found, None otherwise
        """
        sources = self._load_sources()
        for source in sources:
            if source.id == source_id:
                return source
        return None

    def create_source(
        self,
        name: str,
        rclone_remote: Optional[str] = None,
    ) -> PhotoSource:
        """
        Create a new photo source.

        If rclone_remote is not provided, auto-configures one using the
        first available Koofr rclone remote and creates the cloud folder.

        Args:
            name: Human-readable name
            rclone_remote: Optional rclone remote specification

        Returns:
            The created PhotoSource
        """
        sources = self._load_sources()

        # Generate ID from name
        source_id = name.lower().replace(" ", "_")
        # Sanitize: only allow alphanumeric and underscores
        source_id = re.sub(r"[^a-z0-9_]", "_", source_id)

        # Ensure unique ID
        existing_ids = {s.id for s in sources}
        if source_id in existing_ids:
            counter = 2
            while f"{source_id}_{counter}" in existing_ids:
                counter += 1
            source_id = f"{source_id}_{counter}"

        # Create local path
        local_path = Path.home() / "Pictures" / source_id
        local_path.mkdir(parents=True, exist_ok=True)

        # Auto-configure rclone remote if not provided
        if not rclone_remote:
            rclone_remote = self._auto_configure_remote(source_id)

        source = PhotoSource(
            id=source_id,
            name=name,
            local_path=str(local_path),
            rclone_remote=rclone_remote,
            enabled=True,
        )

        sources.append(source)
        self._save_sources(sources)

        logger.info(f"Created source '{source_id}': {local_path}, remote: {rclone_remote}")
        return source

    def _auto_configure_remote(self, source_id: str) -> Optional[str]:
        """
        Auto-configure an rclone remote for a new source.

        Finds the first Koofr rclone remote and creates a cloud folder
        named KFR_<source_id>.

        Args:
            source_id: The source identifier

        Returns:
            rclone remote string (e.g. "kfr_tkframe:KFR_source_id") or None
        """
        try:
            # Find Koofr remotes
            result = subprocess.run(
                ["rclone", "listremotes"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                logger.warning("Failed to list rclone remotes")
                return None

            remote_name = None
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.endswith(":"):
                    candidate = line[:-1]
                    # Check if it's a Koofr remote
                    type_result = subprocess.run(
                        ["rclone", "config", "show", candidate],
                        capture_output=True, text=True, timeout=10,
                    )
                    if "koofr" in type_result.stdout.lower():
                        remote_name = candidate
                        break

            if not remote_name:
                logger.warning("No Koofr rclone remote found")
                return None

            # Create cloud folder
            cloud_folder = f"KFR_{source_id}"
            rclone_remote = f"{remote_name}:{cloud_folder}"

            mkdir_result = subprocess.run(
                ["rclone", "mkdir", rclone_remote],
                capture_output=True, text=True, timeout=30,
            )
            if mkdir_result.returncode != 0:
                logger.error(f"Failed to create cloud folder: {mkdir_result.stderr}")
                return None

            logger.info(f"Auto-configured remote: {rclone_remote}")
            return rclone_remote

        except Exception as e:
            logger.error(f"Failed to auto-configure remote: {e}")
            return None

    def delete_source(self, source_id: str) -> bool:
        """
        Delete a photo source configuration.

        Note: Does not delete the local files.

        Args:
            source_id: Source to delete

        Returns:
            True if source was deleted
        """
        sources = self._load_sources()
        original_count = len(sources)

        sources = [s for s in sources if s.id != source_id]

        if len(sources) < original_count:
            self._save_sources(sources)
            logger.info(f"Deleted source '{source_id}'")
            return True

        return False

    def backfill_remotes(self) -> list[str]:
        """Set rclone_remote on sources that were created before Koofr was configured."""
        updated = []
        sources = self._load_sources()
        for source in sources:
            if source.enabled and not source.rclone_remote:
                remote = self._auto_configure_remote(source.id)
                if remote:
                    source.rclone_remote = remote
                    updated.append(source.id)
        if updated:
            self._save_sources(sources)
            logger.info(f"Backfilled rclone_remote for sources: {updated}")
        return updated

    def update_source(self, source: PhotoSource) -> bool:
        """
        Update an existing source configuration.

        Args:
            source: Updated source configuration

        Returns:
            True if source was updated
        """
        sources = self._load_sources()

        for i, s in enumerate(sources):
            if s.id == source.id:
                sources[i] = source
                self._save_sources(sources)
                logger.info(f"Updated source '{source.id}'")
                return True

        return False


# Global manager instance
source_manager = SourceManager()
