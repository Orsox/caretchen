from __future__ import annotations

from dictapaste.config import (
    AppConfig,
    AudioConfig,
    CURRENT_CONFIG_VERSION,
    StreamingConfig,
    _migrate_config,
)


class TestConfigVersioning:
    """Tests for config versioning and migration."""

    def test_app_config_has_version_default(self) -> None:
        cfg = AppConfig()
        assert cfg.version == CURRENT_CONFIG_VERSION

    def test_from_dict_reads_version(self) -> None:
        raw = {"version": 0, "stt": {"model": "base"}, "llm": {}}
        cfg = AppConfig.from_dict(raw)
        assert cfg.version == 0

    def test_to_dict_includes_version(self) -> None:
        cfg = AppConfig()
        d = cfg.to_dict()
        assert "version" in d
        assert d["version"] == CURRENT_CONFIG_VERSION

    def test_migrate_v0_adds_audio_and_streaming(self) -> None:
        """Migration v0 -> current adds audio and streaming sections."""
        cfg = AppConfig(version=0)
        migrated = _migrate_config(cfg)
        assert migrated.version == CURRENT_CONFIG_VERSION
        assert migrated.audio is not None
        assert migrated.audio.device_index == -1
        assert migrated.streaming == StreamingConfig()

    def test_migrate_v0_preserves_existing_settings(self) -> None:
        """Migration v0 -> v1 preserves existing LLM/stt settings."""
        cfg = AppConfig(
            version=0,
            llm=AppConfig().llm.__class__(base_url="http://custom:1111", model="test-model"),
            stt=AppConfig().stt.__class__(model="small", language="de"),
        )
        migrated = _migrate_config(cfg)
        assert migrated.version == CURRENT_CONFIG_VERSION
        assert migrated.llm.base_url == "http://custom:1111"
        assert migrated.llm.model == "test-model"
        assert migrated.stt.model == "small"
        assert migrated.stt.language == "de"

    def test_migrate_current_version_is_noop(self) -> None:
        cfg = AppConfig(version=CURRENT_CONFIG_VERSION)
        migrated = _migrate_config(cfg)
        assert migrated.version == CURRENT_CONFIG_VERSION

    def test_migrate_future_version_logs_warning(self) -> None:
        """Future versions are not migrated but returned unchanged."""
        cfg = AppConfig(version=999)
        migrated = _migrate_config(cfg)
        assert migrated.version == 999
