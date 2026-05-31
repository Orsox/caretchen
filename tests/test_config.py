from dictapaste.config import (
    AppConfig,
    InputConfig,
    LLMConfig,
    OutputConfig,
    STTConfig,
    StartupConfig,
    StreamingConfig,
    load_config,
    save_config,
)


def test_load_creates_defaults(tmp_path):
    cfg = load_config(tmp_path)

    assert cfg.stt.model == "medium"
    assert cfg.stt.language == "auto"
    assert (tmp_path / "config.toml").exists()
    assert (tmp_path / "dictapaste.yaml").exists()
    assert cfg.startup.start_with_windows is False
    assert cfg.streaming.enabled is True
    assert cfg.streaming.stt_chunking_enabled is False
    assert cfg.streaming.chunk_duration_sec == 3
    assert cfg.streaming.llm_start_mode == "final"


def test_save_and_load_roundtrip(tmp_path):
    cfg = AppConfig(
        stt=STTConfig(model="small", language="de"),
        llm=LLMConfig(
            enabled_by_default=False,
            base_url="http://localhost:7777",
            model="test-model",
            timeout_sec=9,
            temperature=0.4,
        ),
        input=InputConfig(mouse_button="x2"),
        output=OutputConfig(paste_mode="ctrl_v"),
        startup=StartupConfig(start_with_windows=True),
        streaming=StreamingConfig(enabled=False, stt_chunking_enabled=True, chunk_duration_sec=5, llm_start_mode="experimental_partial"),
    )

    save_config(cfg, tmp_path)
    loaded = load_config(tmp_path)

    assert loaded.stt.model == "small"
    assert loaded.stt.language == "de"
    assert loaded.llm.enabled_by_default is False
    assert loaded.llm.base_url == "http://localhost:7777"
    assert loaded.llm.model == "test-model"
    assert loaded.llm.timeout_sec == 9
    assert loaded.llm.temperature == 0.4
    assert loaded.input.mouse_button == "x2"
    assert loaded.output.paste_mode == "ctrl_v"
    assert loaded.startup.start_with_windows is True
    assert loaded.streaming.enabled is False
    assert loaded.streaming.stt_chunking_enabled is True
    assert loaded.streaming.chunk_duration_sec == 5
    assert loaded.streaming.llm_start_mode == "experimental_partial"


def test_root_yaml_overrides_llm_and_mouse(tmp_path):
    cfg = AppConfig(
        llm=LLMConfig(base_url="http://127.0.0.1:1234", model="base-model", timeout_sec=20, temperature=0.2),
        input=InputConfig(mouse_button="x1"),
    )
    save_config(cfg, tmp_path)

    yaml_path = tmp_path / "dictapaste.yaml"
    yaml_path.write_text(
        """
llm:
  base_url: http://localhost:9999
  model: yaml-model
  timeout_sec: 45
  temperature: 0.9
input:
  mouse_button: x2
""".strip()
        + "\n",
        encoding="utf-8",
    )

    loaded = load_config(tmp_path)

    assert loaded.llm.base_url == "http://localhost:9999"
    assert loaded.llm.model == "yaml-model"
    assert loaded.llm.timeout_sec == 45
    assert loaded.llm.temperature == 0.9
    assert loaded.input.mouse_button == "x2"


def test_root_yaml_overrides_streaming(tmp_path):
    cfg = AppConfig(streaming=StreamingConfig(enabled=True, stt_chunking_enabled=False, chunk_duration_sec=3))
    save_config(cfg, tmp_path)

    yaml_path = tmp_path / "dictapaste.yaml"
    yaml_path.write_text(
        (
            "streaming:\n"
            "  enabled: false\n"
            "  stt_chunking_enabled: true\n"
            "  chunk_duration_sec: 10\n"
            "  llm_start_mode: experimental_partial\n"
        ),
        encoding="utf-8",
    )

    loaded = load_config(tmp_path)
    assert loaded.streaming.enabled is False
    assert loaded.streaming.stt_chunking_enabled is True
    assert loaded.streaming.chunk_duration_sec == 10
    assert loaded.streaming.llm_start_mode == "experimental_partial"


def test_root_yaml_overrides_startup(tmp_path):
    cfg = AppConfig(startup=StartupConfig(start_with_windows=False))
    save_config(cfg, tmp_path)

    yaml_path = tmp_path / "dictapaste.yaml"
    yaml_path.write_text(
        (
            "startup:\n"
            "  start_with_windows: true\n"
        ),
        encoding="utf-8",
    )

    loaded = load_config(tmp_path)
    assert loaded.startup.start_with_windows is True


def test_save_config_preserves_yaml_prompt(tmp_path):
    yaml_path = tmp_path / "dictapaste.yaml"
    yaml_path.write_text(
        (
            "llm:\n"
            "  base_url: http://127.0.0.1:1234\n"
            "input:\n"
            "  mouse_button: x1\n"
            "prompt: Keep this {transcript}\n"
        ),
        encoding="utf-8",
    )

    save_config(AppConfig(), tmp_path)

    saved = yaml_path.read_text(encoding="utf-8")
    assert "prompt: Keep this {transcript}" in saved


