import numpy as np

from dictapaste.audio import AudioRecorder


class _FakeStream:
    def __init__(self):
        self.stopped = False
        self.closed = False

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


def test_callback_reports_clamped_audio_level():
    levels = []
    recorder = AudioRecorder(level_callback=levels.append)

    recorder._callback(np.array([[0.5], [0.5]], dtype=np.float32), None, None, None)

    assert levels
    assert 0.49 <= levels[-1] <= 0.51


def test_callback_ignores_level_callback_errors():
    recorder = AudioRecorder(level_callback=lambda _level: (_ for _ in ()).throw(RuntimeError("boom")))

    recorder._callback(np.array([[0.5]], dtype=np.float32), None, None, None)

    assert len(recorder._frames) == 1


def test_snapshot_returns_copy_without_stopping_or_clearing_frames():
    recorder = AudioRecorder(sample_rate=16000, channels=1)
    stream = _FakeStream()
    recorder._stream = stream

    frame = np.array([[0.1], [0.2]], dtype=np.float32)
    recorder._callback(frame, None, None, None)

    snapshot = recorder.snapshot()

    assert snapshot is not None
    audio, sample_rate = snapshot
    assert sample_rate == 16000
    np.testing.assert_allclose(audio, np.array([0.1, 0.2], dtype=np.float32))
    assert recorder.is_recording is True
    assert stream.stopped is False
    assert len(recorder._frames) == 1

    audio[0] = 9.0
    second_snapshot = recorder.snapshot()
    assert second_snapshot is not None
    np.testing.assert_allclose(second_snapshot[0], np.array([0.1, 0.2], dtype=np.float32))


def test_snapshot_mixes_multichannel_audio_to_mono():
    recorder = AudioRecorder(sample_rate=8000, channels=2)
    recorder._stream = _FakeStream()
    recorder._callback(np.array([[0.0, 1.0], [0.5, 1.0]], dtype=np.float32), None, None, None)

    snapshot = recorder.snapshot()

    assert snapshot is not None
    audio, sample_rate = snapshot
    assert sample_rate == 8000
    np.testing.assert_allclose(audio, np.array([0.5, 0.75], dtype=np.float32))


def test_snapshot_returns_none_without_frames():
    recorder = AudioRecorder()

    assert recorder.snapshot() is None


def test_stop_still_returns_audio_and_clears_frames():
    recorder = AudioRecorder(sample_rate=16000, channels=1)
    stream = _FakeStream()
    recorder._stream = stream
    recorder._callback(np.array([[0.3], [0.4]], dtype=np.float32), None, None, None)

    packet = recorder.stop()

    assert packet is not None
    audio, sample_rate = packet
    assert sample_rate == 16000
    np.testing.assert_allclose(audio, np.array([0.3, 0.4], dtype=np.float32))
    assert stream.stopped is True
    assert stream.closed is True
    assert recorder.snapshot() is None
