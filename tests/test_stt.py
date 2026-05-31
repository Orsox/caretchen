from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from dictapaste.stt import IncrementalTranscriptBuffer, WhisperTranscriber, merge_partial_transcripts


class TestIncrementalTranscriptMerge:
    def test_merge_partial_transcripts_removes_overlap(self) -> None:
        result = merge_partial_transcripts(
            "Das ist ein kurzer Test",
            "kurzer Test mit Streaming",
        )

        assert result == "Das ist ein kurzer Test mit Streaming"

    def test_merge_partial_transcripts_preserves_distinct_text(self) -> None:
        result = merge_partial_transcripts(
            "Das ist der erste Satz.",
            "Hier beginnt der zweite Satz.",
        )

        assert result == "Das ist der erste Satz. Hier beginnt der zweite Satz."

    def test_merge_partial_transcripts_handles_replacement_prefix(self) -> None:
        result = merge_partial_transcripts(
            "Das ist",
            "Das ist ein vollständiger Satz.",
        )

        assert result == "Das ist ein vollständiger Satz."

    def test_merge_partial_transcripts_ignores_case_and_punctuation_in_overlap(self) -> None:
        result = merge_partial_transcripts(
            "Hello, world!",
            "World this continues.",
        )

        assert result == "Hello, world! this continues."

    def test_incremental_transcript_buffer_accumulates_chunks(self) -> None:
        buffer = IncrementalTranscriptBuffer()

        assert buffer.add("Das ist ein Test") == "Das ist ein Test"
        assert buffer.add("ein Test mit Chunks") == "Das ist ein Test mit Chunks"
        assert buffer.text == "Das ist ein Test mit Chunks"
        buffer.reset()
        assert buffer.text == ""


class TestWhisperProgress:
    """Tests for WhisperTranscriber progress callback."""

    def test_progress_callback_receives_load_message(self) -> None:
        """Progress callback is called with a message during model load."""
        callback = MagicMock()
        transcriber = WhisperTranscriber(
            model_name="tiny",
            progress_callback=callback,
        )
        # Call the download method directly (mock WhisperModel so it doesn't actually load)
        with patch("dictapaste.stt.WhisperModel"):
            transcriber._download_model_if_needed()
        calls = [c[0][0] for c in callback.call_args_list]
        assert any("Loading" in msg or "Loaded" in msg for msg in calls)

    def test_progress_callback_receives_percentage(self) -> None:
        """Progress callback receives percentage values."""
        callback = MagicMock()
        transcriber = WhisperTranscriber(
            model_name="tiny",
            progress_callback=callback,
        )
        with patch("dictapaste.stt.WhisperModel"):
            transcriber._download_model_if_needed()
        percentages = [c[0][1] for c in callback.call_args_list]
        assert any(0 <= p <= 100 for p in percentages)

    def test_no_callback_does_not_crash(self) -> None:
        """Transcriber works without a progress callback."""
        transcriber = WhisperTranscriber(model_name="tiny")
        with patch("dictapaste.stt.WhisperModel"):
            model = transcriber._ensure_model()
        assert model is not None

    def test_progress_callback_with_none_audio(self) -> None:
        """Empty audio returns empty string regardless of progress callback."""
        callback = MagicMock()
        transcriber = WhisperTranscriber(
            model_name="tiny",
            progress_callback=callback,
        )
        result = transcriber.transcribe(np.array([], dtype=np.float32), 16000)
        assert result == ""
        # No model loading should happen for empty audio
        callback.assert_not_called()

    def test_download_model_if_needed_is_idempotent(self) -> None:
        """_download_model_if_needed guard prevents re-entry during concurrent calls."""
        import threading
        callback = MagicMock()
        transcriber = WhisperTranscriber(
            model_name="tiny",
            progress_callback=callback,
        )
        call_count = 0
        barrier = threading.Barrier(2)

        def _slow_download(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            barrier.wait()  # Block both threads here
            return "/fake/path"

        with patch("dictapaste.stt.download_model", side_effect=_slow_download):
            results = []
            def _call():
                try:
                    transcriber._download_model_if_needed()
                except Exception as exc:
                    results.append(exc)

            t1 = threading.Thread(target=_call)
            t2 = threading.Thread(target=_call)
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)
            # Only one thread should have actually called download_model
            assert call_count == 1, f"Expected 1 download call, got {call_count}"
            assert len(results) == 0, f"Unexpected errors: {results}"

    def test_download_model_error_reports_via_callback(self) -> None:
        """If download fails, error is reported via callback."""
        callback = MagicMock()
        transcriber = WhisperTranscriber(
            model_name="nonexistent-model-xyz",
            progress_callback=callback,
        )
        with patch("dictapaste.stt.download_model", side_effect=Exception("Model not found")):
            transcriber._download_model_if_needed()
        calls = [c[0][0] for c in callback.call_args_list]
        assert any("error" in msg.lower() or "not found" in msg.lower() for msg in calls)

    def test_progress_callback_none_message(self) -> None:
        """Callback with None message doesn't crash."""
        callback = MagicMock()
        transcriber = WhisperTranscriber(
            model_name="tiny",
            progress_callback=callback,
        )
        transcriber._report_progress(None, 50.0)
        # Should not raise

    def test_progress_callback_zero_percentage(self) -> None:
        """Zero percentage is valid."""
        callback = MagicMock()
        transcriber = WhisperTranscriber(
            model_name="tiny",
            progress_callback=callback,
        )
        transcriber._report_progress("Starting", 0.0)
        callback.assert_called_once_with("Starting", 0.0)

    def test_ensure_model_calls_download_once(self) -> None:
        """_ensure_model triggers download only on first call."""
        callback = MagicMock()
        transcriber = WhisperTranscriber(
            model_name="tiny",
            progress_callback=callback,
        )
        download_calls = 0

        def _track_download(*args, **kwargs):
            nonlocal download_calls
            download_calls += 1

        with patch("dictapaste.stt.WhisperModel"):
            with patch.object(transcriber, "_download_model_if_needed", side_effect=_track_download):
                transcriber._ensure_model()
                first = download_calls
                transcriber._ensure_model()
                assert download_calls == first, "Model should not be re-downloaded"
