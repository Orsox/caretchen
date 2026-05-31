from __future__ import annotations

from enum import Enum


class DictationMode(str, Enum):
    IMPROVE = "improve"
    PROMPT = "prompt"
    SUMMARIZE = "summarize"
    TRANSLATE = "translate"
    COMMAND = "command"
    DIRECT = "direct"


MODE_LABELS: dict[DictationMode, str] = {
    DictationMode.IMPROVE: "Verbessern",
    DictationMode.PROMPT: "Prompt",
    DictationMode.SUMMARIZE: "Kurzfassung",
    DictationMode.TRANSLATE: "Übersetzen",
    DictationMode.COMMAND: "Befehl",
    DictationMode.DIRECT: "Direkt",
}


_MODE_INSTRUCTIONS: dict[DictationMode, str] = {
    DictationMode.IMPROVE: "Bereinige und verbessere den diktierten Text als direkt verwendbare Endfassung.",
    DictationMode.PROMPT: "Formuliere aus dem diktierten Text einen klaren, direkt verwendbaren Prompt.",
    DictationMode.SUMMARIZE: "Verdichte den diktierten Text zu einer kurzen, direkt verwendbaren Fassung.",
    DictationMode.TRANSLATE: (
        "Erkenne die Sprache des diktierten Textes automatisch. "
        "Wenn der Quelltext Deutsch ist, übersetze ihn in natürliches Englisch. "
        "In allen anderen Fällen übersetze ihn in natürliches Deutsch. "
        "Gib ausschließlich die Übersetzung aus, ohne Erklärungen."
    ),
    DictationMode.COMMAND: "Wandle den diktierten Text in einen direkt ausführbaren Slash-Befehl um.",
    DictationMode.DIRECT: "Gib den diktierten Text direkt und unverändert ohne LLM-Verarbeitung aus.",
}


def coerce_mode(value: DictationMode | str | None) -> DictationMode:
    if isinstance(value, DictationMode):
        return value
    if isinstance(value, str):
        normalized = value.lower().strip()
        for mode in DictationMode:
            if mode.value == normalized:
                return mode
    return DictationMode.IMPROVE


def build_mode_prompt(base_template: str, mode: DictationMode | str | None) -> str:
    selected = coerce_mode(mode)
    instruction = _MODE_INSTRUCTIONS[selected]
    return (
        f"Aufgabe: {instruction}\n"
        "Gib ausschließlich das finale Ergebnis aus: keine Überschrift, keine Liste, "
        "keine Erklärung, keine Analyse und keinen Denkprozess.\n\n"
        f"{base_template}"
    )
