from dictapaste.conflict import (
    ConflictSeverity,
    ConflictInfo,
    get_conflicts_for_button,
    get_conflict_summary,
    get_conflict_warning,
    has_conflicts,
)


class TestConflictDetection:
    """Tests for mouse button conflict detection."""

    # --- get_conflicts_for_button ---

    def test_no_conflict_for_unlisted_button(self) -> None:
        """Unknown button names return no conflicts."""
        assert get_conflicts_for_button("foobar") == []

    def test_middle_click_has_high_conflict_on_windows(self) -> None:
        """Middle-click is HIGH severity on Windows."""
        conflicts = get_conflicts_for_button("middle", "Windows")
        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.HIGH

    def test_middle_click_has_high_conflict_on_linux(self) -> None:
        """Middle-click is HIGH severity on Linux too."""
        conflicts = get_conflicts_for_button("middle", "Linux")
        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.HIGH

    def test_x1_has_medium_conflict(self) -> None:
        """X1 has MEDIUM severity (browser back)."""
        conflicts = get_conflicts_for_button("x1", "Windows")
        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.MEDIUM

    def test_x2_has_medium_conflict(self) -> None:
        """X2 has MEDIUM severity (browser forward)."""
        conflicts = get_conflicts_for_button("x2", "Windows")
        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.MEDIUM

    def test_left_click_has_high_conflict(self) -> None:
        """Left-click is HIGH severity (primary button)."""
        conflicts = get_conflicts_for_button("left", "Windows")
        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.HIGH

    def test_right_click_has_high_conflict(self) -> None:
        """Right-click is HIGH severity (context menus)."""
        conflicts = get_conflicts_for_button("right", "Windows")
        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.HIGH

    def test_case_insensitive(self) -> None:
        """Button names are case-insensitive."""
        assert len(get_conflicts_for_button("MIDDLE", "Windows")) == 1
        assert len(get_conflicts_for_button("Middle", "Windows")) == 1
        assert len(get_conflicts_for_button("middle", "Windows")) == 1

    def test_conflict_has_suggestion(self) -> None:
        """Every conflict includes a suggestion."""
        conflicts = get_conflicts_for_button("middle", "Windows")
        assert conflicts[0].suggestion != ""

    def test_conflict_has_description(self) -> None:
        """Every conflict includes a description."""
        conflicts = get_conflicts_for_button("middle", "Windows")
        assert conflicts[0].description != ""

    # --- has_conflicts ---

    def test_has_conflicts_returns_true_for_middle(self) -> None:
        assert has_conflicts("middle", "Windows") is True

    def test_has_conflicts_returns_false_for_none(self) -> None:
        assert has_conflicts("foobar", "Windows") is False

    # --- get_conflict_summary ---

    def test_conflict_summary_for_middle(self) -> None:
        summary = get_conflict_summary("middle", "Windows")
        assert "paste" in summary.lower() or "clipboard" in summary.lower()

    def test_conflict_summary_for_none(self) -> None:
        assert get_conflict_summary("foobar", "Windows") == ""

    # --- get_conflict_warning ---

    def test_conflict_warning_for_middle(self) -> None:
        warning = get_conflict_warning("middle", "Windows")
        assert "paste" in warning.lower() or "clipboard" in warning.lower()

    def test_conflict_warning_for_none(self) -> None:
        assert get_conflict_warning("foobar", "Windows") == ""

    # --- ConflictInfo ---

    def test_conflict_info_is_namedtuple(self) -> None:
        info = ConflictInfo(
            button="middle",
            severity=ConflictSeverity.HIGH,
            description="Test",
            suggestion="Fix it",
        )
        assert info.button == "middle"
        assert info.severity == ConflictSeverity.HIGH
        assert info.description == "Test"
        assert info.suggestion == "Fix it"

    # --- Platform differences ---

    def test_linux_middle_mentions_x11(self) -> None:
        """Linux middle-click warning mentions X11 PRIMARY selection."""
        conflicts = get_conflicts_for_button("middle", "Linux")
        assert len(conflicts) == 1
        assert "X11" in conflicts[0].description or "primary" in conflicts[0].description.lower()

    def test_windows_middle_mentions_clipboard(self) -> None:
        """Windows middle-click warning mentions clipboard."""
        conflicts = get_conflicts_for_button("middle", "Windows")
        assert len(conflicts) == 1
        assert "clipboard" in conflicts[0].description.lower() or "paste" in conflicts[0].description.lower()
