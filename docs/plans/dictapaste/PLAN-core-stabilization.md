# Implementation Plan: DictaPaste — Core Stabilization & Feature Expansion

## Overview

DictaPaste is a cross-platform system-tray dictation app (Windows + Linux/X11). It records audio via a global mouse-button toggle, transcribes speech locally with Whisper (`faster-whisper`), optionally refines the transcript through a local LLM (Ollama/LM Studio), and pastes the result into the focused application via clipboard + Ctrl+V.

The codebase is functional but has gaps in test coverage, missing platform support (Linux autostart), no error recovery UI, no history/log, and the Settings dialog is German-only with limited configurability. This plan breaks work into vertical slices that each deliver testable, working functionality.

## Architecture Overview

```
tray.py (DictaPasteTrayApp)
  ├── input_hook.py (MouseToggleHook) ── global mouse listener
  ├── pipeline.py (DictationPipeline) ─── orchestrator (threaded)
  │     ├── audio.py (AudioRecorder) ──── sounddevice stream
  │     ├── stt.py (WhisperTranscriber) ─ faster-whisper transcription
  │     ├── llm.py (LLMRefiner) ───────── httpx OpenAI-compatible call
  │     └── paste.py (paste_text) ─────── clipboard + keyboard simulation
  ├── config.py (AppConfig) ───────────── TOML + YAML config
  ├── prompt.py ───────────────────────── prompt loading/saving
  ├── settings_dialog.py ──────────────── Qt settings UI
  ├── autostart.py ────────────────────── Windows startup script
  └── icon.py ─────────────────────────── icon loading
```

**Dependency graph (bottom → top):**
```
app_state (enum)
    ↑
audio, stt, llm, paste, input_hook (independent modules)
    ↑
config, prompt (shared config layer)
    ↑
pipeline (orchestrates audio→stt→llm→paste)
    ↑
tray (UI layer, wires everything together)
    ↑
settings_dialog (UI above tray)
    ↑
main (entry point)
```

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Wayland lack of support | Linux users on Wayland can't use global mouse hook | Document limitation; consider `xdotool`/d-Bus fallback later |
| Whisper model download on first run | Poor first-time UX | Add progress indicator; cache model path |
| LLM timeout kills UX | User waits 20s+ for nothing | Add cancel button; show progress state |
| pynput conflicts on macOS | Not yet supported — no risk for now | Platform guards in input_hook |
| Clipboard race conditions | Paste fails silently | Already has retry logic; add more robustness |

## Open Questions

1. **Should the app support multiple recording sessions (queue) or only one-at-a-time?** — Current code is single-session. Multi-session would be a bigger change.
2. **Should the LLM be configurable per-session (toggle in tray) or only globally?** — Currently only global toggle.
3. **Language support for UI strings?** — Currently all German. Should we add i18n or keep German-only?
4. **Should Whisper model size be configurable at runtime or only via settings restart?** — Currently requires restart to change model.

---

## Task List

### Phase 1: Foundation — Test Coverage & Config Robustness

#### Task 1: Add test coverage for pipeline error paths and edge cases

**Description:** The pipeline has only 2 tests covering the happy path. Add tests for: transcription failure (empty audio), LLM timeout, paste failure, recording already in progress, async processing mode, and state reset from ERROR.

**Acceptance criteria:**
- [ ] Test for transcription returning empty string → state returns to IDLE, no paste
- [ ] Test for recorder raising exception → state returns to IDLE
- [ ] Test for LLMError with async_processing=True → state transitions correctly
- [ ] Test for toggle_recording called while in TRANSCRIBING/REFINING/PASTING → ignored with message
- [ ] Test for update_runtime() replacing transcriber and refiner instances
- [ ] All existing tests still pass

**Verification:**
- [ ] Tests pass: `pytest tests/test_pipeline.py -v`
- [ ] Build succeeds: `python -c "import dictapaste"`
- [ ] Manual check: no regression in existing behavior

**Dependencies:** None

**Files likely touched:**
- `tests/test_pipeline.py` (new)
- `src/dictapaste/pipeline.py` (minor: add logging)

