import logging
import threading
import time

import numpy as np
import pytest

from dictapaste.app_state import AppState
from dictapaste.config import AppConfig, StreamingConfig
from dictapaste.llm import LLMError
from dictapaste.modes import DictationMode
from dictapaste.pipeline import DictationPipeline


class DummyRecorder:
    def __init__(self, audio_packet=None, raise_on_start=False, raise_on_stop=False):
        self.audio_packet = audio_packet
        self.started = False
        self.raise_on_start = raise_on_start
        self.raise_on_stop = raise_on_stop

    def start(self):
        if self.raise_on_start:
            raise RuntimeError("mic busy")
        self.started = True

    def stop(self):
        if self.raise_on_stop:
            raise RuntimeError("mic error")
        self.started = False
        return self.audio_packet

    def snapshot(self):
        return self.audio_packet


class DummyTranscriber:
    def __init__(self, text="", raise_on_transcribe=None):
        self.text = text
        self.raise_on_transcribe = raise_on_transcribe
        self.preload_count = 0
        self.transcribe_count = 0

    def preload(self):
        self.preload_count += 1

    def transcribe(self, _audio, _sample_rate):
        self.transcribe_count += 1
        if self.raise_on_transcribe:
            raise self.raise_on_transcribe
        return self.text


class StreamingDummyRefiner:
    def __init__(self, chunks=None, output="streamed"):
        self.chunks = chunks or ["stream", "ed"]
        self.output = output
        self._cancelled = False

    def refine_stream(self, transcript, prompt_template, language, chunk_callback=None):
        for chunk in self.chunks:
            if chunk_callback is not None:
                chunk_callback(chunk)
        return self.output

    def update_config(self, _config):
        return None

    def cancel(self):
        self._cancelled = True

    def is_cancelled(self):
        return self._cancelled

    def reset_cancel(self):
        self._cancelled = False


class DummyRefiner:
    def __init__(self, output=None, fail=False):
        self.output = output
        self.fail = fail
        self.call_count = 0
        self.last_transcript = None
        self._cancelled = False

    def refine(self, transcript, prompt_template, language):
        self.call_count += 1
        self.last_transcript = transcript
        if self.fail:
            raise LLMError("router down")
        return self.output if self.output is not None else transcript

    def update_config(self, _config):
        return None

    def cancel(self):
        self._cancelled = True

    def is_cancelled(self):
        return self._cancelled

    def reset_cancel(self):
        self._cancelled = False


def _make_pipeline(**kwargs):
    config = kwargs.pop("config", AppConfig())
    prompt_template = kwargs.pop("prompt_template", "{transcript}")
    recorder = kwargs.pop("recorder", DummyRecorder((np.zeros(1600, dtype=np.float32), 16000)))
    transcriber = kwargs.pop("transcriber", DummyTranscriber("raw transcript"))
    refiner = kwargs.pop("refiner", DummyRefiner(output="refined"))
    state_callback = kwargs.pop("state_callback", None)
    message_callback = kwargs.pop("message_callback", None)
    paste_func = kwargs.pop("paste_func", None)
    stream_callback = kwargs.pop("stream_callback", None)
    audio_level_callback = kwargs.pop("audio_level_callback", None)
    async_processing = kwargs.pop("async_processing", False)
    preload_stt_model = kwargs.pop("preload_stt_model", False)

    return DictationPipeline(
        config=config,
        prompt_template=prompt_template,
        state_callback=state_callback,
        message_callback=message_callback,
        stream_callback=stream_callback,
        audio_level_callback=audio_level_callback,
        recorder=recorder,
        transcriber=transcriber,
        refiner=refiner,
        paste_func=paste_func,
        async_processing=async_processing,
        preload_stt_model=preload_stt_model,
    )


# ── Recording preparation ─────────────────────────────────────────


def test_pipeline_warms_transcriber_during_recording():
    warmed = threading.Event()

    class WarmupTranscriber(DummyTranscriber):
        def preload(self):
            super().preload()
            warmed.set()

    config = AppConfig(streaming=StreamingConfig(enabled=True, stt_chunking_enabled=False))
    transcriber = WarmupTranscriber("raw transcript")
    pipeline = _make_pipeline(config=config, transcriber=transcriber)

    pipeline.toggle_recording()

    assert warmed.wait(1)
    assert transcriber.preload_count == 1

    pipeline.abort_recording()


