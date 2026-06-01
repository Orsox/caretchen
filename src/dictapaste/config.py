from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import os
import platform
import tomllib

import tomli_w
import yaml

from .paste import PasteMode

CONFIG_FILE_NAME = "config.toml"
PROMPT_FILE_NAME = "prompt.txt"
ROOT_YAML_FILE_NAME = "dictapaste.yaml"
CURRENT_CONFIG_VERSION = 3


@dataclass
class STTConfig:
    model: str = "medium"
    language: str = "auto"


@dataclass
class LLMConfig:
    enabled_by_default: bool = True
    base_url: str = "http://127.0.0.1:1234"
    model: str = "google/gemma-4-e4b"
    timeout_sec: int = 20
    temperature: float = 0.2


@dataclass
class AudioConfig:
    device_index: int = -1  # -1 = system default

    def to_dict(self) -> dict:
        return {"device_index": self.device_index}

    @classmethod
    def from_dict(cls, raw: dict) -> "AudioConfig":
        try:
            return cls(device_index=int(raw.get("device_index", -1)))
        except (TypeError, ValueError):
            return cls()


@dataclass
class InputConfig:
    mouse_button: str = "x1"


@dataclass
class OutputConfig:
    paste_mode: str = "ctrl_v"

    def to_dict(self) -> dict:
        return {"paste_mode": self.paste_mode}

    @classmethod
    def from_dict(cls, raw: dict) -> "OutputConfig":
        mode = str(raw.get("paste_mode", "ctrl_v")).lower().strip()
        if mode not in ("ctrl_v", "ctrl_shift_v", "copy", "xdotool", "ydotool", "ydotool_type", "wtype", "portal"):
            mode = "ctrl_v"
        return cls(paste_mode=mode)


@dataclass
class StartupConfig:
    start_with_windows: bool = False


@dataclass
class StreamingConfig:
    enabled: bool = True
    stt_chunking_enabled: bool = False
    chunk_duration_sec: int = 3
    llm_start_mode: str = "final"

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "stt_chunking_enabled": self.stt_chunking_enabled,
            "chunk_duration_sec": self.chunk_duration_sec,
            "llm_start_mode": self.llm_start_mode,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "StreamingConfig":
        duration = _safe_int(raw.get("chunk_duration_sec"), 3)
        if duration not in (1, 2, 3, 4, 5, 10):
            duration = 3
        llm_start_mode = str(raw.get("llm_start_mode", "final")).lower().strip()
        if llm_start_mode not in ("final", "experimental_partial"):
            llm_start_mode = "final"
        return cls(
            enabled=bool(raw.get("enabled", True)),
            stt_chunking_enabled=bool(raw.get("stt_chunking_enabled", False)),
            chunk_duration_sec=duration,
            llm_start_mode=llm_start_mode,
        )


