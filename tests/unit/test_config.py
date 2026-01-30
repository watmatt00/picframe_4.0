"""
Unit tests for configuration module.
"""

import pytest
import tempfile
from pathlib import Path

from src.config.settings import Settings, FrameConfig, DisplayConfig
from src.config.manager import ConfigManager
from src.config.schema import SourceConfigSchema


class TestSettings:
    """Tests for application settings."""

    def test_default_settings(self):
        """Settings should have sensible defaults."""
        settings = Settings()

        assert settings.frame.id == "picframe"
        assert settings.frame.name == "PicFrame"
        assert settings.display.rotation_interval == 30
        assert settings.sync.interval == 900
        assert settings.logging.level == "INFO"

    def test_settings_from_yaml(self):
        """Settings should load from YAML file."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(b"""
frame:
  id: test-frame
  name: Test Frame
display:
  current_source: test-source
  rotation_interval: 60
""")
            f.flush()

            settings = Settings.from_yaml(Path(f.name))

            assert settings.frame.id == "test-frame"
            assert settings.frame.name == "Test Frame"
            assert settings.display.current_source == "test-source"
            assert settings.display.rotation_interval == 60

    def test_settings_to_yaml(self):
        """Settings should save to YAML file."""
        settings = Settings(
            frame=FrameConfig(id="save-test", name="Save Test"),
            display=DisplayConfig(current_source="test", rotation_interval=45),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            settings.to_yaml(path)

            assert path.exists()

            # Reload and verify
            loaded = Settings.from_yaml(path)
            assert loaded.frame.id == "save-test"
            assert loaded.display.rotation_interval == 45


class TestConfigManager:
    """Tests for config file management."""

    def test_read_write_config(self):
        """Config manager should read and write correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            manager = ConfigManager(path)

            # Write config
            manager.write({"key": "value", "nested": {"a": 1}})

            # Read config
            config = manager.read()
            assert config["key"] == "value"
            assert config["nested"]["a"] == 1

    def test_update_config(self):
        """Config manager should update values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            manager = ConfigManager(path)

            manager.write({"key": "value", "other": "keep"})
            manager.update({"key": "updated"})

            config = manager.read()
            assert config["key"] == "updated"
            assert config["other"] == "keep"

    def test_get_nested_key(self):
        """Config manager should get nested keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            manager = ConfigManager(path)

            manager.write({"level1": {"level2": {"value": 42}}})

            assert manager.get("level1.level2.value") == 42
            assert manager.get("missing.key", "default") == "default"


class TestConfigSchema:
    """Tests for configuration validation."""

    def test_valid_source_config(self):
        """Valid source config should pass validation."""
        config = SourceConfigSchema(
            id="test-source",
            name="Test Source",
            local_path="/home/pi/Pictures/test",
            rclone_remote="koofr:test",
            enabled=True,
        )
        assert config.id == "test-source"

    def test_invalid_source_id(self):
        """Invalid source ID should fail validation."""
        with pytest.raises(ValueError):
            SourceConfigSchema(
                id="invalid id with spaces",
                name="Test",
                local_path="/path",
            )

    def test_path_traversal_rejected(self):
        """Path traversal attempts should be rejected."""
        with pytest.raises(ValueError):
            SourceConfigSchema(
                id="test",
                name="Test",
                local_path="/home/pi/../../../etc/passwd",
            )
