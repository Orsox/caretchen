import pytest

from dictapaste.config import LLMConfig
from dictapaste.llm import LLMCancelled, LLMError, LLMRefiner


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines
        self.status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(self._lines)


class _FakeClient:
    def __init__(self, timeout, capture):
        self._capture = capture
        self._capture["timeout"] = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        self._capture["url"] = url
        self._capture["json"] = json
        return _FakeResponse({"choices": [{"message": {"content": "Refined text"}}]})

    def stream(self, method, url, json):
        self._capture["method"] = method
        self._capture["url"] = url
        self._capture["json"] = json
        return _FakeStreamResponse(
            [
                'data: {"choices":[{"delta":{"content":"Refined "}}]}',
                'data: {"choices":[{"delta":{"content":"text"}}]}',
                "data: [DONE]",
            ]
        )


def test_refine_maps_request_and_parses_response(monkeypatch):
    capture = {}

    def _factory(timeout):
        return _FakeClient(timeout, capture)

    monkeypatch.setattr("dictapaste.llm.httpx.Client", _factory)

    config = LLMConfig(base_url="http://127.0.0.1:1234", model="google/gemma-4-e4b", timeout_sec=15, temperature=0.3)
    refiner = LLMRefiner(config)

    result = refiner.refine("hello", "Please fix: {transcript}", language="de")

    assert result == "Refined text"
    assert capture["timeout"] == 15
    assert capture["url"] == "http://127.0.0.1:1234/v1/chat/completions"
    assert capture["json"]["model"] == "google/gemma-4-e4b"
    assert capture["json"]["messages"][0]["role"] == "system"
    assert capture["json"]["messages"][1]["content"] == "Please fix: hello"
    assert capture["json"]["reasoning_effort"] == "none"
    assert capture["json"]["reasoning"] == {"effort": "none"}
    assert capture["json"]["think"] is False
    assert capture["json"]["thinking"] == {"type": "disabled"}
    assert capture["json"]["chat_template_kwargs"] == {"enable_thinking": False, "preserve_thinking": False}


def test_refine_stream_maps_request_and_streams_chunks(monkeypatch):
    capture = {}

    def _factory(timeout):
        return _FakeClient(timeout, capture)

    monkeypatch.setattr("dictapaste.llm.httpx.Client", _factory)

    refiner = LLMRefiner(LLMConfig(base_url="http://127.0.0.1:1234", timeout_sec=15))
    chunks = []

    result = refiner.refine_stream("hello", "Please fix: {transcript}", language="de", chunk_callback=chunks.append)

    assert result == "Refined text"
    assert chunks == ["Refined ", "text"]
    assert capture["method"] == "POST"
    assert capture["url"] == "http://127.0.0.1:1234/v1/chat/completions"
    assert capture["json"]["stream"] is True
    assert capture["json"]["messages"][1]["content"] == "Please fix: hello"


def test_refine_stream_filters_split_think_blocks(monkeypatch):
    capture = {}

    class _ThinkingClient(_FakeClient):
        def stream(self, method, url, json):
            self._capture["method"] = method
            self._capture["url"] = url
            self._capture["json"] = json
            return _FakeStreamResponse(
                [
                    'data: {"choices":[{"delta":{"content":"<thi"}}]}',
                    'data: {"choices":[{"delta":{"content":"nk>secret"}}]}',
                    'data: {"choices":[{"delta":{"content":" reasoning</think>Final"}}]}',
                    'data: {"choices":[{"delta":{"content":" text"}}]}',
                    "data: [DONE]",
                ]
            )

    def _factory(timeout):
        return _ThinkingClient(timeout, capture)

    monkeypatch.setattr("dictapaste.llm.httpx.Client", _factory)

    refiner = LLMRefiner(LLMConfig())

    assert refiner.refine_stream("hello", "Please fix: {transcript}") == "Final text"


def test_refine_stream_can_be_cancelled(monkeypatch):
    capture = {}

    def _factory(timeout):
        return _FakeClient(timeout, capture)

    monkeypatch.setattr("dictapaste.llm.httpx.Client", _factory)

    refiner = LLMRefiner(LLMConfig())
    refiner.cancel()

    with pytest.raises(LLMCancelled):
        refiner.refine_stream("hello", "Please fix: {transcript}")


def test_extract_text_handles_content_array():
    payload = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {"type": "text", "text": "World"},
                    ]
                }
            }
        ]
    }

    assert LLMRefiner._extract_text(payload) == "Hello World"


def test_extract_text_removes_prompt_echo():
    prompt = "Bereiniger nur den Text. Gib ausschließlich das Endergebnis aus.\nRaw transcript:\nDies ist ein Test."
    echoed = prompt + "\n\nDies ist ein weiterer Test."

    payload = {"choices": [{"message": {"content": echoed}}]}

    assert LLMRefiner._extract_text(payload, prompt=prompt, transcript="Dies ist ein Test.") == "Dies ist ein weiterer Test."


