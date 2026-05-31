from __future__ import annotations

import platform
from enum import Enum, auto
from typing import NamedTuple


class ConflictSeverity(Enum):
    """Severity level for a mouse button conflict."""
    LOW = auto()        # Minor annoyance, unlikely to cause issues
    MEDIUM = auto()     # Common function, user should be aware
    HIGH = auto()       # Critical function that will likely interfere


class ConflictInfo(NamedTuple):
    """Information about a mouse button conflict."""
    button: str
    severity: ConflictSeverity
    description: str
    suggestion: str


# Platform-specific conflict definitions
# Keys are button names, values are (severity, description, suggestion)
_WINDOWS_CONFLICTS: dict[str, tuple[ConflictSeverity, str, str]] = {
    "middle": (
        ConflictSeverity.HIGH,
        "Middle-click often pastes the current clipboard content",
        "Consider using X1 or X2 to avoid accidental pastes",
    ),
    "x1": (
        ConflictSeverity.MEDIUM,
        "X1 is commonly used for 'Back' navigation in browsers and file explorer",
        "Consider using X2 or middle-click",
    ),
    "x2": (
        ConflictSeverity.MEDIUM,
        "X2 is commonly used for 'Forward' navigation in browsers and file explorer",
        "Consider using X1 or middle-click",
    ),
    "left": (
        ConflictSeverity.HIGH,
        "Left-click is the primary mouse button used for selection and clicking",
        "Consider using a side button (X1/X2) to avoid accidental triggers",
    ),
    "right": (
        ConflictSeverity.HIGH,
        "Right-click opens context menus in most applications",
        "Consider using a side button (X1/X2) to avoid interrupting workflows",
    ),
}

_LINUX_CONFLICTS: dict[str, tuple[ConflictSeverity, str, str]] = {
    **_WINDOWS_CONFLICTS,  # Same base conflicts
    "middle": (
        ConflictSeverity.HIGH,
        "Middle-click pastes the X11 PRIMARY selection in Linux",
        "Consider using X1 or X2 to avoid accidental pastes",
    ),
}


def get_conflicts_for_button(
    button_name: str,
    platform_name: str | None = None,
) -> list[ConflictInfo]:
    """Detect potential conflicts for a given mouse button.

    Returns a list of conflicts, sorted by severity (HIGH first).
    An empty list means no known conflicts for this button.
    """
    button_name = button_name.lower().strip()
    if platform_name is None:
        platform_name = platform.system()

    conflicts_map = _LINUX_CONFLICTS if platform_name == "Linux" else _WINDOWS_CONFLICTS

    if button_name not in conflicts_map:
        return []

    severity, description, suggestion = conflicts_map[button_name]
    return [
        ConflictInfo(
            button=button_name,
            severity=severity,
            description=description,
            suggestion=suggestion,
        )
    ]


def has_conflicts(
    button_name: str,
    platform_name: str | None = None,
) -> bool:
    """Check if a mouse button has any known conflicts."""
    return len(get_conflicts_for_button(button_name, platform_name)) > 0


def get_conflict_summary(button_name: str, platform_name: str | None = None) -> str:
    """Get a human-readable conflict summary for a mouse button."""
    conflicts = get_conflicts_for_button(button_name, platform_name)
    if not conflicts:
        return ""
    return conflicts[0].description


def get_conflict_warning(button_name: str, platform_name: str | None = None) -> str:
    """Get a user-facing warning message for a conflicting mouse button."""
    conflicts = get_conflicts_for_button(button_name, platform_name)
    if not conflicts:
        return ""
    conflict = conflicts[0]
    return f"{conflict.description} {conflict.suggestion}"
