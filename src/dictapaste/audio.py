from __future__ import annotations

from collections.abc import Callable
import threading

import numpy as np
import sounddevice as sd


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        dtype: str = "float32",
        device_index: int = -1,
        level_callback: Callable[[float], None] | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.device_index = device_index
        self._level_callback = level_callback

        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self._last_status: str | None = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._stream is not None

    @property
    def last_status(self) -> str | None:
        return self._last_status

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                raise RuntimeError("Recorder is already running.")

            self._frames = []
            self._last_status = None
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                device=self.device_index if self.device_index >= 0 else None,
                callback=self._callback,
            )
            stream.start()
            self._stream = stream

    def stop(self) -> tuple[np.ndarray, int] | None:
        with self._lock:
            stream = self._stream
            self._stream = None

        if stream is None:
            return None

        stream.stop()
        stream.close()

        with self._lock:
            frames = self._frames
            self._frames = []

        return self._frames_to_packet(frames)

    def snapshot(self) -> tuple[np.ndarray, int] | None:
        """Return a copy of audio captured so far without stopping recording."""
        with self._lock:
            frames = [frame.copy() for frame in self._frames]

        return self._frames_to_packet(frames)

    def _frames_to_packet(self, frames: list[np.ndarray]) -> tuple[np.ndarray, int] | None:
        if not frames:
            return None

        audio = np.concatenate(frames, axis=0)

        if audio.ndim == 2 and audio.shape[1] > 1:
            audio = audio.mean(axis=1)
        else:
            audio = audio.reshape(-1)

        return audio.astype(np.float32), self.sample_rate

    def _callback(self, indata, _frames, _time_info, status) -> None:
        if status:
            self._last_status = str(status)

        frame = indata.copy()
        with self._lock:
            self._frames.append(frame)

        if self._level_callback is not None:
            try:
                level = float(np.sqrt(np.mean(np.square(frame, dtype=np.float32))))
                self._level_callback(max(0.0, min(1.0, level)))
            except Exception:
                pass


def enumerate_input_devices() -> list[tuple[int, str]]:
    """Return list of (index, name) for available input devices."""
    devices = sd.query_devices()
    result: list[tuple[int, str]] = []
    for i, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0:
            name = dev.get("name", f"Device {i}")
            result.append((i, name))
    if not result:
        result.append((-1, "Kein Eingabegerät gefunden"))
    return result