# ── Corrupt / invalid config ───────────────────────────────────────


def test_load_config_corrupt_toml_returns_defaults(tmp_path):
    (tmp_path / "config.toml").write_text("not valid toml {{{", encoding="utf-8")

    cfg = load_config(tmp_path)

    assert cfg.stt.model == "medium"
    assert cfg.llm.base_url == "http://127.0.0.1:1234"
    assert cfg.llm.model == "google/gemma-4-e4b"


# ── from_dict / to_dict roundtrip ──────────────────────────────────


def test_from_dict_with_missing_nested_sections():
    cfg = AppConfig.from_dict({})

    assert cfg.stt.model == "medium"
    assert cfg.stt.language == "auto"
    assert cfg.llm.enabled_by_default is True
    assert cfg.input.mouse_button == "x1"
    assert cfg.output.paste_mode == "ctrl_v"
    assert cfg.startup.start_with_windows is False


def test_from_dict_with_partial_sections():
    cfg = AppConfig.from_dict({"llm": {"base_url": "http://custom:9999"}})

    assert cfg.llm.base_url == "http://custom:9999"
    assert cfg.llm.timeout_sec == 20  # default preserved
    assert cfg.stt.model == "medium"  # other sections default


def test_from_dict_invalid_types_fallback():
    cfg = AppConfig.from_dict({
        "llm": {
            "timeout_sec": "not-a-number",
            "temperature": "hot",
        },
    })

    # Invalid values should fall back to defaults via _safe_int/_safe_float
    assert cfg.llm.timeout_sec == 20
    assert cfg.llm.temperature == 0.2


def test_to_dict_roundtrip():
    original = AppConfig(
        stt=STTConfig(model="base", language="en"),
        llm=LLMConfig(
            enabled_by_default=False,
            base_url="http://test:5555",
            model="test",
            timeout_sec=5,
            temperature=0.5,
        ),
        input=InputConfig(mouse_button="middle"),
        output=OutputConfig(paste_mode="ctrl_v"),
        startup=StartupConfig(start_with_windows=True),
        streaming=StreamingConfig(enabled=False, stt_chunking_enabled=True, chunk_duration_sec=10, llm_start_mode="experimental_partial"),
    )

    d = original.to_dict()
    restored = AppConfig.from_dict(d)

    assert restored.stt.model == original.stt.model
    assert restored.stt.language == original.stt.language
    assert restored.llm.enabled_by_default == original.llm.enabled_by_default
    assert restored.llm.base_url == original.llm.base_url
    assert restored.llm.model == original.llm.model
    assert restored.llm.timeout_sec == original.llm.timeout_sec
    assert restored.llm.temperature == original.llm.temperature
    assert restored.input.mouse_button == original.input.mouse_button
    assert restored.output.paste_mode == original.output.paste_mode
    assert restored.startup.start_with_windows == original.startup.start_with_windows
    assert restored.streaming.enabled == original.streaming.enabled
    assert restored.streaming.stt_chunking_enabled == original.streaming.stt_chunking_enabled
    assert restored.streaming.chunk_duration_sec == original.streaming.chunk_duration_sec
    assert restored.streaming.llm_start_mode == original.streaming.llm_start_mode


# ── YAML-only load ─────────────────────────────────────────────────


def test_load_config_yaml_only_no_toml(tmp_path):
    # No TOML file — load_config creates defaults + save_config which writes YAML
    # The YAML that was already there gets overwritten by save_config.
    # This test verifies that the flow completes without error and defaults are used.
    cfg = load_config(tmp_path)

    assert cfg.stt.model == "medium"  # defaults applied
    assert (tmp_path / "config.toml").exists()


# ── Invalid YAML types ─────────────────────────────────────────────


def test_root_yaml_invalid_type_fallback(tmp_path):
    cfg = AppConfig(llm=LLMConfig(timeout_sec=20, temperature=0.2))
    save_config(cfg, tmp_path)

    # Write YAML with wrong types
    yaml_path = tmp_path / "dictapaste.yaml"
    yaml_path.write_text(
        (
            "llm:\n"
            "  timeout_sec: not-a-number\n"
            "  temperature: hot\n"
        ),
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)

    # Invalid values should fall back to existing config values
    assert cfg.llm.timeout_sec == 20
    assert cfg.llm.temperature == 0.2


# ── Empty YAML ─────────────────────────────────────────────────────


def test_load_config_empty_yaml(tmp_path):
    cfg = AppConfig()
    save_config(cfg, tmp_path)

    yaml_path = tmp_path / "dictapaste.yaml"
    yaml_path.write_text("", encoding="utf-8")

    cfg = load_config(tmp_path)

    assert cfg.stt.model == "medium"  # defaults preserved


# ── YAML with non-dict content ─────────────────────────────────────


def test_load_config_yaml_is_list(tmp_path):
    cfg = AppConfig()
    save_config(cfg, tmp_path)

    yaml_path = tmp_path / "dictapaste.yaml"
    yaml_path.write_text("- item1\n- item2", encoding="utf-8")

    cfg = load_config(tmp_path)

    assert cfg.stt.model == "medium"  # defaults, list ignored