@dataclass
class AppConfig:
    version: int = CURRENT_CONFIG_VERSION
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    input: InputConfig = field(default_factory=InputConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    startup: StartupConfig = field(default_factory=StartupConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "audio": self.audio.to_dict(),
            "stt": {
                "model": self.stt.model,
                "language": self.stt.language,
            },
            "llm": {
                "enabled_by_default": self.llm.enabled_by_default,
                "base_url": self.llm.base_url,
                "model": self.llm.model,
                "timeout_sec": self.llm.timeout_sec,
                "temperature": self.llm.temperature,
            },
            "input": {
                "mouse_button": self.input.mouse_button,
            },
            "output": {
                "paste_mode": self.output.paste_mode,
            },
            "startup": {
                "start_with_windows": self.startup.start_with_windows,
            },
            "streaming": self.streaming.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "AppConfig":
        audio_raw = raw.get("audio", {}) if isinstance(raw.get("audio", {}), dict) else {}
        stt_raw = raw.get("stt", {}) if isinstance(raw.get("stt", {}), dict) else {}
        llm_raw = raw.get("llm", {}) if isinstance(raw.get("llm", {}), dict) else {}
        input_raw = raw.get("input", {}) if isinstance(raw.get("input", {}), dict) else {}
        output_raw = raw.get("output", {}) if isinstance(raw.get("output", {}), dict) else {}
        startup_raw = raw.get("startup", {}) if isinstance(raw.get("startup", {}), dict) else {}
        streaming_raw = raw.get("streaming", {}) if isinstance(raw.get("streaming", {}), dict) else {}

        return cls(
            version=int(raw.get("version", 0)),
            audio=AudioConfig.from_dict(audio_raw),
            stt=STTConfig(
                model=str(stt_raw.get("model", "medium")),
                language=str(stt_raw.get("language", "auto")),
            ),
            llm=LLMConfig(
                enabled_by_default=bool(llm_raw.get("enabled_by_default", True)),
                base_url=str(llm_raw.get("base_url", "http://127.0.0.1:1234")),
                model=str(llm_raw.get("model", "google/gemma-4-e4b")),
                timeout_sec=_safe_int(llm_raw.get("timeout_sec"), 20),
                temperature=_safe_float(llm_raw.get("temperature"), 0.2),
            ),
            input=InputConfig(
                mouse_button=str(input_raw.get("mouse_button", "x1")),
            ),
            output=OutputConfig(
                paste_mode=str(output_raw.get("paste_mode", "ctrl_v")),
            ),
            startup=StartupConfig(
                start_with_windows=bool(startup_raw.get("start_with_windows", False)),
            ),
            streaming=StreamingConfig.from_dict(streaming_raw),
        )


def default_config_dir() -> Path:
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
        return base / "DictaPaste"

    return Path.home() / ".config" / "dictapaste"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_root_dir(config_dir: Path | None, root_dir: Path | None) -> Path:
    if root_dir is not None:
        return root_dir
    if config_dir is not None:
        return config_dir
    return project_root()


def ensure_config_dir(config_dir: Path | None = None) -> Path:
    path = config_dir or default_config_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path(config_dir: Path | None = None) -> Path:
    return ensure_config_dir(config_dir) / CONFIG_FILE_NAME


def prompt_path(config_dir: Path | None = None) -> Path:
    return ensure_config_dir(config_dir) / PROMPT_FILE_NAME


def root_yaml_path(config_dir: Path | None = None, root_dir: Path | None = None) -> Path:
    resolved_root = _resolve_root_dir(config_dir, root_dir)
    resolved_root.mkdir(parents=True, exist_ok=True)
    return resolved_root / ROOT_YAML_FILE_NAME


def _root_yaml_payload(config: AppConfig) -> dict:
    return {
        "llm": {
            "enabled_by_default": config.llm.enabled_by_default,
            "base_url": config.llm.base_url,
            "model": config.llm.model,
            "timeout_sec": config.llm.timeout_sec,
            "temperature": config.llm.temperature,
        },
        "input": {
            "mouse_button": config.input.mouse_button,
        },
        "startup": {
            "start_with_windows": config.startup.start_with_windows,
        },
        "streaming": config.streaming.to_dict(),
    }


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _migrate_config(cfg: AppConfig) -> AppConfig:
    """Migrate config to the current version.

    Returns the migrated config. Unknown future versions are logged and returned unchanged.
    """
    current_version = cfg.version

    if current_version < 1:
        # Migration v0 -> v1: add missing audio section with defaults
        if not hasattr(cfg, "audio") or cfg.audio is None:
            cfg.audio = AudioConfig()
        elif cfg.audio.device_index is None:
            cfg.audio = AudioConfig()
        cfg.version = 1

    if current_version < 2:
        # Migration v1 -> v2: add streaming controls with safe defaults.
        if not hasattr(cfg, "streaming") or cfg.streaming is None:
            cfg.streaming = StreamingConfig()
        cfg.version = 2

    if current_version < 3:
        # Migration v2 -> v3: add guarded LLM start mode.
        if not hasattr(cfg, "streaming") or cfg.streaming is None:
            cfg.streaming = StreamingConfig()
        elif not getattr(cfg.streaming, "llm_start_mode", None):
            cfg.streaming.llm_start_mode = "final"
        cfg.version = 3

    if current_version > CURRENT_CONFIG_VERSION:
        logger = logging.getLogger(__name__)
        logger.warning(
            "Config version %d is newer than expected (%d). Proceeding without migration.",
            current_version,
            CURRENT_CONFIG_VERSION,
        )

    return cfg


def _apply_root_yaml_overrides(config: AppConfig, raw: dict) -> AppConfig:
    llm_raw = raw.get("llm", {}) if isinstance(raw.get("llm", {}), dict) else {}
    input_raw = raw.get("input", {}) if isinstance(raw.get("input", {}), dict) else {}
    startup_raw = raw.get("startup", {}) if isinstance(raw.get("startup", {}), dict) else {}
    streaming_raw = raw.get("streaming", {}) if isinstance(raw.get("streaming", {}), dict) else {}

    if "enabled_by_default" in llm_raw:
        config.llm.enabled_by_default = bool(llm_raw.get("enabled_by_default"))
    if "base_url" in llm_raw:
        config.llm.base_url = str(llm_raw.get("base_url") or config.llm.base_url)
    if "model" in llm_raw:
        config.llm.model = str(llm_raw.get("model") or config.llm.model)
    if "timeout_sec" in llm_raw:
        config.llm.timeout_sec = _safe_int(llm_raw.get("timeout_sec"), config.llm.timeout_sec)
    if "temperature" in llm_raw:
        config.llm.temperature = _safe_float(llm_raw.get("temperature"), config.llm.temperature)

    if "mouse_button" in input_raw:
        config.input.mouse_button = str(input_raw.get("mouse_button") or config.input.mouse_button)

    if "start_with_windows" in startup_raw:
        config.startup.start_with_windows = bool(startup_raw.get("start_with_windows"))

    if "enabled" in streaming_raw:
        config.streaming.enabled = bool(streaming_raw.get("enabled"))
    if "stt_chunking_enabled" in streaming_raw:
        config.streaming.stt_chunking_enabled = bool(streaming_raw.get("stt_chunking_enabled"))
    if "chunk_duration_sec" in streaming_raw:
        config.streaming.chunk_duration_sec = StreamingConfig.from_dict(streaming_raw).chunk_duration_sec
    if "llm_start_mode" in streaming_raw:
        config.streaming.llm_start_mode = StreamingConfig.from_dict(streaming_raw).llm_start_mode

    return config


def load_config(config_dir: Path | None = None, root_dir: Path | None = None) -> AppConfig:
    path = config_path(config_dir)
    if not path.exists():
        cfg = AppConfig()
        save_config(cfg, config_dir=config_dir, root_dir=root_dir)
        return cfg

    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        cfg = AppConfig.from_dict(raw)
        cfg = _migrate_config(cfg)
    except Exception:
        cfg = AppConfig()
        cfg = _migrate_config(cfg)

    yaml_path = root_yaml_path(config_dir=config_dir, root_dir=root_dir)
    if not yaml_path.exists():
        save_root_yaml(cfg, config_dir=config_dir, root_dir=root_dir)
        return cfg

    try:
        yaml_raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return cfg

    if isinstance(yaml_raw, dict):
        return _apply_root_yaml_overrides(cfg, yaml_raw)

    return cfg


def save_root_yaml(config: AppConfig, config_dir: Path | None = None, root_dir: Path | None = None) -> Path:
    path = root_yaml_path(config_dir=config_dir, root_dir=root_dir)
    payload = _root_yaml_payload(config)

    if path.exists():
        try:
            existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(existing, dict) and isinstance(existing.get("prompt"), str):
                payload["prompt"] = existing["prompt"]
        except Exception:
            pass

    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def save_config(config: AppConfig, config_dir: Path | None = None, root_dir: Path | None = None) -> Path:
    path = config_path(config_dir)
    # Ensure version is current
    config.version = CURRENT_CONFIG_VERSION
    path.write_text(tomli_w.dumps(config.to_dict()), encoding="utf-8")
    save_root_yaml(config, config_dir=config_dir, root_dir=root_dir)
    return path