**Estimated scope:** M (2-3 files)

---

#### Task 2: Add test coverage for config edge cases and validation

**Description:** The config module handles TOML + YAML loading with fallbacks, but has no tests for: corrupt TOML, missing YAML sections, invalid values (negative timeout, empty base_url), and the `from_dict`/`to_dict` roundtrip for all field types.

**Acceptance criteria:**
- [ ] Test for corrupt/invalid TOML → returns default AppConfig
- [ ] Test for YAML with invalid types (string where int expected) → graceful fallback
- [ ] Test for `from_dict` with missing nested sections → uses defaults
- [ ] Test for `to_dict` roundtrip preserves all field types
- [ ] Test for `save_root_yaml` preserving existing prompt when only config changes
- [ ] Test for `load_config` with only YAML present (no TOML) → YAML overrides apply

**Verification:**
- [ ] Tests pass: `pytest tests/test_config.py -v`
- [ ] Build succeeds
- [ ] Manual check: app starts normally with various config states

**Dependencies:** None

**Files likely touched:**
- `tests/test_config.py` (new tests)

**Estimated scope:** S (1 file)

---

#### Task 3: Add test coverage for paste module edge cases

**Description:** The paste module has basic tests but misses: clipboard permission errors (PyperclipException), very long text (>10k chars), text with special characters/emojis, and the retry exhaustion path.

**Acceptance criteria:**
- [ ] Test for PyperclipException during copy → retries fail gracefully, raises exception
- [ ] Test for long text (>5000 chars) → pastes successfully
- [ ] Test for text with Unicode/emojis → clipboard handles correctly
- [ ] Test for _copy_with_retry exhausting all attempts → raises last error

**Verification:**
- [ ] Tests pass: `pytest tests/test_paste.py -v`
- [ ] Build succeeds

**Dependencies:** None

**Files likely touched:**
- `tests/test_paste.py` (new tests)

**Estimated scope:** S (1 file)

---

#### Checkpoint: Foundation
- [ ] All tests pass: `pytest -v`
- [ ] Build succeeds: `python -c "import dictapaste"`
- [ ] No regression in existing behavior
- [ ] Review with human before proceeding

---

### Phase 2: UX Improvements — Tray UI & Settings

#### Task 4: Add tray icon state colors for better visual feedback

**Description:** Currently the tray icon is static. Add color-coded icons per state: green (IDLE/RECORDING), yellow (TRANSCRIBING), blue (REFINING), orange (PASTING), red (ERROR). This gives instant visual feedback without opening the menu.

**Acceptance criteria:**
- [ ] `_build_state_icon(state)` generates a colored pixmap per AppState
- [ ] Icon color mapping: IDLE=gray, RECORDING=green, TRANSCRIBING=yellow, REFINING=blue, PASTING=orange, ERROR=red
- [ ] Icon updates in real-time via state callback
- [ ] Fallback to existing fallback icon if generation fails
- [ ] Works with both dev (SVG) and bundled (PyInstaller) modes

**Verification:**
- [ ] Build succeeds
- [ ] Manual check: icon changes color during a dictation cycle
- [ ] No regression in tray menu functionality

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/tray.py`
- `src/dictapaste/icon.py` (add state icon generation)

**Estimated scope:** M (2 files)

---

#### Task 5: Improve Settings dialog — add model discovery and better validation

**Description:** The Settings dialog has hardcoded Whisper model list and LLM model as free text. Add: (a) Whisper model description hints, (b) LLM connection test button, (c) better input validation with inline feedback, (d) English i18n labels alongside German.

**Acceptance criteria:**
- [ ] "Test LLM Connection" button sends a lightweight request and shows success/failure
- [ ] LLM base_url field validates URL format
- [ ] Timeout field shows current model's recommended timeout as tooltip
- [ ] Whisper model dropdown includes model size hints (e.g., "small (~500MB)")
- [ ] All dialog labels have English translations in comments or tooltip
- [ ] Settings dialog resize handles small windows gracefully

**Verification:**
- [ ] Build succeeds
- [ ] Manual check: Settings dialog opens, LLM test works with real/fake server
- [ ] No regression in settings save/load

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/settings_dialog.py`

