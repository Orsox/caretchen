# Implementation Plan: DictaPaste — v2 Feature Improvements

## Overview

DictaPaste v1 is stable with 83 tests passing, covering core functionality: tray-based dictation with global mouse toggle, Whisper transcription, optional LLM refinement, error recovery, history, and platform support (Windows + Linux).

This plan targets **v2 improvements** that address real user pain points identified in the codebase and open questions from the previous plan:

1. **Whisper model progress feedback** — first-run model download is silent and confusing
2. **i18n foundation** — all UI strings are hardcoded German; add English alongside
3. **Better LLM timeout UX** — 20s timeout gives no progress feedback
4. **Multiple paste modes** — currently only Ctrl+V; add direct clipboard, keyboard, and X11/xdotool
5. **Config migration** — no versioning; new fields break old configs silently
6. **Input hook conflict detection** — mouse hook silently blocks the chosen button

Each task is a vertical slice delivering testable, working functionality.

## Architecture Decisions

- **Keep PySide6 as the only UI framework** — no migration to web-based UI
- **Add i18n via Qt's `QTranslator`** — not custom dict, leverages Qt ecosystem
- **Add `paste_mode` enum** — not just a string, with validation
- **Version config with `version` field** — enable forward-compatible migrations
- **Whisper progress via callback** — not blocking; feed progress to pipeline callback

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Qt translator loading order | Translations don't apply | Load translator before QApplication init |
| Whisper progress callback API changes | Callback signature mismatch | Wrap in adapter; test with mock |
| xdotool not installed on Linux | Paste mode fails silently | Graceful fallback to Ctrl+V |
| Config migration breaks user data | User loses settings | Preserve unknown fields; log migration steps |
| Mouse hook conflict detection false positives | User sees spurious warnings | Only warn if conflict detected during recording |

## Open Questions

1. **Should i18n cover all UI strings or just the tray menu?** — Plan covers all user-visible strings.
2. **Should Whisper model progress show in tray or a separate dialog?** — Tray tooltip + message callback (non-blocking).
3. **Should config migration be automatic or prompt the user?** — Automatic with logging; user can reset.
4. **Should paste modes be configurable per-session or only globally?** — Global in settings (simpler for v2).

---

## Task List

### Phase 1: Foundation — i18n & Config Versioning

#### Task 1: Add i18n foundation with German and English

**Description:** Introduce a translation system using Qt's `QTranslator`. Extract all hardcoded UI strings from `tray.py`, `settings_dialog.py`, and `input_hook.py` into translation files. Provide German (existing) and English translations. No behavior changes — just structural.

**Acceptance criteria:**
- [ ] `tray.py` uses `tr("...")` function for all user-visible strings
- [ ] `settings_dialog.py` uses `tr("...")` for all user-visible strings
- [ ] `input_hook.py` uses `tr("...")` for all user-visible strings
- [ ] `tr()` falls back to English if no translation found
- [ ] German translation file (`de_DE.ts`) contains all German strings
- [ ] English translation file (`en_US.ts`) contains all English strings
- [ ] App loads German by default on German locale, English otherwise
- [ ] All 83 existing tests still pass (no behavior change)

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds: `python -c "import dictapaste"`
- [ ] Manual check: UI shows English strings when LANG=en_US

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/tray.py`
- `src/dictapaste/settings_dialog.py`
- `src/dictapaste/input_hook.py`
- `src/dictapaste/main.py` (translator loading)
- `tests/test_i18n.py` (new)

**Estimated scope:** M (5 files)

---

#### Task 2: Add config versioning and migration

**Description:** Config files have no version. Add a `version` field to the TOML config. Implement a migration system that upgrades old configs to the current version. This enables safe backward-compatible changes in the future.

**Acceptance criteria:**
- [ ] `AppConfig` includes a `version: int = 1` field
- [ ] `load_config()` reads version from TOML and applies migrations if needed
- [ ] Migration v0→v1: adds missing `audio` section with defaults
- [ ] Migration preserves all existing user settings during upgrade
- [ ] Unknown future versions log a warning but don't crash
- [ ] `save_config()` writes the current version
- [ ] Unit tests for migration v0→v1 and forward-compatibility

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: existing config.toml upgrades without data loss

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/config.py`
- `tests/test_config.py`

