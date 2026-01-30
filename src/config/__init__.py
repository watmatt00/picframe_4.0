"""
PicFrame 4.0 - Configuration Module.

Handles application configuration:
- settings: Pydantic settings from environment/files
- schema: Configuration validation schemas
- manager: Config file read/write with locking
"""

from src.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
