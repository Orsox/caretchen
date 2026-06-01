from __future__ import annotations

from pathlib import Path

import yaml

from .config import prompt_path, root_yaml_path

DEFAULT_PROMPT = """Bereinige den folgenden diktierten Text.
Ziele:
1) Entferne Füllwörter, Satzabbrüche, Wiederholungen, Selbstkorrekturen und unnötige Einleitungen.
2) Korrigiere Grammatik, Rechtschreibung und Zeichensetzung.
3) Verdichte den Text so stark wie sinnvoll, ohne inhaltlich relevante Informationen, Anforderungen, Absichten oder Details zu verlieren.
4) Behandle das Ergebnis nicht als Zusammenfassung, sondern als bereinigte, kompakte Endfassung derselben Aussage.
5) Gib nur den finalen Text als direkt weiterverwendbaren Fließtext aus.
6) Gib keine Überschrift, keine Liste, keine Erklärungen und keinen Denkprozess aus.
7) Erfinde keine Fakten und füge nichts hinzu.

Sprachhinweis: {language}

Text:
{transcript}
"""


def _load_prompt_from_yaml(config_dir: Path | None = None, root_dir: Path | None = None) -> str | None:
    path = root_yaml_path(config_dir=config_dir, root_dir=root_dir)
    if not path.exists():
        return None

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None

    if not isinstance(raw, dict):
        return None

    prompt = raw.get("prompt")
    if not isinstance(prompt, str):
        return None

    cleaned = prompt.strip()
    return cleaned or None


def _save_prompt_to_yaml(prompt_text: str, config_dir: Path | None = None, root_dir: Path | None = None) -> None:
    path = root_yaml_path(config_dir=config_dir, root_dir=root_dir)

    raw: dict = {}
    if path.exists():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded
        except Exception:
            raw = {}

    raw["prompt"] = prompt_text
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def load_prompt(config_dir: Path | None = None, root_dir: Path | None = None) -> str:
    yaml_prompt = _load_prompt_from_yaml(config_dir=config_dir, root_dir=root_dir)
    if yaml_prompt is not None:
        return yaml_prompt

    path = prompt_path(config_dir)
    if not path.exists():
        save_prompt(DEFAULT_PROMPT, config_dir=config_dir, root_dir=root_dir)
        return DEFAULT_PROMPT

    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception:
        return DEFAULT_PROMPT

    return content if content else DEFAULT_PROMPT


def save_prompt(prompt_text: str, config_dir: Path | None = None, root_dir: Path | None = None) -> Path:
    normalized_prompt = prompt_text.strip()

    path = prompt_path(config_dir)
    path.write_text(normalized_prompt + "\n", encoding="utf-8")

    _save_prompt_to_yaml(normalized_prompt, config_dir=config_dir, root_dir=root_dir)
    return path


def render_prompt(template: str, transcript: str, language: str = "auto") -> str:
    if "{transcript}" not in template:
        raise ValueError("Prompt template must include {transcript}.")

    normalized_language = language or "auto"
    cleaned_transcript = transcript.strip()

    try:
        return template.format(
            transcript=cleaned_transcript,
            language=normalized_language,
        )
    except KeyError as exc:
        raise ValueError(f"Unsupported prompt placeholder: {exc}") from exc