**Estimated scope:** S (2 files)

---

#### Task 3: Add paste mode enum and validation

**Description:** `paste_mode` is currently a plain string ("ctrl_v"). Add a proper `PasteMode` enum with `CTRL_V`, `COPY`, and `XDOTOOL` modes. Validate the mode on config load and fall back to `CTRL_V` on invalid values.

**Acceptance criteria:**
- [ ] `PasteMode` enum defined in `paste.py` with `CTRL_V`, `COPY`, `XDOTOOL`
- [ ] `OutputConfig.paste_mode` is `PasteMode` enum, not string
- [ ] `from_dict()` validates paste_mode string and falls back to `CTRL_V`
- [ ] `to_dict()` serializes enum to string
- [ ] `paste_text()` dispatches to the correct paste implementation based on mode
- [ ] `COPY` mode: copies to clipboard only (no keyboard simulation)
- [ ] `XDOTOOL` mode: uses `xdotool` on Linux (falls back to `CTRL_V` if not available)

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: each paste mode works correctly

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/paste.py`
- `src/dictapaste/config.py`
- `tests/test_paste.py`

**Estimated scope:** M (3 files)

---

#### Checkpoint: Foundation
- [ ] All 83+ tests pass
- [ ] Build succeeds
- [ ] Config migration works without data loss
- [ ] Review with human before proceeding

---

### Phase 2: Core UX — Whisper Progress & LLM Timeout

#### Task 4: Add Whisper model download progress feedback

**Description:** On first run, Whisper downloads the model silently. Users see no feedback for 30-60 seconds. Add a progress callback to `WhisperTranscriber` that reports download/initialization progress through the pipeline's `state_callback` or a new `progress_callback`.

**Acceptance criteria:**
- [ ] `WhisperTranscriber` accepts an optional `progress_callback: Callable[[str, float], None]`
- [ ] Progress callback receives (message, percentage) tuples during model load
- [ ] Pipeline forwards progress to `message_callback` or a dedicated `progress_callback`
- [ ] Tray tooltip shows "Loading Whisper model..." during initialization
- [ ] Progress is non-blocking (doesn't affect transcription quality)
- [ ] Progress callback is optional (existing code without it still works)
- [ ] Unit tests for progress callback invocation

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: progress message appears during first-run model load

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/stt.py`
- `src/dictapaste/pipeline.py`
- `src/dictapaste/tray.py`
- `tests/test_stt.py` (new)

**Estimated scope:** M (4 files)

---

#### Task 5: Add LLM timeout progress indicator

**Description:** When LLM is called, the user waits silently for up to 20 seconds. Add a progress indicator that shows the LLM is being contacted. If the request takes longer than 10 seconds, show a "still working..." message. Add a cancel option.