**Estimated scope:** M (1 file)

---

#### Task 6: Add in-app error recovery — retry paste from tray menu

**Description:** When paste fails, the state goes to ERROR and stays there. Add a "Retry Paste" action to the tray menu when in ERROR state, and a "Last Result" preview. This prevents the user from having to restart the whole dictation cycle.

**Acceptance criteria:**
- [ ] Tray menu shows "Retry Paste" action when state is ERROR
- [ ] "Retry Paste" re-executes the last pasted text without re-recording
- [ ] Last result text shown in tray tooltip on hover
- [ ] ERROR state auto-resets to IDLE after 10 seconds if no action taken
- [ ] No new recording can start while in ERROR state

**Verification:**
- [ ] Build succeeds
- [ ] Manual check: trigger paste failure → see retry option → retry works
- [ ] No regression in normal dictation flow

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/tray.py`
- `src/dictapaste/pipeline.py`

**Estimated scope:** M (2 files)

---

#### Checkpoint: UX Improvements
- [ ] All tests pass
- [ ] Build succeeds
- [ ] Manual check: full dictation cycle with improved UI
- [ ] Review with human before proceeding

---

### Phase 3: Platform Support & Reliability

#### Task 7: Add Linux autostart support

**Description:** Autostart currently only works on Windows (creates `.cmd` in Startup folder). Add Linux support via `~/.config/autostart/` .desktop file, following the freedesktop autostart specification.

**Acceptance criteria:**
- [ ] `set_linux_autostart(enabled)` creates/removes `.desktop` file in `~/.config/autostart/`
- [ ] Desktop file follows freedesktop spec (Type=Application, Exec, Name, Comment)
- [ ] `set_windows_startup()` is platform-gated (no-op on Linux)
- [ ] New Linux autostart function is platform-gated (no-op on Windows)
- [ ] `set_autostart(enabled)` unified entry point dispatches to platform-specific function
- [ ] Unit tests for Linux autostart path

**Verification:**
- [ ] Tests pass: `pytest tests/ -v`
- [ ] Build succeeds
- [ ] Manual check (Linux): autostart toggle creates correct .desktop file

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/autostart.py`
- `tests/test_autostart.py` (new)

**Estimated scope:** S (2 files)

---

#### Task 8: Add audio input device selection

**Description:** Users may have multiple microphones. Add audio device enumeration and selection in the Settings dialog. Default to the system default device.

**Acceptance criteria:**
- [ ] `AudioRecorder` accepts an optional `device_id` parameter
- [ ] `sd.query_devices()` enumerates input devices on startup
- [ ] Settings dialog shows dropdown with device names and indices
- [ ] Default selection is the system default input device
- [ ] Invalid device selection falls back to default with a warning
- [ ] Device list refreshes when settings dialog opens (hotplug safety)

**Verification:**
- [ ] Build succeeds
- [ ] Manual check: device dropdown shows available microphones
- [ ] Selecting different device changes recording source

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/audio.py`
- `src/dictapaste/settings_dialog.py`
- `src/dictapaste/config.py` (add AudioConfig dataclass)

**Estimated scope:** M (3 files)

---

#### Task 9: Add recording duration indicator and abort

**Description:** Users have no feedback on how long they've been recording. Add a recording timer to the tray tooltip and menu, and an "Abort Recording" option to cancel mid-recording.

**Acceptance criteria:**
- [ ] Tray tooltip shows recording duration (e.g., "caretchen - Recording 0:15")
- [ ] Duration updates every second during recording
- [ ] Tray menu shows "Abort Recording" action during RECORDING state
- [ ] Abort stops recording, discards captured audio, returns to IDLE
- [ ] Abort shows notification: "Recording aborted."
- [ ] No regression in normal recording flow

**Verification:**
- [ ] Build succeeds
- [ ] Manual check: timer updates during recording, abort works
- [ ] No regression in normal dictation flow

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/tray.py`
- `src/dictapaste/audio.py`
- `src/dictapaste/pipeline.py`

**Estimated scope:** M (3 files)

---

