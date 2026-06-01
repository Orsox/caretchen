from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

import httpx

from .config import LLMConfig
from .prompt import render_prompt

logger = logging.getLogger(__name__)

_ECHO_PREFIX_RE = re.compile(
    r"^(?:bereinigter\s*text|cleaned\s*text|improved|verbessert(?:er?\s*text)?|result|output|ergebnis|final(?:\s+(?:answer|choice))?(?:[^:\n]{0,100})?)\s*:\s*",
    re.IGNORECASE,
)
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_FINAL_MARKER_RE = re.compile(
    r"(?:^|\n)\s*(?:final(?:\s+(?:answer|choice))?(?:[^:\n]{0,100})?|end(?:ergebnis)?|bereinigter\s*text|cleaned\s*text|improved|verbessert(?:er?\s*text)?|result|output|ergebnis)\s*:\s*",
    re.IGNORECASE,
)
_ANALYSIS_MARKER_RE = re.compile(
    r"(?im)^\s*(?:analysis|reasoning|thought process|thinking|gedanken|analyse)\s*:\s*"
)
_READY_MARKER_RE = re.compile(
    r"(?:the\s+resulting\s+(?:german\s+)?prose\s+is\s+ready\.|the\s+resulting\s+text\s+is\s+ready\.)\s*",
    re.IGNORECASE,
)
_CHECKLIST_LINE_RE = re.compile(r"(?m)^\s*\d+[.)]\s+.*(?:\n|$)")
_META_LEAK_RE = re.compile(
    r"\b(?:the user wants|the input text is|original text analysis|refined output construction|self-correction|"
    r"drafting the clean version|revision steps|goal \d+|this seems compact|i will keep|if i treat|however, if|"
    r"since the input|given the ambiguity|let's stick|clean up|analysis:)\b",
    re.IGNORECASE,
)
_ARROW_FINAL_RE = re.compile(r"(?:->|→)\s*[\"“”']?(?P<final>[^\"“”'\n.]+)[\"“”']?\s*\.?(?P=final)?\s*$", re.IGNORECASE)
_GERMAN_TAIL_RE = re.compile(
    r"(?s).*[.!?]\s*(?=(?:Ich|Das|Die|Der|Den|Dem|Bitte|Zusätzlich|Außerdem|Des Weiteren|Wenn|Beim|Nach|Im|Am|Es)\b)"
)


def _normalize_for_comparison(text: str) -> str:
    return " ".join(text.split()).strip().casefold()


class LLMError(RuntimeError):
    pass


class LLMCancelled(LLMError):
    pass


class _ThinkBlockFilter:
    """State-machine filter for streamed <think>...</think> blocks across chunks."""

    def __init__(self) -> None:
        self._inside_think = False
        self._pending = ""

    def feed(self, chunk: str) -> str:
        text = self._pending + chunk
        self._pending = ""
        output: list[str] = []
        i = 0

        while i < len(text):
            lowered_tail = text[i:].casefold()
            if self._inside_think:
                close_idx = lowered_tail.find(_THINK_CLOSE)
                if close_idx < 0:
                    self._pending = text[max(i, len(text) - len(_THINK_CLOSE) + 1) :]
                    return "".join(output)
                i += close_idx + len(_THINK_CLOSE)
                self._inside_think = False
                continue

            open_idx = lowered_tail.find(_THINK_OPEN)
            if open_idx < 0:
                safe_end = len(text)
                for keep in range(min(len(_THINK_OPEN) - 1, len(text)), 0, -1):
                    if _THINK_OPEN.startswith(text[-keep:].casefold()):
                        safe_end = len(text) - keep
                        self._pending = text[safe_end:]
                        break
                output.append(text[i:safe_end])
                return "".join(output)

            output.append(text[i : i + open_idx])
            i += open_idx + len(_THINK_OPEN)
            self._inside_think = True

        return "".join(output)

    def flush(self) -> str:
        if self._inside_think:
            self._pending = ""
            return ""
        pending = self._pending
        self._pending = ""
        return pending