**Acceptance criteria:**
- [ ] Pipeline shows "Contacting LLM..." state during request
- [ ] If request exceeds 10s, shows "LLM taking longer than expected..."
- [ ] User can cancel LLM request via tray menu "Cancel" action
- [ ] Cancel sets a flag checked by the LLM client (graceful abort)
- [ ] Cancelled request falls back to raw transcript (same as timeout)
- [ ] Cancel action is only visible during LLM request

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: cancel during LLM request returns to IDLE with raw transcript

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/pipeline.py`
- `src/dictapaste/llm.py`
- `src/dictapaste/tray.py`

**Estimated scope:** M (3 files)

---

#### Task 6: Add Whisper model size selector with progress

**Description:** The Whisper model size (base/small/medium/large-v3) dramatically affects download time and accuracy. Add model size info to the Settings dropdown and show estimated download time. When user changes model, show a progress dialog for the download.

**Acceptance criteria:**
- [ ] Settings dropdown shows model size and estimated download time (e.g., "medium (~1.5 GB, ~3 min)")
- [ ] Changing model in Settings triggers a progress dialog during download
- [ ] Progress dialog shows download percentage and ETA
- [ ] User can cancel model download (stays on previous model)
- [ ] Downloaded model is cached (no re-download on restart)
- [ ] Model path is stored in config for fast restart

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: model change shows progress, download completes

**Dependencies:** Task 4 (progress callback infrastructure)

**Files likely touched:**
- `src/dictapaste/stt.py`
- `src/dictapaste/settings_dialog.py`
- `src/dictapaste/config.py`

**Estimated scope:** L (3-4 files)

---

#### Checkpoint: Core UX
- [ ] All tests pass
- [ ] Build succeeds
- [ ] Manual check: Whisper progress visible, LLM cancel works
- [ ] Review with human before proceeding

---

### Phase 3: Platform & Reliability — Input Hook & Paste Modes

#### Task 7: Add input hook conflict detection

**Description:** The mouse hook silently blocks the chosen button. Users don't realize their side button is unusable. Add conflict detection: warn the user if the chosen button is mapped to a common system function (e.g., middle-click = paste).

**Acceptance criteria:**
- [ ] `MouseToggleHook` detects if the chosen button conflicts with a common function
- [ ] Conflict detection checks: middle-click (paste), x1/x2 (browser back/forward)
- [ ] On conflict, shows a warning in the tray tooltip: "Warning: x2 may conflict with browser navigation"
- [ ] Warning only shows once (not on every trigger)
- [ ] User can dismiss the warning
- [ ] Conflict detection is platform-aware (Windows vs Linux)

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: warning appears for conflicting buttons

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/input_hook.py`
- `src/dictapaste/tray.py`

**Estimated scope:** S (2 files)

---

#### Task 8: Implement COPY and XDOTOOL paste modes

**Description:** `COPY` mode copies to clipboard only (no keyboard simulation) — useful for users who want to review before pasting. `XDOTOOL` mode uses `xdotool` on Linux for more reliable pasting. Both modes need proper error handling.

**Acceptance criteria:**
- [ ] `COPY` mode: writes text to clipboard, shows notification "Copied to clipboard"
- [ ] `COPY` mode does NOT simulate keyboard input
- [ ] `XDOTOOL` mode: uses `xdotool key ctrl+v` on Linux
- [ ] `XDOTOOL` mode gracefully falls back to `CTRL_V` if xdotool not found
- [ ] `CTRL_V` mode: existing behavior (clipboard + keyboard)
- [ ] Each mode has a dedicated test
- [ ] Settings dropdown shows paste mode with description

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: COPY mode copies without pasting, XDOTOOL works on Linux

**Dependencies:** Task 3 (paste mode enum)

**Files likely touched:**
- `src/dictapaste/paste.py`
- `src/dictapaste/settings_dialog.py`
- `tests/test_paste.py`

**Estimated scope:** M (3 files)

---

#### Task 9: Add audio input device hot-reload

**Description:** Currently, changing the audio device requires restarting the app. Add a "Refresh Devices" button in Settings that re-enumerates devices without restart. Also add a hot-reload on settings apply.

