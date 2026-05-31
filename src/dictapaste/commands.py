from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    command: str
    aliases: tuple[str, ...]


SLASH_COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("/compact", ("compact", "kompakt", "komprimieren", "zusammenfassen")),
    SlashCommand("/new", ("new", "neu", "neue sitzung", "neuer chat")),
    SlashCommand("/reload", ("reload", "neu laden", "neuladen", "aktualisieren")),
)

_SLASH_PREFIX_RE = re.compile(r"^\s*(?:/|slash|schrägstrich|schraegstrich)\s*", re.IGNORECASE)
_NON_WORD_RE = re.compile(r"[^\wäöüß/]+", re.IGNORECASE)


def _normalize(text: str) -> str:
    normalized = text.casefold().strip()
    normalized = normalized.replace("schraegstrich", "slash")
    normalized = _NON_WORD_RE.sub(" ", normalized)
    return " ".join(normalized.split())


def resolve_slash_command(text: str, *, force: bool = False) -> str | None:
    """Resolve dictated command text to a known slash command."""
    raw = text.strip()
    if not raw:
        return None

    has_prefix = bool(_SLASH_PREFIX_RE.match(raw)) or raw.startswith("/")
    if not force and not has_prefix:
        return None

    without_prefix = _SLASH_PREFIX_RE.sub("", raw, count=1)
    normalized = _normalize(without_prefix)
    normalized = normalized.removeprefix("/").strip()

    for item in SLASH_COMMANDS:
        command_name = item.command.removeprefix("/")
        aliases = (command_name, *item.aliases)
        if normalized in {_normalize(alias) for alias in aliases}:
            return item.command

    return None