#### Checkpoint: Platform Support & Reliability
- [ ] All tests pass
- [ ] Build succeeds
- [ ] Manual check: app works on both Windows and Linux (where applicable)
- [ ] Review with human before proceeding

---

### Phase 4: Quality of Life Features

#### Task 10: Add dictation history (in-memory with optional file persistence)

**Description:** Users can't see what was previously dictated. Add an in-memory history buffer (last 50 entries) with optional file persistence. Each entry stores: timestamp, raw transcript, refined text (if any), and source (transcript-only vs. LLM-refined).

**Acceptance criteria:**
- [ ] `DictationHistory` class stores last 50 entries with timestamp, raw_text, refined_text, was_refined
- [ ] History is populated automatically after each successful paste
- [ ] History persists to `history.json` in config directory across restarts
- [ ] Settings dialog shows history panel with entries (timestamp + first 50 chars)
- [ ] Clicking an entry copies it to clipboard
- [ ] "Clear History" button in settings

**Verification:**
- [ ] Build succeeds
- [ ] Manual check: history persists across restarts, entries are clickable
- [ ] No regression in normal dictation flow

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/pipeline.py` (integrate history)
- `src/dictapaste/settings_dialog.py` (add history panel)
- `src/dictapaste/tray.py` (optional: quick history access)

**Estimated scope:** L (3-4 files)

---

#### Task 11: Add system notification on paste completion with copy-to-clipboard

**Description:** After pasting, also offer to copy the result to clipboard (in addition to pasting). Show a system notification with the pasted text (truncated). Allow clicking the notification to see full text.

**Acceptance criteria:**
- [ ] After successful paste, show system notification with truncated result text
- [ ] Notification is clickable → opens a small preview dialog with full text
- [ ] Preview dialog has "Copy" button
- [ ] Settings toggle: "Also copy to clipboard after paste" (default: off, since Ctrl+V already copies)
- [ ] Notification respects user's system notification settings

**Verification:**
- [ ] Build succeeds
- [ ] Manual check: notification appears after paste, preview dialog works
- [ ] No regression in normal dictation flow

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/tray.py`
- `src/dictapaste/settings_dialog.py`
- `src/dictapaste/pipeline.py`

**Estimated scope:** M (3 files)

---

#### Task 12: Add logging viewer in Settings dialog

**Description:** Debugging issues requires checking `dictapaste.log`. Add a log viewer tab/panel in the Settings dialog that shows the last 100 lines of the log file with auto-refresh.

**Acceptance criteria:**
- [ ] Settings dialog has a "Logs" tab/section
- [ ] Shows last 100 lines of `dictapaste.log` in a read-only text area
- [ ] Auto-refreshes every 5 seconds while the tab is visible
- [ ] "Open Log File" button opens the log file in the default text editor
- [ ] "Clear Log" button (with confirmation) truncates the log file
- [ ] Log viewer is only available on platforms where file access works

**Verification:**
- [ ] Build succeeds
- [ ] Manual check: log viewer shows recent log entries, auto-refresh works
- [ ] No regression in settings dialog

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/settings_dialog.py`
- `src/dictapaste/logging_setup.py` (add log path accessor)

**Estimated scope:** S (2 files)

---

#### Checkpoint: Complete
- [ ] All tests pass: `pytest -v`
- [ ] Build succeeds: `python -c "import dictapaste"`
- [ ] Manual check: all new features work end-to-end
- [ ] Documentation updated (README.md reflects new features)
- [ ] Ready for human review

---

## Summary

| Phase | Tasks | Scope | Goal |
|-------|-------|-------|------|
| 1. Foundation | 1-3 | ~3 files | Comprehensive test coverage |
| 2. UX Improvements | 4-6 | ~5 files | Better visual feedback & error recovery |
| 3. Platform Support | 7-9 | ~6 files | Linux autostart, device selection, recording abort |
| 4. Quality of Life | 10-12 | ~6 files | History, notifications, log viewer |

**Total estimated tasks:** 12
**Total estimated scope:** ~20 file changes across 4 phases
**Checkpoint frequency:** After every 3 tasks