def test_extract_text_falls_back_to_transcript_on_exact_prompt_echo():
    transcript = "Dies ist ein Test. Ich möchte einfach mal sehen ob das ganze jetzt so funktioniert wie ich mir das vorstelle."
    prompt = (
        "Bereinige nur den Text.\n"
        "Gib ausschließlich das Endergebnis aus, ohne Erklärungen oder Denkprozess.\n"
        f"{transcript}"
    )
    payload = {"choices": [{"message": {"content": prompt}}]}

    assert LLMRefiner._extract_text(payload, prompt=prompt, transcript=transcript) == transcript


def test_extract_text_strips_result_label():
    payload = {"choices": [{"message": {"content": "Ergebnis: Das ist sauber."}}]}

    assert LLMRefiner._extract_text(payload) == "Das ist sauber."


def test_extract_text_removes_minimal_input_thinking_leak():
    noisy = """The input text is: "an."

This input is extremely minimal—just the word "an" followed by a period.

If I treat this literally as the final statement, cleaning it results in nothing more than what was given.

Let's stick to the most literal interpretation: Clean up "an." -> "an".an"""
    payload = {"choices": [{"message": {"content": noisy}}]}

    assert LLMRefiner._extract_text(payload, transcript="an.") == "an"


def test_extract_text_removes_meta_leakage_before_final_german_text():
    noisy = """The user wants me to clean up a dictated text according to several strict rules.

Original Text Analysis:
This section should not be visible.

This seems compact and retains all meaning while being grammatically correct German prose.Ich suche eine bessere Methode, den Thinking-Teil aus dem System zu entfernen, die nicht auf Regex basiert."""
    payload = {"choices": [{"message": {"content": noisy}}]}

    assert (
        LLMRefiner._extract_text(payload)
        == "Ich suche eine bessere Methode, den Thinking-Teil aus dem System zu entfernen, die nicht auf Regex basiert."
    )


def test_extract_text_removes_thinking_and_uses_final_choice():
    noisy = """The user wants me to clean up a dictated German text.

Analysis:
* Remove filler words.
* Correct punctuation.

Final choice: Ich möchte das Karetchen testen und sehen, wie gut es funktioniert.Ich möchte das Karetchen testen und sehen, wie gut es funktioniert."""
    payload = {"choices": [{"message": {"content": noisy}}]}

    assert LLMRefiner._extract_text(payload) == "Ich möchte das Karetchen testen und sehen, wie gut es funktioniert."


def test_extract_text_removes_think_block():
    payload = {"choices": [{"message": {"content": "<think>Analyse...</think>Bereinigter Text: Hallo Welt."}}]}

    assert LLMRefiner._extract_text(payload) == "Hallo Welt."


def test_extract_text_handles_final_choice_explanation_and_variant():
    noisy = (
        "Final choice based on minimal change and maximum cleanup: "
        "Das ist der nächste Test, wie gut sich das ganze Programm verhält, wenn ich sehr viel stottere."
        "Das ist der nächste Test, wie gut sich das gesamte Programm verhält, wenn ich stark stottere."
    )
    payload = {"choices": [{"message": {"content": noisy}}]}

    assert (
        LLMRefiner._extract_text(payload)
        == "Das ist der nächste Test, wie gut sich das gesamte Programm verhält, wenn ich stark stottere."
    )


def test_extract_text_removes_checklist_and_ready_sentence():
    noisy = """1. Removed fillers, repetitions, self-corrections. (Yes)
2. Corrected grammar/punctuation. (Yes)
3. Condensed without losing meaning. (Yes)
4. Treated as final statement. (Yes)
5. Output only the final text. (Will do)

The resulting German prose is ready.Das Popup für die Verbesserung oder Zusammenfassung der Übersetzung erscheint direkt am Mauszeiger."""
    payload = {"choices": [{"message": {"content": noisy}}]}

    assert (
        LLMRefiner._extract_text(payload)
        == "Das Popup für die Verbesserung oder Zusammenfassung der Übersetzung erscheint direkt am Mauszeiger."
    )


def test_ensure_reasoning_disabled_rejects_reasoning_tokens():
    payload = {
        "choices": [{"message": {"content": "Refined text"}}],
        "usage": {
            "completion_tokens_details": {
                "reasoning_tokens": 4,
            }
        },
    }

    with pytest.raises(LLMError, match="thinking tokens"):
        LLMRefiner._ensure_reasoning_disabled(payload)


def test_extract_text_strips_improved_prefix():
    for prefix in ("Improved: ", "improved: ", "Verbessert: ", "Verbesserter Text: "):
        payload = {"choices": [{"message": {"content": f"{prefix}Das ist der bereinigte Text."}}]}
        assert LLMRefiner._extract_text(payload) == "Das ist der bereinigte Text.", f"failed for prefix {prefix!r}"


def test_extract_text_raises_on_bad_shape():
    with pytest.raises(LLMError):
        LLMRefiner._extract_text({"nope": 1})