class LLMRefiner:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._cancel_requested = False

    def cancel(self) -> None:
        """Request cancellation of the current LLM request."""
        self._cancel_requested = True

    def is_cancelled(self) -> bool:
        return self._cancel_requested

    def reset_cancel(self) -> None:
        self._cancel_requested = False

    def update_config(self, config: LLMConfig) -> None:
        self.config = config

    def is_available(self) -> bool:
        endpoint = self.config.base_url.rstrip("/") + "/v1/models"
        try:
            with httpx.Client(timeout=min(self.config.timeout_sec, 5)) as client:
                response = client.get(endpoint)
                response.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("LLM availability check failed: endpoint=%s error=%s", endpoint, exc)
            return False

    def refine(self, transcript: str, prompt_template: str, language: str = "auto") -> str:
        prompt = render_prompt(prompt_template, transcript, language=language)
        endpoint = self.config.base_url.rstrip("/") + "/v1/chat/completions"
        payload = self._build_payload(prompt, stream=False)

        logger.info(
            "LLM request start: base_url=%s endpoint=%s model=%s timeout_sec=%s transcript_chars=%s prompt_chars=%s stream=false",
            self.config.base_url,
            endpoint,
            self.config.model,
            self.config.timeout_sec,
            len(transcript),
            len(prompt),
        )

        try:
            with httpx.Client(timeout=self.config.timeout_sec) as client:
                response = client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()

            logger.info(
                "LLM request success: endpoint=%s status_code=%s",
                endpoint,
                response.status_code,
            )
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text if exc.response is not None else "<no response body>"
            logger.error(
                "LLM HTTP status error: endpoint=%s status_code=%s body=%s",
                endpoint,
                exc.response.status_code if exc.response is not None else "unknown",
                response_text[:1000],
            )
            raise LLMError(f"LLM request failed with HTTP status {exc.response.status_code}: {response_text[:240]}") from exc
        except httpx.RequestError as exc:
            logger.error(
                "LLM request transport error: endpoint=%s error_type=%s error=%s",
                endpoint,
                type(exc).__name__,
                str(exc),
            )
            raise LLMError(f"LLM request failed: {exc}") from exc
        except ValueError as exc:
            logger.error(
                "LLM JSON parse error: endpoint=%s error=%s",
                endpoint,
                str(exc),
            )
            raise LLMError("LLM response was not valid JSON.") from exc

        self._ensure_reasoning_disabled(data)
        return self._extract_text(data, prompt=prompt, transcript=transcript)

    def refine_stream(
        self,
        transcript: str,
        prompt_template: str,
        language: str = "auto",
        chunk_callback: Callable[[str], None] | None = None,
    ) -> str:
        prompt = render_prompt(prompt_template, transcript, language=language)
        endpoint = self.config.base_url.rstrip("/") + "/v1/chat/completions"
        payload = self._build_payload(prompt, stream=True)
        chunks: list[str] = []
        think_filter = _ThinkBlockFilter()

        logger.info(
            "LLM request start: base_url=%s endpoint=%s model=%s timeout_sec=%s transcript_chars=%s prompt_chars=%s stream=true",
            self.config.base_url,
            endpoint,
            self.config.model,
            self.config.timeout_sec,
            len(transcript),
            len(prompt),
        )

        try:
            with httpx.Client(timeout=self.config.timeout_sec) as client:
                with client.stream("POST", endpoint, json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if self._cancel_requested:
                            raise LLMCancelled("LLM request cancelled.")

                        content = self._parse_stream_line(line)
                        if content is None:
                            continue
                        visible_content = think_filter.feed(content)
                        if not visible_content:
                            continue
                        chunks.append(visible_content)
                        if chunk_callback is not None:
                            chunk_callback(visible_content)

                    tail = think_filter.flush()
                    if tail:
                        chunks.append(tail)
                        if chunk_callback is not None:
                            chunk_callback(tail)

            logger.info("LLM stream success: endpoint=%s chunks=%s", endpoint, len(chunks))
        except LLMCancelled:
            raise
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text if exc.response is not None else "<no response body>"
            logger.error(
                "LLM stream HTTP status error: endpoint=%s status_code=%s body=%s",
                endpoint,
                exc.response.status_code if exc.response is not None else "unknown",
                response_text[:1000],
            )
            raise LLMError(f"LLM request failed with HTTP status {exc.response.status_code}: {response_text[:240]}") from exc
        except httpx.RequestError as exc:
            logger.error(
                "LLM stream transport error: endpoint=%s error_type=%s error=%s",
                endpoint,
                type(exc).__name__,
                str(exc),
            )
            raise LLMError(f"LLM request failed: {exc}") from exc
        except ValueError as exc:
            logger.error("LLM stream parse error: endpoint=%s error=%s", endpoint, str(exc))
            raise LLMError("LLM stream response was not valid JSON.") from exc

        result = self._sanitize_model_output("".join(chunks).strip(), prompt=prompt, transcript=transcript)
        if not result:
            logger.error("LLM stream returned empty text")
            raise LLMError("LLM returned empty text.")
        return result

    def _build_payload(self, prompt: str, stream: bool) -> dict:
        return {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "/no_think\n"
                        "You are a deterministic text-cleaning function. "
                        "Return only the final cleaned continuous prose. "
                        "Do not include headings, labels, explanations, alternatives, analysis, reasoning, or thinking. "
                        "If you cannot comply without reasoning, return the cleaned text only."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": self.config.temperature,
            "reasoning_effort": "none",
            "reasoning": {"effort": "none"},
            "think": False,
            "thinking": {"type": "disabled"},
            "chat_template_kwargs": {"enable_thinking": False, "preserve_thinking": False},
            "stream": stream,
        }

    def _parse_stream_line(self, line: str) -> str | None:
        line = line.strip()
        if not line:
            return None
        if line.startswith("data:"):
            line = line[5:].strip()
        if line == "[DONE]":
            return None

        data = json.loads(line)
        self._ensure_reasoning_disabled(data)

        try:
            choice = data["choices"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Unexpected LLM stream response shape.") from exc

        delta = choice.get("delta") or choice.get("message") or {}
        content = delta.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            content = "".join(parts)
        if content is None:
            return None
        if not isinstance(content, str):
            raise ValueError("LLM stream content is not text.")
        return content

    @staticmethod
    def _ensure_reasoning_disabled(data: dict) -> None:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return

        completion_details = usage.get("completion_tokens_details")
        if not isinstance(completion_details, dict):
            return

        reasoning_tokens = completion_details.get("reasoning_tokens")
        if not isinstance(reasoning_tokens, int):
            return

        if reasoning_tokens > 0:
            logger.error("LLM reported reasoning tokens despite reasoning_effort=none: %s", reasoning_tokens)
            raise LLMError("LLM used thinking tokens although reasoning was disabled.")

    @staticmethod
    def _extract_text(data: dict, prompt: str | None = None, transcript: str | None = None) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.error("Unexpected LLM response shape: %s", repr(data)[:1000])
            raise LLMError("Unexpected LLM response shape.") from exc

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            content = "".join(parts)

        if not isinstance(content, str):
            logger.error("LLM response content is not text: type=%s", type(content).__name__)
            raise LLMError("LLM response content is not text.")

        result = LLMRefiner._sanitize_model_output(content.strip(), prompt=prompt, transcript=transcript)
        if not result:
            logger.error("LLM returned empty text")
            raise LLMError("LLM returned empty text.")

        return result

    @staticmethod
    def _sanitize_model_output(text: str, prompt: str | None = None, transcript: str | None = None) -> str:
        if not text:
            return ""

        think_filter = _ThinkBlockFilter()
        text = (think_filter.feed(text) + think_filter.flush()).strip()
        text = _THINK_BLOCK_RE.sub("", text).strip()

        # Handle orphaned </think> close tag (model started thinking but block wasn't captured)
        last_close = text.lower().rfind("</think>")
        if last_close >= 0:
            after = text[last_close + len("</think>"):].strip()
            if after:
                text = after

        prompt_clean = (prompt or "").strip()
        transcript_clean = (transcript or "").strip()

        # Fast path: output is clean — strip any label prefix and return immediately
        if not (
            _META_LEAK_RE.search(text)
            or _FINAL_MARKER_RE.search(text)
            or _ANALYSIS_MARKER_RE.search(text)
            or _READY_MARKER_RE.search(text)
            or _CHECKLIST_LINE_RE.search(text)
            or (prompt_clean and text.startswith(prompt_clean))
            or (transcript_clean and len(text) > len(transcript_clean) and text.startswith(transcript_clean))
        ):
            cleaned = _ECHO_PREFIX_RE.sub("", text, count=1).strip()
            return cleaned or text

        candidates: list[str] = [text]

        if _META_LEAK_RE.search(text):
            meta_removed = LLMRefiner._remove_meta_leakage(text)
            if meta_removed and meta_removed != text:
                candidates.insert(0, meta_removed)

        ready_parts = _READY_MARKER_RE.split(text)
        if len(ready_parts) > 1:
            ready_tail = ready_parts[-1].strip(" \n\t:-")
            if ready_tail:
                candidates.insert(0, ready_tail)

        checklist_removed = _CHECKLIST_LINE_RE.sub("", text).strip()
        if checklist_removed and checklist_removed != text:
            candidates.append(checklist_removed)

        final_parts = _FINAL_MARKER_RE.split(text)
        if len(final_parts) > 1:
            final_tail = final_parts[-1].strip(" \n\t:-")
            if final_tail:
                candidates.insert(0, final_tail)

        if _ANALYSIS_MARKER_RE.search(text):
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
            if paragraphs:
                candidates.insert(0, paragraphs[-1])

        if prompt_clean:
            if text.startswith(prompt_clean):
                tail = text[len(prompt_clean) :].strip(" \n\t:-")
                if tail:
                    candidates.append(tail)
            idx = text.find(prompt_clean)
            if idx >= 0:
                tail = text[idx + len(prompt_clean) :].strip(" \n\t:-")
                if tail:
                    candidates.append(tail)

        if transcript_clean and len(text) > len(transcript_clean):
            raw_prefix = f"Raw transcript:\n{transcript_clean}"
            if text.startswith(raw_prefix):
                tail = text[len(raw_prefix) :].strip(" \n\t:-")
                if tail:
                    candidates.append(tail)
            if text.startswith(transcript_clean):
                tail = text[len(transcript_clean) :].strip(" \n\t:-")
                if tail:
                    candidates.append(tail)

        prompt_normalized = _normalize_for_comparison(prompt_clean) if prompt_clean else ""
        transcript_normalized = _normalize_for_comparison(transcript_clean) if transcript_clean else ""

        cleaned_candidates = []
        for candidate in candidates:
            normalized = _ECHO_PREFIX_RE.sub("", candidate.strip(), count=1).strip()
            if not normalized:
                continue

            normalized_candidate = _normalize_for_comparison(normalized)
            if prompt_normalized and normalized_candidate == prompt_normalized:
                continue

            if prompt_normalized and transcript_normalized:
                prompt_plus_transcript = _normalize_for_comparison(f"{prompt_clean}\n{transcript_clean}")
                if normalized_candidate == prompt_plus_transcript:
                    continue

            cleaned_candidates.append(LLMRefiner._collapse_repeated_output(normalized))

        if not cleaned_candidates and transcript_clean:
            text_normalized = _normalize_for_comparison(text)
            prompt_echoes = {prompt_normalized}
            if prompt_normalized and transcript_normalized:
                prompt_echoes.add(_normalize_for_comparison(f"{prompt_clean}\n{transcript_clean}"))

            if text_normalized in prompt_echoes:
                return transcript_clean

        if cleaned_candidates:
            # Prefer the shortest non-empty candidate to avoid prompt echos.
            best = min(cleaned_candidates, key=len)
            return best

        return ""

    @staticmethod
    def _remove_meta_leakage(text: str) -> str:
        cleaned_lines: list[str] = []
        skip_until_blank = False
        for line in text.splitlines():
            stripped = line.strip()
            if _META_LEAK_RE.search(stripped):
                skip_until_blank = True
                continue
            if skip_until_blank:
                if not stripped:
                    skip_until_blank = False
                continue
            cleaned_lines.append(line)

        arrow_match = _ARROW_FINAL_RE.search(text.strip())
        if arrow_match:
            return arrow_match.group("final").strip()

        cleaned = "\n".join(cleaned_lines).strip()
        if not cleaned:
            cleaned = text.strip()

        german_tail = _GERMAN_TAIL_RE.sub("", cleaned).strip()
        if german_tail and len(german_tail) < len(cleaned):
            return german_tail

        return cleaned

    @staticmethod
    def _collapse_repeated_output(text: str) -> str:
        """Collapse accidental repeated final answers, even when joined without whitespace."""
        stripped = text.strip()
        if not stripped:
            return ""

        length = len(stripped)
        for split_at in range(1, (length // 2) + 1):
            first = stripped[:split_at].strip()
            second = stripped[split_at:].strip()
            if first and first == second:
                return first

        return LLMRefiner._prefer_last_sentence_variant(stripped)

    @staticmethod
    def _prefer_last_sentence_variant(text: str) -> str:
        """When the model emits multiple corrected variants, keep the final one."""
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s*(?=[A-ZÄÖÜ])", text) if part.strip()]
        if len(sentences) < 2:
            return text

        last = sentences[-1]
        previous = sentences[-2]
        last_words = _normalize_for_comparison(last).split()[:5]
        previous_words = _normalize_for_comparison(previous).split()[:5]
        shared_prefix_words = 0
        for left, right in zip(last_words, previous_words):
            if left != right:
                break
            shared_prefix_words += 1

        if shared_prefix_words >= 3 and len(last) >= 20:
            return last

        return text