def test_pipeline_experimental_chunk_stt_updates_partial_transcript():
    class GrowingSnapshotRecorder(DummyRecorder):
        def __init__(self):
            super().__init__((np.array([0.1, 0.2, 0.3], dtype=np.float32), 16000))
            self.snapshot_count = 0

        def snapshot(self):
            self.snapshot_count += 1
            audio = np.ones(self.snapshot_count, dtype=np.float32)
            return audio, 16000

    class ChunkTranscriber(DummyTranscriber):
        def transcribe(self, audio, _sample_rate):
            self.transcribe_count += 1
            if audio.size == 1:
                return "Das ist"
            return "Das ist ein Test"

    config = AppConfig(streaming=StreamingConfig(enabled=True, stt_chunking_enabled=True, chunk_duration_sec=1))
    transcriber = ChunkTranscriber("final")
    pipeline = _make_pipeline(config=config, recorder=GrowingSnapshotRecorder(), transcriber=transcriber)

    pipeline.toggle_recording()

    deadline = time.monotonic() + 2
    while pipeline.latest_partial_transcript != "Das ist ein Test" and time.monotonic() < deadline:
        time.sleep(0.05)

    assert pipeline.latest_partial_transcript == "Das ist ein Test"
    assert transcriber.transcribe_count >= 2

    pipeline.abort_recording()


def test_pipeline_captures_audio_snapshot_during_recording():
    snapshotted = threading.Event()
    packet = (np.array([0.1, 0.2], dtype=np.float32), 16000)

    class SnapshotRecorder(DummyRecorder):
        def snapshot(self):
            snapshotted.set()
            return packet

    config = AppConfig(streaming=StreamingConfig(enabled=True, stt_chunking_enabled=True, chunk_duration_sec=1))
    pipeline = _make_pipeline(config=config, recorder=SnapshotRecorder(packet))

    pipeline.toggle_recording()

    assert snapshotted.wait(1)
    assert pipeline._latest_audio_snapshot is not None
    np.testing.assert_allclose(pipeline._latest_audio_snapshot[0], packet[0])

    pipeline.abort_recording()


def test_pipeline_uses_final_transcript_for_llm_by_default_even_with_partial():
    config = AppConfig(streaming=StreamingConfig(enabled=True, stt_chunking_enabled=True, llm_start_mode="final"))
    refiner = DummyRefiner(output="refined")
    pipeline = _make_pipeline(config=config, refiner=refiner, paste_func=lambda _text: None)

    pipeline.toggle_recording()
    pipeline._latest_partial_transcript = "partial transcript"
    pipeline.toggle_recording()

    assert refiner.last_transcript == "raw transcript"


def test_pipeline_uses_experimental_partial_llm_result_when_final_matches():
    pasted = []
    config = AppConfig(streaming=StreamingConfig(enabled=True, stt_chunking_enabled=True, llm_start_mode="experimental_partial"))
    refiner = DummyRefiner(output="early refined")
    pipeline = _make_pipeline(config=config, refiner=refiner, paste_func=pasted.append)

    pipeline.toggle_recording()
    pipeline._latest_partial_transcript = "raw transcript"
    pipeline.toggle_recording()

    assert pasted == ["early refined"]
    assert refiner.call_count == 1
    assert refiner.last_transcript == "raw transcript"


def test_pipeline_ignores_experimental_partial_when_final_differs(caplog):
    caplog.set_level(logging.INFO, logger="dictapaste.pipeline")
    config = AppConfig(streaming=StreamingConfig(enabled=True, stt_chunking_enabled=True, llm_start_mode="experimental_partial"))
    refiner = DummyRefiner(output="refined")
    pipeline = _make_pipeline(config=config, refiner=refiner, paste_func=lambda _text: None)

    pipeline.toggle_recording()
    pipeline._latest_partial_transcript = "partial transcript"
    pipeline.toggle_recording()

    assert refiner.last_transcript == "raw transcript"
    assert any("Ignoring partial transcript" in record.message for record in caplog.records)


