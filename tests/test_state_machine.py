import numpy as np

from dictapaste.app_state import AppState
from dictapaste.config import AppConfig
from dictapaste.llm import LLMError
from dictapaste.pipeline import DictationPipeline


class DummyRecorder:
    def __init__(self, audio_packet):
        self.audio_packet = audio_packet
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False
        return self.audio_packet


class DummyTranscriber:
    def __init__(self, text):
        self.text = text

    def transcribe(self, _audio, _sample_rate):
        return self.text


class DummyRefiner:
    def __init__(self, output=None, fail=False):
        self.output = output
        self.fail = fail
        self._cancelled = False

    def refine(self, transcript, prompt_template, language):
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


def test_pipeline_transitions_and_pastes_refined_text():
    audio = np.zeros(1600, dtype=np.float32)
    recorder = DummyRecorder((audio, 16000))
    transcriber = DummyTranscriber("raw transcript")
    refiner = DummyRefiner(output="refined transcript")

    states = []
    messages = []
    pasted = []

    pipeline = DictationPipeline(
        config=AppConfig(),
        prompt_template="{transcript}",
        state_callback=states.append,
        message_callback=messages.append,
        recorder=recorder,
        transcriber=transcriber,
        refiner=refiner,
        paste_func=pasted.append,
        async_processing=False,
    )

    pipeline.toggle_recording()
    assert pipeline.state == AppState.RECORDING

    pipeline.toggle_recording()

    assert pipeline.state == AppState.IDLE
    assert pasted == ["refined transcript"]
    assert AppState.TRANSCRIBING in states
    assert AppState.REFINING in states
    assert AppState.PASTING in states


def test_pipeline_falls_back_to_raw_when_llm_fails():
    audio = np.zeros(1600, dtype=np.float32)
    recorder = DummyRecorder((audio, 16000))
    transcriber = DummyTranscriber("raw transcript")
    refiner = DummyRefiner(fail=True)

    messages = []
    pasted = []

    pipeline = DictationPipeline(
        config=AppConfig(),
        prompt_template="{transcript}",
        message_callback=messages.append,
        recorder=recorder,
        transcriber=transcriber,
        refiner=refiner,
        paste_func=pasted.append,
        async_processing=False,
    )

    pipeline.toggle_recording()
    pipeline.toggle_recording()

    assert pasted == ["raw transcript"]
    assert any("using raw transcript" in msg.lower() for msg in messages)
