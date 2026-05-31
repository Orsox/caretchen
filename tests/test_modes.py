from dictapaste.modes import DictationMode, MODE_LABELS, build_mode_prompt


def test_translate_mode_auto_selects_direction():
    prompt = build_mode_prompt("Text: {transcript}", DictationMode.TRANSLATE)

    assert "Wenn der Quelltext Deutsch ist" in prompt
    assert "Englisch" in prompt
    assert "In allen anderen Fällen" in prompt
    assert "Deutsch" in prompt


def test_command_mode_is_available():
    prompt = build_mode_prompt("Text: {transcript}", DictationMode.COMMAND)

    assert "Slash-Befehl" in prompt


def test_direct_mode_is_named_direkt():
    assert DictationMode.DIRECT.value == "direct"
    assert MODE_LABELS[DictationMode.DIRECT] == "Direkt"
