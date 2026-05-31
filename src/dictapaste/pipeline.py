from __future__ import annotations

from collections.abc import Callable
import inspect
import logging
import threading
import time

import numpy as np

from .app_state import AppState
from .audio import AudioRecorder, enumerate_input_devices
from .commands import resolve_slash_command
from .config import AppConfig
from .history import DictationHistory
from .i18n import tr
from .llm import LLMCancelled, LLMError, LLMRefiner
from .modes import DictationMode, build_mode_prompt, coerce_mode
from .paste import PasteMode, paste_text
from .stt import IncrementalTranscriptBuffer, WhisperTranscriber


logger = logging.getLogger(__name__)


class DictationPipeline:
    def __init__(
        self,
        config: AppConfig,
        prompt_template: str,
        state_callback: Callable[[AppState], None] | None = None,
        message_callback: Callable[[str], None] | None = None,
        notification_callback: Callable[[str], None] | None = None,
        stream_callback: Callable[[str], None] | None = None,
        audio_level_callback: Callable[[float], None] | None = None,
        recorder: AudioRecorder | None = None,
        transcriber: WhisperTranscriber | None = None,
        refiner: LLMRefiner | None = None,
        paste_func: Callable[[str], None] | None = None,
        async_processing: bool = True,
        history: DictationHistory | None = None,
        preload_stt_model: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self._state = AppState.IDLE

        self._config = config
        self._prompt_template = prompt_template
        self._refine_enabled = config.llm.enabled_by_default

        self._state_callback = state_callback
        self._message_callback = message_callback
        self._notification_callback = notification_callback
        self._stream_callback = stream_callback
        self._audio_level_callback = audio_level_callback

        self._recorder = recorder or AudioRecorder(
            device_index=config.audio.device_index,
            level_callback=audio_level_callback,
        )
        self._transcriber = transcriber or WhisperTranscriber(
            model_name=config.stt.model,
            language=config.stt.language,
            progress_callback=self._on_stt_progress,
        )
        self._refiner = refiner or LLMRefiner(config.llm)
        self._paste_func = paste_func or (lambda text: paste_text(text, mode=self._config.output.paste_mode))

        self._custom_transcriber = transcriber is not None
        self._custom_refiner = refiner is not None
        self._async_processing = async_processing
        self._preload_stt_model = preload_stt_model
        self._preload_done = threading.Event()
        self._preload_error: Exception | None = None
        self._recording_prepare_stop = threading.Event()
        self._recording_prepare_thread: threading.Thread | None = None
        self._latest_audio_snapshot: tuple[np.ndarray, int] | None = None
        self._partial_transcript_buffer = IncrementalTranscriptBuffer()
        self._latest_partial_transcript = ""
        self._stt_call_lock = threading.Lock()
        if preload_stt_model:
            self._preload_transcriber()
        else:
            self._preload_done.set()

        # Last output for retry
        self._last_output_text: str = ""
        self._recording_start_time: float = 0.0
        self._current_mode = DictationMode.IMPROVE

        self._history = history

    @property
    def state(self) -> AppState:
        with self._lock:
            return self._state

    @property
    def refine_enabled(self) -> bool:
        with self._lock:
            return self._refine_enabled

    @property
    def last_output_text(self) -> str:
        with self._lock:
            return self._last_output_text

    @property
    def recording_duration_sec(self) -> float:
        """Seconds since recording started, 0 if not recording."""
        with self._lock:
            if self._recording_start_time > 0:
                return time.monotonic() - self._recording_start_time
            return 0.0

    def set_refine_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._refine_enabled = bool(enabled)

    def update_runtime(self, config: AppConfig, prompt_template: str) -> None:
        with self._lock:
            self._config = config
            self._prompt_template = prompt_template
            self._refine_enabled = config.llm.enabled_by_default

            if not self._custom_transcriber:
                self._transcriber = WhisperTranscriber(
                    model_name=config.stt.model,
                    language=config.stt.language,
                    progress_callback=self._on_stt_progress,
                )

            if not self._custom_transcriber:
                self._recorder = AudioRecorder(
                    device_index=config.audio.device_index,
                    level_callback=self._audio_level_callback,
                )

            if not self._custom_refiner:
                self._refiner = LLMRefiner(config.llm)
            elif hasattr(self._refiner, "update_config"):
                self._refiner.update_config(config.llm)

            if self._preload_stt_model:
                self._preload_done.clear()
                self._preload_error = None
                self._preload_transcriber()
            else:
                self._preload_done.set()

            self._recording_prepare_stop.set()
            self._latest_audio_snapshot = None
            self._latest_partial_transcript = ""
            self._partial_transcript_buffer.reset()

    @property
    def latest_partial_transcript(self) -> str:
        with self._lock:
            return self._latest_partial_transcript

    def toggle_recording(self, mode: DictationMode | str | None = None) -> None:
        current = self.state

        if current == AppState.IDLE:
            self._start_recording(mode=mode)
            return

        if current == AppState.RECORDING:
            self._stop_and_process(mode=mode)
            return

        self._notify(tr("pipeline_busy"))

    def abort_recording(self) -> None:
        """Abort current recording and discard captured audio."""
        if self.state != AppState.RECORDING:
            return

        self._recording_prepare_stop.set()

        try:
            self._recorder.stop()
        except Exception:
            pass

        with self._lock:
            self._recording_start_time = 0.0

        self._notify(tr("pipeline_recording_aborted"))
        self._set_state(AppState.IDLE)

    def retry_last_paste(self) -> None:
        """Retry pasting the last output text."""
        text = self.last_output_text
        if not text:
            self._notify(tr("pipeline_retry_no_result"))
            return

        try:
            self._paste_func(text)
            self._notify(tr("pipeline_pasted"))
        except Exception as exc:
            self._notify(tr("pipeline_retry_failed") + str(exc))
            self._set_state(AppState.ERROR)
            self._set_state(AppState.IDLE)

    def wait_until_ready(self, timeout: float | None = None) -> bool:
        if not self._preload_done.wait(timeout):
            return False
        if self._preload_error is not None:
            return False
        if self._config.llm.enabled_by_default:
            available = getattr(self._refiner, "is_available", None)
            if available is not None and not available():
                return False
        return True

    def _preload_transcriber(self) -> None:
        preload = getattr(self._transcriber, "preload", None)
        if preload is None:
            self._preload_done.set()
            return

        def _run_preload() -> None:
            try:
                preload()
            except Exception as exc:
                self._preload_error = exc
            finally:
                self._preload_done.set()

        worker = threading.Thread(target=_run_preload, daemon=True)
        worker.start()

    def _start_recording_preparation(self) -> None:
        if not self._config.streaming.enabled:
            return

        self._recording_prepare_stop.set()
        self._recording_prepare_stop = threading.Event()

        def _prepare() -> None:
            preload = getattr(self._transcriber, "preload", None)
            if preload is not None:
                try:
                    preload()
                except Exception as exc:
                    logger.warning("Recording STT warmup failed: %s", exc)

            if not self._config.streaming.stt_chunking_enabled:
                return

            snapshot = getattr(self._recorder, "snapshot", None)
            if snapshot is None:
                return

            interval = max(0.1, float(self._config.streaming.chunk_duration_sec))
            last_sample_count = 0
            while not self._recording_prepare_stop.is_set():
                try:
                    packet = snapshot()
                    if packet is not None:
                        audio, sample_rate = packet
                        with self._lock:
                            self._latest_audio_snapshot = packet
                        if audio.size > last_sample_count:
                            last_sample_count = audio.size
                            with self._stt_call_lock:
                                partial = self._transcriber.transcribe(audio, sample_rate).strip()
                            if partial:
                                merged = self._partial_transcript_buffer.add(partial)
                                with self._lock:
                                    self._latest_partial_transcript = merged
                except Exception as exc:
                    logger.warning("Recording audio snapshot/transcription failed: %s", exc)
                    return
                self._recording_prepare_stop.wait(interval)

        self._recording_prepare_thread = threading.Thread(target=_prepare, daemon=True)
        self._recording_prepare_thread.start()

    def _start_recording(self, mode: DictationMode | str | None = None) -> None:
        try:
            with self._lock:
                self._current_mode = coerce_mode(mode)
            self._recorder.start()
            with self._lock:
                self._recording_start_time = time.monotonic()
                self._latest_audio_snapshot = None
                self._latest_partial_transcript = ""
                self._partial_transcript_buffer.reset()
            self._start_recording_preparation()
            self._set_state(AppState.RECORDING)
            self._notify(tr("pipeline_recording_started"))
        except Exception as exc:
            self._notify(tr("pipeline_recording_start_error") + str(exc))
            self._set_state(AppState.ERROR)
            self._set_state(AppState.IDLE)

    def _stop_and_process(self, mode: DictationMode | str | None = None) -> None:
        with self._lock:
            if mode is not None:
                self._current_mode = coerce_mode(mode)
            processing_mode = self._current_mode

        self._recording_prepare_stop.set()

        try:
            audio_packet = self._recorder.stop()
        except Exception as exc:
            self._notify(tr("pipeline_recording_stop_error") + str(exc))
            self._set_state(AppState.ERROR)
            self._set_state(AppState.IDLE)
            return

        if audio_packet is None:
            self._notify(tr("pipeline_no_audio"))
            self._set_state(AppState.IDLE)
            return

        recording_stopped_at = time.monotonic()
        self._set_state(AppState.TRANSCRIBING)

        if self._async_processing:
            worker = threading.Thread(
                target=self._process_audio,
                args=(audio_packet, processing_mode, recording_stopped_at),
                daemon=True,
            )
            worker.start()
        else:
            self._process_audio(audio_packet, processing_mode, recording_stopped_at)

    def _process_audio(
        self,
        audio_packet: tuple[np.ndarray, int],
        mode: DictationMode = DictationMode.IMPROVE,
        recording_stopped_at: float | None = None,
    ) -> None:
        audio, sample_rate = audio_packet
        total_started_at = recording_stopped_at or time.monotonic()
        stt_started_at = time.monotonic()
        stt_finished_at: float | None = None
        llm_started_at: float | None = None
        llm_first_token_at: float | None = None
        llm_finished_at: float | None = None
        paste_started_at: float | None = None
        paste_finished_at: float | None = None
        paste_succeeded = False
        early_llm = self._start_early_partial_refinement(mode) if self.refine_enabled else None

        def _handle_llm_chunk(chunk: str) -> None:
            nonlocal llm_first_token_at
            if llm_first_token_at is None:
                llm_first_token_at = time.monotonic()
            if self._stream_callback is not None:
                self._stream_callback(chunk)

        try:
            with self._stt_call_lock:
                transcript = self._transcriber.transcribe(audio, sample_rate).strip()
            stt_finished_at = time.monotonic()
        except Exception as exc:
            stt_finished_at = time.monotonic()
            self._log_timings(
                outcome="stt_error",
                total_started_at=total_started_at,
                stt_started_at=stt_started_at,
                stt_finished_at=stt_finished_at,
            )
            self._notify(tr("pipeline_transcription_failed") + str(exc))
            self._set_state(AppState.ERROR)
            self._set_state(AppState.IDLE)
            return

        if not transcript:
            self._notify(tr("pipeline_no_speech"))
            self._log_timings(
                outcome="no_speech",
                total_started_at=total_started_at,
                stt_started_at=stt_started_at,
                stt_finished_at=stt_finished_at,
            )
            self._set_state(AppState.IDLE)
            return

        command_text = resolve_slash_command(transcript, force=(mode == DictationMode.COMMAND))
        output_text = command_text or transcript
        refinement_transcript = self._select_refinement_transcript(transcript)

        if self.refine_enabled and command_text is None and mode != DictationMode.DIRECT:
            self._set_state(AppState.REFINING)
            self._notify(tr("pipeline_contacting_llm"))
            cancelled = False
            try:
                early_result = self._consume_early_partial_refinement(early_llm, transcript)
                if early_result is not None:
                    output_text = early_result["text"]
                    llm_started_at = early_result["started_at"]
                    llm_first_token_at = early_result["first_token_at"]
                    llm_finished_at = early_result["finished_at"]
                else:
                    llm_started_at = time.monotonic()
                    output_text = self._run_refinement(
                        self._refiner,
                        transcript=refinement_transcript,
                        mode=mode,
                        chunk_callback=_handle_llm_chunk,
                    )
                    llm_finished_at = time.monotonic()
            except LLMCancelled:
                llm_finished_at = time.monotonic()
                cancelled = True
                output_text = transcript
            except (LLMError, ValueError) as exc:
                llm_finished_at = time.monotonic()
                self._notify(tr("pipeline_llm_unavailable") + str(exc) + ")")
                output_text = transcript
            except Exception as exc:
                llm_finished_at = time.monotonic()
                self._notify(tr("pipeline_llm_error") + str(exc) + ")")
                output_text = transcript
            finally:
                if self._refiner.is_cancelled():
                    cancelled = True
                    output_text = transcript
                self._refiner.reset_cancel()
                if cancelled:
                    self._notify(tr("pipeline_llm_cancelled"))

        self._set_state(AppState.PASTING)

        try:
            paste_started_at = time.monotonic()
            self._paste_func(output_text)
            paste_finished_at = time.monotonic()
            paste_succeeded = True
            self._notify("Dictation pasted.")

            # Record to history
            if self._history is not None:
                self._history.add(
                    raw_text=transcript,
                    refined_text=output_text,
                    was_refined=(output_text != transcript),
                )

            # Show post-paste notification
            if self._notification_callback is not None:
                preview = output_text[:100] + ("..." if len(output_text) > 100 else "")
                self._notification_callback(preview)
        except Exception as exc:
            paste_finished_at = time.monotonic()
            self._notify(tr("pipeline_paste_failed") + str(exc))
            self._set_state(AppState.ERROR)
        finally:
            self._log_timings(
                outcome="pasted" if paste_succeeded else "paste_error",
                total_started_at=total_started_at,
                stt_started_at=stt_started_at,
                stt_finished_at=stt_finished_at,
                llm_started_at=llm_started_at,
                llm_first_token_at=llm_first_token_at,
                llm_finished_at=llm_finished_at,
                paste_started_at=paste_started_at,
                paste_finished_at=paste_finished_at,
            )
            with self._lock:
                self._last_output_text = output_text
            self._set_state(AppState.IDLE)

    def _run_refinement(
        self,
        refiner,
        *,
        transcript: str,
        mode: DictationMode,
        chunk_callback: Callable[[str], None] | None = None,
    ) -> str:
        prompt_template = build_mode_prompt(self._prompt_template, mode)
        if hasattr(refiner, "refine_stream"):
            refine_stream = refiner.refine_stream
            stream_kwargs = {
                "transcript": transcript,
                "prompt_template": prompt_template,
                "language": self._config.stt.language,
            }
            if chunk_callback is not None and "chunk_callback" in inspect.signature(refine_stream).parameters:
                stream_kwargs["chunk_callback"] = chunk_callback
            return refine_stream(**stream_kwargs)

        return refiner.refine(
            transcript=transcript,
            prompt_template=prompt_template,
            language=self._config.stt.language,
        )

    def _early_partial_candidate(self) -> str:
        if self._config.streaming.llm_start_mode != "experimental_partial":
            return ""
        with self._lock:
            return self._latest_partial_transcript.strip()

    def _start_early_partial_refinement(self, mode: DictationMode) -> dict | None:
        partial = self._early_partial_candidate()
        if not partial:
            return None

        result: dict = {
            "partial": partial,
            "text": None,
            "error": None,
            "started_at": None,
            "first_token_at": None,
            "finished_at": None,
        }

        def _mark_first_token(_chunk: str) -> None:
            if result["first_token_at"] is None:
                result["first_token_at"] = time.monotonic()
            if self._stream_callback is not None:
                self._stream_callback(_chunk)

        def _run() -> None:
            refiner = self._refiner if self._custom_refiner else LLMRefiner(self._config.llm)
            try:
                result["started_at"] = time.monotonic()
                result["text"] = self._run_refinement(
                    refiner,
                    transcript=partial,
                    mode=mode,
                    chunk_callback=_mark_first_token,
                )
            except Exception as exc:  # stored and handled after final STT validation
                result["error"] = exc
            finally:
                result["finished_at"] = time.monotonic()
                reset = getattr(refiner, "reset_cancel", None)
                if reset is not None:
                    reset()

        thread = threading.Thread(target=_run, daemon=True)
        result["thread"] = thread
        thread.start()
        logger.info("Started experimental partial LLM refinement.")
        return result

    def _consume_early_partial_refinement(self, early_llm: dict | None, final_transcript: str) -> dict | None:
        if early_llm is None:
            return None

        if early_llm["partial"] != final_transcript.strip():
            logger.info("Ignoring early partial LLM result because final STT differs.")
            return None

        early_llm["thread"].join()
        if early_llm.get("error") is not None:
            logger.info("Ignoring early partial LLM result because it failed: %s", early_llm["error"])
            return None

        text = early_llm.get("text")
        if not text:
            return None

        logger.info("Using experimental partial LLM result after final STT matched.")
        return early_llm

    def _select_refinement_transcript(self, final_transcript: str) -> str:
        if self._config.streaming.llm_start_mode != "experimental_partial":
            return final_transcript

        with self._lock:
            partial = self._latest_partial_transcript.strip()

        if partial and partial == final_transcript.strip():
            return partial

        if partial:
            logger.info("Ignoring partial transcript for LLM because final STT differs.")
        return final_transcript

    @staticmethod
    def _elapsed_ms(started_at: float | None, finished_at: float | None) -> str:
        if started_at is None or finished_at is None:
            return "n/a"
        return str(max(0, int(round((finished_at - started_at) * 1000))))

    def _log_timings(
        self,
        *,
        outcome: str,
        total_started_at: float,
        stt_started_at: float | None = None,
        stt_finished_at: float | None = None,
        llm_started_at: float | None = None,
        llm_first_token_at: float | None = None,
        llm_finished_at: float | None = None,
        paste_started_at: float | None = None,
        paste_finished_at: float | None = None,
    ) -> None:
        finished_at = paste_finished_at or llm_finished_at or stt_finished_at or time.monotonic()
        logger.info(
            "Dictation timings: outcome=%s stt_ms=%s llm_first_token_ms=%s llm_ms=%s llm_to_paste_ms=%s paste_ms=%s total_ms=%s",
            outcome,
            self._elapsed_ms(stt_started_at, stt_finished_at),
            self._elapsed_ms(llm_started_at, llm_first_token_at),
            self._elapsed_ms(llm_started_at, llm_finished_at),
            self._elapsed_ms(llm_finished_at, paste_started_at),
            self._elapsed_ms(paste_started_at, paste_finished_at),
            self._elapsed_ms(total_started_at, finished_at),
        )

    def _set_state(self, state: AppState) -> None:
        with self._lock:
            self._state = state

        if self._state_callback:
            self._state_callback(state)

    def _notify(self, message: str) -> None:
        if self._message_callback:
            self._message_callback(message)

    def _on_stt_progress(self, message: str, percentage: float) -> None:
        """Forward Whisper model load progress to the message callback."""
        if self._message_callback:
            self._message_callback(message)
