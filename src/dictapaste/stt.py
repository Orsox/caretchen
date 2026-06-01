from __future__ import annotations

import threading
from collections.abc import Callable

import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.utils import download_model


_MIN_NORMALIZE_PEAK = 0.01
_TARGET_NORMALIZE_PEAK = 0.8


def _normalize_words(text: str) -> list[str]:
    return [word.casefold().strip(".,!?;:()[]{}\"'“”„‚‘’") for word in text.split() if word.strip()]


def merge_partial_transcripts(previous: str, new: str, max_overlap_words: int = 12) -> str:
    """Merge incremental STT text while removing duplicated overlap."""
    previous = " ".join(previous.split()).strip()
    new = " ".join(new.split()).strip()
    if not previous:
        return new
    if not new:
        return previous

    previous_words = previous.split()
    new_words = new.split()
    previous_norm = _normalize_words(previous)
    new_norm = _normalize_words(new)
    max_overlap = min(max_overlap_words, len(previous_norm), len(new_norm))

    for overlap in range(max_overlap, 0, -1):
        if previous_norm[-overlap:] == new_norm[:overlap]:
            return " ".join(previous_words + new_words[overlap:]).strip()

    if previous_norm == new_norm[: len(previous_norm)]:
        return new
    if new_norm == previous_norm[-len(new_norm) :]:
        return previous

    return f"{previous} {new}".strip()


class IncrementalTranscriptBuffer:
    """Stores and merges tentative chunk transcripts for experimental streaming STT."""

    def __init__(self, max_overlap_words: int = 12) -> None:
        self.max_overlap_words = max_overlap_words
        self._text = ""
        self._lock = threading.Lock()

    @property
    def text(self) -> str:
        with self._lock:
            return self._text

    def add(self, transcript: str) -> str:
        with self._lock:
            self._text = merge_partial_transcripts(self._text, transcript, self.max_overlap_words)
            return self._text

    def reset(self) -> None:
        with self._lock:
            self._text = ""


class WhisperTranscriber:
    """Whisper transcriber with optional download progress feedback."""

    def __init__(
        self,
        model_name: str = "medium",
        language: str = "auto",
        device: str = "cpu",
        compute_type: str = "int8",
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> None:
        self.model_name = model_name
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self._progress_callback = progress_callback

        self._lock = threading.Lock()
        self._model: WhisperModel | None = None
        self._downloading = False

    def _report_progress(self, message: str, percentage: float) -> None:
        if self._progress_callback:
            self._progress_callback(message, percentage)

    def _ensure_model(self) -> WhisperModel:
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is None:
                self._download_model_if_needed()
                self._model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )
        return self._model

    def _download_model_if_needed(self) -> None:
        """Download the Whisper model with progress reporting."""
        if self._downloading:
            return
        self._downloading = True

        try:
            self._report_progress(f"Loading Whisper model '{self.model_name}'...", 0)

            # Download with progress
            model_path = download_model(
                self.model_name,
                local_files_only=False,
            )

            self._report_progress(f"Loaded Whisper model '{self.model_name}'.", 100)
        except Exception as exc:
            self._report_progress(f"Whisper model error: {exc}", 0)
        finally:
            self._downloading = False

    def preload(self) -> None:
        """Load/download the Whisper model before the first dictation finishes."""
        self._ensure_model()

    def _prepare_waveform(self, audio: np.ndarray) -> np.ndarray:
        """Return a mono float32 waveform with light cleanup for dictation.

        Some microphones arrive with a DC offset or very low gain. Whisper is
        more robust when the signal is centered and speech peaks are not tiny,
        so we normalize quiet-but-nonempty recordings without clipping loud ones.
        """
        waveform = np.asarray(audio, dtype=np.float32).reshape(-1)
        if waveform.size == 0:
            return waveform

        finite_mask = np.isfinite(waveform)
        if not finite_mask.all():
            waveform = np.where(finite_mask, waveform, 0.0).astype(np.float32, copy=False)

        waveform = waveform - float(np.mean(waveform))
        peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
        if _MIN_NORMALIZE_PEAK <= peak < _TARGET_NORMALIZE_PEAK:
            waveform = waveform * (_TARGET_NORMALIZE_PEAK / peak)

        return np.clip(waveform, -1.0, 1.0).astype(np.float32, copy=False)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if audio.size == 0:
            return ""

        model = self._ensure_model()

        if sample_rate != 16000:
            raise ValueError(f"WhisperTranscriber expects 16 kHz audio, got {sample_rate} Hz")

        # Pass the waveform directly to faster-whisper. This avoids PyAV decoding
        # of a temporary WAV file, which can fail on localized systems while
        # formatting FFmpeg error messages (UnicodeDecodeError).
        waveform = self._prepare_waveform(audio)
        language = None if self.language in ("", "auto") else self.language
        segments, _ = model.transcribe(
            waveform,
            language=language,
            vad_filter=True,
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_parameters={"min_silence_duration_ms": 700},
        )
        text = " ".join(seg.text.strip() for seg in segments if seg.text and seg.text.strip())
        return text.strip()