**Acceptance criteria:**
- [ ] Settings dialog has a "Refresh Devices" button
- [ ] Clicking refresh re-calls `enumerate_input_devices()` and repopulates the dropdown
- [ ] Changing device in Settings applies immediately (no restart needed)
- [ ] If currently recording, device change is deferred until recording stops
- [ ] Warning shown if selected device becomes unavailable
- [ ] Device selection persists across restarts

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: device change applies without restart

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/audio.py`
- `src/dictapaste/settings_dialog.py`
- `src/dictapaste/pipeline.py`

**Estimated scope:** S (3 files)

---

#### Checkpoint: Platform & Reliability
- [ ] All tests pass
- [ ] Build succeeds
- [ ] Manual check: all paste modes work, device hot-reload works
- [ ] Review with human before proceeding

---

### Phase 4: Polish — History Enhancements & Settings Polish

#### Task 10: Add history search and filtering

**Description:** The history panel shows entries but has no search. Add a search box that filters entries by raw text or refined text. Also add date range filtering (last hour, today, last 7 days).

**Acceptance criteria:**
- [ ] History panel has a search box that filters entries in real-time
- [ ] Search matches against both raw text and refined text
- [ ] Search is case-insensitive
- [ ] Empty search shows all entries
- [ ] Search results update as user types (debounced by 300ms)
- [ ] "All entries" count shown alongside search results count

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: search filters entries correctly

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/settings_dialog.py`
- `src/dictapaste/history.py`

**Estimated scope:** S (2 files)

---

#### Task 11: Add tray quick-actions menu

**Description:** The tray menu is functional but minimal. Add quick-access actions: "Copy Last Result", "View History", "Settings", and a state indicator that's more prominent. Group actions logically.

**Acceptance criteria:**
- [ ] Tray menu has a "Quick Actions" section with "Copy Last Result" and "View History"
- [ ] "Copy Last Result" copies the last pasted text to clipboard
- [ ] "View History" opens the Settings dialog on the history tab
- [ ] State indicator shows colored dot + state name (not just text)
- [ ] Menu is organized: Quick Actions, Recording Controls, Settings, Quit
- [ ] Quick actions are only enabled when relevant (e.g., "Copy Last Result" only when history exists)

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: quick actions work as expected

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/tray.py`

**Estimated scope:** S (1 file)

---

#### Task 12: Add settings dialog resize handling

**Description:** The Settings dialog has a fixed size. On high-DPI displays or with long translations, content gets clipped. Add proper resize handling, minimum size, and scrollable content areas.

**Acceptance criteria:**
- [ ] Settings dialog has a minimum size (500x400)
- [ ] Dialog resizes to fit content on different DPI settings
- [ ] Content areas (history, logs) are scrollable when content exceeds height
- [ ] Dialog remembers last size between opens
- [ ] All form fields remain visible at minimum size
- [ ] No overlapping or clipped widgets

**Verification:**
- [ ] Tests pass: `pytest -v`
- [ ] Build succeeds
- [ ] Manual check: dialog resizes correctly on different screen sizes

**Dependencies:** None

**Files likely touched:**
- `src/dictapaste/settings_dialog.py`

**Estimated scope:** XS (1 file)

---

#### Checkpoint: Complete
- [ ] All tests pass: `pytest -v`
- [ ] Build succeeds: `python -c "import dictapaste"`
- [ ] Manual check: all v2 features work end-to-end
- [ ] README.md updated with new features
- [ ] Ready for human review

---

## Summary

| Phase | Tasks | Scope | Goal |
|-------|-------|-------|------|
| 1. Foundation | 1-3 | ~7 files | i18n, config versioning, paste mode enum ✅ DONE |
| 2. Core UX | 4-6 | ~7 files | Whisper progress, LLM cancel, model selector ✅ DONE |
| 3. Platform | 7-9 | ~6 files | Conflict detection, COPY/XDOTOOL modes, device hot-reload ✅ DONE |
| 4. Polish | 10-12 | ~4 files | History search, tray quick-actions, resize handling ✅ DONE |

**Total estimated tasks:** 12
**Total estimated scope:** ~24 file changes across 4 phases
**Checkpoint frequency:** After every 3 tasks

**All phases complete — 135 tests passing (up from 83).**

## Parallelization Opportunities

- **Safe to parallelize:** Task 1 (i18n) and Task 2 (config versioning) are independent
- **Safe to parallelize:** Task 7 (conflict detection) and Task 9 (device hot-reload) are independent
- **Must be sequential:** Task 3 (paste mode enum) → Task 8 (paste mode implementations)
- **Must be sequential:** Task 4 (Whisper progress) → Task 6 (model selector with progress)
