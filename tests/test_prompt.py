import pytest

from dictapaste.prompt import DEFAULT_PROMPT, load_prompt, render_prompt, save_prompt


def test_render_prompt_success():
    template = "Clean this ({language}): {transcript}"
    output = render_prompt(template, "  hello world  ", language="de")

    assert output == "Clean this (de): hello world"


def test_render_prompt_requires_transcript_placeholder():
    with pytest.raises(ValueError):
        render_prompt("No placeholder here", "hello")


def test_render_prompt_rejects_unknown_placeholder():
    with pytest.raises(ValueError):
        render_prompt("{transcript} {unknown}", "hello")


def test_load_prompt_prefers_yaml_prompt(tmp_path):
    (tmp_path / "dictapaste.yaml").write_text(
        (
            "llm:\n"
            "  base_url: http://127.0.0.1:1234\n"
            "input:\n"
            "  mouse_button: x1\n"
            "prompt: |\n"
            "  YAML prompt line 1\n"
            "  {transcript}\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / "prompt.txt").write_text("TXT prompt {transcript}\n", encoding="utf-8")

    loaded = load_prompt(config_dir=tmp_path, root_dir=tmp_path)

    assert loaded == "YAML prompt line 1\n{transcript}"


def test_save_prompt_writes_yaml_and_txt(tmp_path):
    save_prompt("Prompt from settings {transcript}", config_dir=tmp_path, root_dir=tmp_path)

    txt_content = (tmp_path / "prompt.txt").read_text(encoding="utf-8").strip()
    yaml_content = (tmp_path / "dictapaste.yaml").read_text(encoding="utf-8")

    assert txt_content == "Prompt from settings {transcript}"
    assert "prompt:" in yaml_content
    assert "Prompt from settings {transcript}" in yaml_content


def test_load_prompt_falls_back_to_default_when_missing(tmp_path):
    loaded = load_prompt(config_dir=tmp_path, root_dir=tmp_path)
    assert loaded == DEFAULT_PROMPT
