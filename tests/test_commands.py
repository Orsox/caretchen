from dictapaste.commands import resolve_slash_command


def test_resolves_direct_slash_command():
    assert resolve_slash_command("/compact") == "/compact"
    assert resolve_slash_command("slash reload") == "/reload"
    assert resolve_slash_command("Schrägstrich new") == "/new"


def test_requires_prefix_without_force():
    assert resolve_slash_command("compact") is None


def test_force_resolves_command_mode_without_prefix():
    assert resolve_slash_command("kompakt", force=True) == "/compact"
    assert resolve_slash_command("neu laden", force=True) == "/reload"


def test_unknown_command_returns_none():
    assert resolve_slash_command("slash unknown") is None