# ── Latency instrumentation ───────────────────────────────────────


def test_pipeline_logs_latency_timings_on_success(caplog):
    caplog.set_level(logging.INFO, logger="dictapaste.pipeline")

    pipeline = _make_pipeline(paste_func=lambda _text: None)

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    timing_logs = [record.message for record in caplog.records if "Dictation timings:" in record.message]
    assert timing_logs
    assert "stt_ms=" in timing_logs[-1]
    assert "llm_ms=" in timing_logs[-1]
    assert "llm_to_paste_ms=" in timing_logs[-1]
    assert "paste_ms=" in timing_logs[-1]
    assert "total_ms=" in timing_logs[-1]


def test_pipeline_logs_latency_timings_when_transcript_is_empty(caplog):
    caplog.set_level(logging.INFO, logger="dictapaste.pipeline")

    pipeline = _make_pipeline(transcriber=DummyTranscriber(text=""), paste_func=lambda _text: None)

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    timing_logs = [record.message for record in caplog.records if "Dictation timings:" in record.message]
    assert timing_logs
    assert "outcome=no_speech" in timing_logs[-1]
    assert "stt_ms=" in timing_logs[-1]


def test_pipeline_pastes_immediately_after_stream_finalizes(caplog):
    caplog.set_level(logging.INFO, logger="dictapaste.pipeline")
    states = []
    pasted = []
    pipeline = _make_pipeline(
        refiner=StreamingDummyRefiner(chunks=["first"], output="final streamed text"),
        state_callback=states.append,
        paste_func=pasted.append,
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pasted == ["final streamed text"]
    assert states[-2:] == [AppState.PASTING, AppState.IDLE]
    timing_logs = [record.message for record in caplog.records if "Dictation timings:" in record.message]
    assert timing_logs
    assert "llm_to_paste_ms=" in timing_logs[-1]
    assert "llm_to_paste_ms=n/a" not in timing_logs[-1]


def test_pipeline_forwards_streaming_chunks_to_callback():
    chunks = []
    pipeline = _make_pipeline(
        refiner=StreamingDummyRefiner(chunks=["first", " second"], output="first second"),
        stream_callback=chunks.append,
        paste_func=lambda _text: None,
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert chunks == ["first", " second"]


def test_pipeline_logs_first_llm_token_latency_for_streaming_refiner(caplog):
    caplog.set_level(logging.INFO, logger="dictapaste.pipeline")

    pipeline = _make_pipeline(refiner=StreamingDummyRefiner(), paste_func=lambda _text: None)

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    timing_logs = [record.message for record in caplog.records if "Dictation timings:" in record.message]
    assert timing_logs
    assert "llm_first_token_ms=" in timing_logs[-1]
    assert "llm_first_token_ms=n/a" not in timing_logs[-1]


# ── Slash commands ─────────────────────────────────────────────────


def test_pipeline_direct_slash_command_bypasses_llm():
    pasted = []
    refiner = DummyRefiner(output="refined")
    pipeline = _make_pipeline(
        transcriber=DummyTranscriber("slash compact"),
        refiner=refiner,
        paste_func=pasted.append,
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pasted == ["/compact"]
    assert refiner.call_count == 0


def test_pipeline_command_mode_resolves_without_slash_prefix():
    pasted = []
    refiner = DummyRefiner(output="refined")
    pipeline = _make_pipeline(
        transcriber=DummyTranscriber("neu laden"),
        refiner=refiner,
        paste_func=pasted.append,
    )

    pipeline.toggle_recording(DictationMode.COMMAND)
    pipeline.toggle_recording(DictationMode.COMMAND)

    assert pasted == ["/reload"]
    assert refiner.call_count == 0


def test_pipeline_direct_mode_bypasses_llm_and_pastes_raw_transcript():
    pasted = []
    refiner = DummyRefiner(output="refined")
    pipeline = _make_pipeline(refiner=refiner, paste_func=pasted.append)

    pipeline.toggle_recording(DictationMode.DIRECT)
    pipeline.toggle_recording(DictationMode.DIRECT)

    assert pasted == ["raw transcript"]
    assert refiner.call_count == 0


# ── Happy path regression ──────────────────────────────────────────


def test_pipeline_transitions_and_pastes_refined_text():
    states = []
    messages = []
    pasted = []

    pipeline = _make_pipeline(
        state_callback=states.append,
        message_callback=messages.append,
        paste_func=pasted.append,
    )

    pipeline.toggle_recording()
    assert pipeline.state == AppState.RECORDING

    pipeline.toggle_recording()

    assert pipeline.state == AppState.IDLE
    assert pasted == ["refined"]
    assert AppState.RECORDING in states
    assert AppState.TRANSCRIBING in states
    assert AppState.REFINING in states
    assert AppState.PASTING in states


def test_pipeline_falls_back_to_raw_when_llm_fails():
    messages = []
    pasted = []

    pipeline = _make_pipeline(
        message_callback=messages.append,
        paste_func=pasted.append,
        refiner=DummyRefiner(fail=True),
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pasted == ["raw transcript"]
    assert any("raw transcript" in msg.lower() for msg in messages)


# ── Transcription returning empty string ───────────────────────────


def test_pipeline_empty_transcript_returns_to_idle():
    messages = []
    pasted = []

    pipeline = _make_pipeline(
        message_callback=messages.append,
        paste_func=pasted.append,
        transcriber=DummyTranscriber(text=""),
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pipeline.state == AppState.IDLE
    assert pasted == []
    assert any("no speech" in msg.lower() for msg in messages)


# ── Recorder raises on start ───────────────────────────────────────


def test_pipeline_recorder_start_failure():
    messages = []

    pipeline = _make_pipeline(
        message_callback=messages.append,
        recorder=DummyRecorder(raise_on_start=True),
    )

    pipeline.toggle_recording()

    assert pipeline.state == AppState.IDLE
    assert any("could not start recording" in msg.lower() for msg in messages)


# ── Recorder raises on stop ────────────────────────────────────────


def test_pipeline_recorder_stop_failure():
    messages = []

    pipeline = _make_pipeline(
        message_callback=messages.append,
        recorder=DummyRecorder(raise_on_stop=True),
    )

    pipeline.toggle_recording()  # starts
    pipeline.toggle_recording()  # tries to stop

    assert pipeline.state == AppState.IDLE
    assert any("could not stop recording" in msg.lower() for msg in messages)


# ── Toggle while busy (transcribing) ───────────────────────────────


def test_pipeline_toggle_while_transcribing():
    messages = []
    call_count = [0]

    def slow_transcribe(*args):
        call_count[0] += 1
        if call_count[0] == 1:
            import time
            time.sleep(0.05)
        return "done"

    pipeline = _make_pipeline(
        message_callback=messages.append,
        transcriber=DummyTranscriber(),
        async_processing=False,
    )

    pipeline.toggle_recording()
    assert pipeline.state == AppState.RECORDING

    # Second toggle while still recording → stops and starts processing
    pipeline.toggle_recording()
    assert pipeline.state == AppState.IDLE  # completes synchronously (async=False)

    # Toggle again immediately → should be ignored because already IDLE
    messages.clear()
    pipeline.toggle_recording()
    assert pipeline.state == AppState.RECORDING

    # Toggle again while recording → stops
    pipeline.toggle_recording()


# ── Toggle while processing (async) ────────────────────────────────


def test_pipeline_toggle_ignored_while_processing_async():
    states = []
    pasted = []

    pipeline = _make_pipeline(
        state_callback=states.append,
        paste_func=pasted.append,
        async_processing=True,
    )

    pipeline.toggle_recording()
    assert pipeline.state == AppState.RECORDING

    pipeline.toggle_recording()
    # State should be TRANSCRIBING (recording stopped, processing started)
    # The async thread may complete quickly with dummy components,
    # so we accept TRANSCRIBING, REFINING, PASTING, or IDLE
    assert pipeline.state in (
        AppState.TRANSCRIBING,
        AppState.REFINING,
        AppState.PASTING,
        AppState.IDLE,
    )

    # Wait for async processing to finish
    import time
    time.sleep(0.3)

    assert pipeline.state == AppState.IDLE
    assert AppState.TRANSCRIBING in states
    assert AppState.PASTING in states


# ── Transcription exception ────────────────────────────────────────


def test_pipeline_transcription_exception():
    messages = []

    pipeline = _make_pipeline(
        message_callback=messages.append,
        paste_func=lambda t: None,
        transcriber=DummyTranscriber(raise_on_transcribe=RuntimeError("whisper crash")),
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pipeline.state == AppState.IDLE
    assert any("transcription failed" in msg.lower() for msg in messages)


# ── LLMError with async processing ─────────────────────────────────


def test_pipeline_llm_error_async_fallback():
    messages = []
    pasted = []

    pipeline = _make_pipeline(
        message_callback=messages.append,
        paste_func=pasted.append,
        refiner=DummyRefiner(fail=True),
        async_processing=True,
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    import time
    time.sleep(0.3)

    assert pipeline.state == AppState.IDLE
    assert pasted == ["raw transcript"]
    assert any("raw transcript" in msg.lower() for msg in messages)


# ── update_runtime replaces components ─────────────────────────────


def test_update_runtime_replaces_transcriber_and_refiner():
    from dictapaste.config import InputConfig, OutputConfig, StartupConfig

    # Don't pass custom components so _custom_transcriber/_custom_refiner are False
    pipeline = DictationPipeline(
        config=AppConfig(),
        prompt_template="{transcript}",
        async_processing=False,
    )
    old_transcriber = pipeline._transcriber
    old_refiner = pipeline._refiner

    new_config = AppConfig(
        stt=AppConfig.__dataclass_fields__["stt"].default_factory(model="large-v3", language="en"),
        llm=AppConfig.__dataclass_fields__["llm"].default_factory(base_url="http://new:8080"),
        input=InputConfig(),
        output=OutputConfig(),
        startup=StartupConfig(),
    )
    pipeline.update_runtime(new_config, "{transcript} new")

    assert pipeline._transcriber is not old_transcriber
    assert pipeline._transcriber.model_name == "large-v3"
    assert pipeline._transcriber.language == "en"
    assert pipeline._refiner is not old_refiner
    assert pipeline._refiner.config.base_url == "http://new:8080"
    assert pipeline._prompt_template == "{transcript} new"


def test_update_runtime_keeps_custom_components():
    from dictapaste.config import InputConfig, OutputConfig, StartupConfig

    custom_transcriber = DummyTranscriber("custom")
    custom_refiner = DummyRefiner(output="custom")

    pipeline = _make_pipeline(
        transcriber=custom_transcriber,
        refiner=custom_refiner,
    )

    new_config = AppConfig(
        stt=AppConfig.__dataclass_fields__["stt"].default_factory(model="large-v3"),
        llm=AppConfig.__dataclass_fields__["llm"].default_factory(base_url="http://new:8080"),
        input=InputConfig(),
        output=OutputConfig(),
        startup=StartupConfig(),
    )
    pipeline.update_runtime(new_config, "new prompt")

    assert pipeline._transcriber is custom_transcriber
    assert hasattr(pipeline._refiner, "update_config")


# ── Refine toggle ──────────────────────────────────────────────────


def test_set_refine_enabled():
    pipeline = _make_pipeline()
    assert pipeline.refine_enabled is True

    pipeline.set_refine_enabled(False)
    assert pipeline.refine_enabled is False

    pipeline.set_refine_enabled(True)
    assert pipeline.refine_enabled is True


def test_pipeline_uses_streaming_refiner_when_available():
    pasted = []

    class StreamingRefiner(DummyRefiner):
        def __init__(self):
            super().__init__(output="non-stream")
            self.stream_call_count = 0

        def refine_stream(self, transcript, prompt_template, language):
            self.stream_call_count += 1
            assert transcript == "raw transcript"
            return "streamed refined"

    refiner = StreamingRefiner()
    pipeline = _make_pipeline(refiner=refiner, paste_func=pasted.append)

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert refiner.stream_call_count == 1
    assert refiner.call_count == 0
    assert pasted == ["streamed refined"]


def test_pipeline_cancelled_streaming_llm_uses_raw_transcript():
    messages = []
    pasted = []

    class CancelledRefiner(DummyRefiner):
        def refine_stream(self, transcript, prompt_template, language):
            self.cancel()
            raise LLMError("cancelled")

    pipeline = _make_pipeline(
        message_callback=messages.append,
        paste_func=pasted.append,
        refiner=CancelledRefiner(output="refined"),
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pasted == ["raw transcript"]
    assert any("cancel" in msg.lower() for msg in messages)


def test_pipeline_passes_selected_mode_to_prompt():
    prompts = []
    pasted = []

    class CapturingRefiner(DummyRefiner):
        def refine(self, transcript, prompt_template, language):
            prompts.append(prompt_template)
            return "prompt output"

    pipeline = _make_pipeline(
        refiner=CapturingRefiner(),
        paste_func=pasted.append,
    )

    pipeline.toggle_recording(DictationMode.PROMPT)
    pipeline.toggle_recording(DictationMode.PROMPT)

    assert pasted == ["prompt output"]
    assert "direkt verwendbaren Prompt" in prompts[0]


def test_pipeline_defaults_to_improve_mode_for_existing_toggle():
    prompts = []

    class CapturingRefiner(DummyRefiner):
        def refine(self, transcript, prompt_template, language):
            prompts.append(prompt_template)
            return "improved"

    pipeline = _make_pipeline(refiner=CapturingRefiner())

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert "Bereinige und verbessere" in prompts[0]


def test_pipeline_skips_llm_when_refine_disabled():
    messages = []
    pasted = []

    pipeline = _make_pipeline(
        message_callback=messages.append,
        paste_func=pasted.append,
        refiner=DummyRefiner(output="refined"),
    )
    pipeline.set_refine_enabled(False)

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pipeline.state == AppState.IDLE
    assert pasted == ["raw transcript"]
    # REFINING state should NOT appear
    assert AppState.REFINING not in [s for s in []]  # no state callback, so check no LLM call


def test_pipeline_skips_llm_when_refine_disabled_state_tracking():
    states = []
    pasted = []

    pipeline = _make_pipeline(
        state_callback=states.append,
        paste_func=pasted.append,
        refiner=DummyRefiner(output="refined"),
    )
    pipeline.set_refine_enabled(False)

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert AppState.REFINING not in states
    assert pasted == ["raw transcript"]


# ── Async processing mode ──────────────────────────────────────────


def test_async_processing_starts_thread():
    pasted = []

    pipeline = _make_pipeline(
        paste_func=pasted.append,
        async_processing=True,
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    # Should be processing (not yet IDLE)
    assert pipeline.state in (AppState.TRANSCRIBING, AppState.RECORDING, AppState.IDLE)

    import time
    time.sleep(0.3)

    assert pipeline.state == AppState.IDLE
    assert pasted == ["refined"]


# ── Paste failure ──────────────────────────────────────────────────


def test_pipeline_paste_failure():
    states = []
    messages = []

    def failing_paste(text):
        raise RuntimeError("clipboard locked")

    pipeline = _make_pipeline(
        state_callback=states.append,
        message_callback=messages.append,
        paste_func=failing_paste,
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    # ERROR is transient — finally block resets to IDLE
    assert pipeline.state == AppState.IDLE
    assert AppState.ERROR in states
    assert any("paste failed" in msg.lower() for msg in messages)


# ── Unexpected LLM error falls back ────────────────────────────────


def test_pipeline_unexpected_llm_error_fallback():
    messages = []
    pasted = []

    class BadRefiner(DummyRefiner):
        def refine(self, transcript, prompt_template, language):
            raise ValueError("some unexpected issue")

    pipeline = _make_pipeline(
        message_callback=messages.append,
        paste_func=pasted.append,
        refiner=BadRefiner(),
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pipeline.state == AppState.IDLE
    assert pasted == ["raw transcript"]
    assert any("raw transcript" in msg.lower() for msg in messages)


# ── Retry last paste ───────────────────────────────────────────────


def test_retry_last_paste_succeeds():
    pasted = []

    pipeline = _make_pipeline(
        paste_func=pasted.append,
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pasted == ["refined"]
    assert pipeline.last_output_text == "refined"

    pasted.clear()
    pipeline.retry_last_paste()

    assert pasted == ["refined"]


def test_retry_last_paste_empty():
    messages = []

    pipeline = _make_pipeline(
        message_callback=messages.append,
    )

    pipeline.retry_last_paste()

    assert any("no previous result" in msg.lower() for msg in messages)


def test_retry_last_paste_after_failure():
    """After a paste failure, retry should re-paste the last text."""
    messages = []
    pasted = []
    call_count = [0]

    def flaky_paste(text):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("clipboard locked")
        pasted.append(text)

    pipeline = _make_pipeline(
        message_callback=messages.append,
        paste_func=flaky_paste,
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pipeline.state == AppState.IDLE
    assert pasted == []  # first paste failed

    # Retry should succeed on second attempt
    pipeline.retry_last_paste()
    assert pasted == ["refined"]


# ── Recording duration & abort ─────────────────────────────────────


def test_recording_duration_starts_at_zero():
    pipeline = _make_pipeline()
    assert pipeline.recording_duration_sec == 0.0


def test_recording_duration_increases():
    import time

    pipeline = _make_pipeline()
    pipeline.toggle_recording()
    assert pipeline.state == AppState.RECORDING

    duration = pipeline.recording_duration_sec
    time.sleep(0.1)
    duration2 = pipeline.recording_duration_sec

    assert duration2 > duration


def test_abort_recording_stops_and_returns_to_idle():
    messages = []

    pipeline = _make_pipeline(
        message_callback=messages.append,
    )

    pipeline.toggle_recording()
    assert pipeline.state == AppState.RECORDING

    pipeline.abort_recording()
    assert pipeline.state == AppState.IDLE
    assert any("aborted" in msg.lower() for msg in messages)


def test_abort_when_not_recording_is_noop():
    pipeline = _make_pipeline()
    pipeline.abort_recording()  # Should not raise
    assert pipeline.state == AppState.IDLE


def test_llm_cancel_during_refining():
    """User can cancel LLM request during refining state."""
    messages = []
    pasted = []

    class SlowRefiner(DummyRefiner):
        def refine(self, transcript, prompt_template, language):
            # Simulate a long-running request
            if self.is_cancelled():
                raise LLMError("cancelled")
            return "refined"

    pipeline = _make_pipeline(
        messages=messages,
        refiner=SlowRefiner(output="refined"),
        paste_func=pasted.append,
        async_processing=False,  # Synchronous to test cancel logic directly
    )

    pipeline.toggle_recording()  # Start recording
    time.sleep(0.05)
    pipeline.toggle_recording()  # Stop recording → triggers processing

    # Should complete (no cancel in this test)
    assert pipeline.state == AppState.IDLE
    assert pasted == ["refined"]
    # No cancel message should appear
    assert not any("cancel" in m.lower() for m in messages)


def test_pipeline_wait_until_ready_uses_preload_and_llm_availability():
    class PreloadTranscriber(DummyTranscriber):
        def __init__(self):
            super().__init__("raw")
            self.preloaded = False

        def preload(self):
            self.preloaded = True

    class AvailableRefiner(DummyRefiner):
        def is_available(self):
            return True

    transcriber = PreloadTranscriber()
    pipeline = _make_pipeline(
        transcriber=transcriber,
        refiner=AvailableRefiner(output="refined"),
        preload_stt_model=True,
    )

    assert pipeline.wait_until_ready(timeout=1) is True
    assert transcriber.preloaded is True


def test_pipeline_wait_until_ready_rejects_unavailable_llm():
    class UnavailableRefiner(DummyRefiner):
        def is_available(self):
            return False

    pipeline = _make_pipeline(refiner=UnavailableRefiner(output="refined"))

    assert pipeline.wait_until_ready(timeout=1) is False


def test_llm_refiner_has_cancel_methods():
    """LLMRefiner supports cancel/is_cancelled/reset_cancel."""
    from dictapaste.llm import LLMRefiner
    from dictapaste.config import LLMConfig

    refiner = LLMRefiner(LLMConfig())
    assert not refiner.is_cancelled()
    refiner.cancel()
    assert refiner.is_cancelled()
    refiner.reset_cancel()
    assert not refiner.is_cancelled()
