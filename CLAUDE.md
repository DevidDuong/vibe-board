# Claude Code — Vibe-Board agent instructions

The product and engineering source of truth is **`CLIPFLOW_SPEC.md`**. Read it in full before designing or coding.

Vibe-Board is a **privacy-first macOS command library** for terminal commands. It targets **macOS on Apple Silicon**, is developed in **VS Code**, and uses **Python + PySide6 (QSS) + PyObjC + SQLite**. It is a **local-only desktop application**, not a web service.

The original automatic clipboard-history design was **superseded on 2026-10-01**. Don't reintroduce any part of it.

**Name:** the app is shown as **Vibe-Board** (`clipflow.APP_NAME`). It was called ClipFlow until 2026-10-02.
- Internal names keep the old name on purpose: the `clipflow` package, `config.STORAGE_NAME` (the `~/Library/Application Support/ClipFlow` and `~/Library/Logs/ClipFlow` folders), `CLIPFLOW_*` variables, the bundle identifier, and `packaging/ClipFlow.spec`.
- Never derive storage paths from `APP_NAME`.
- Never move or rename the library folder without explicit approval and a tested, non-destructive migration.
- Use `APP_NAME` for any new user-visible text. `tests/test_branding.py` enforces this.

## What you must do

1. Inspect the existing repository and environment before editing. Don't overwrite files blindly.
2. Follow the phases in `CLIPFLOW_SPEC.md` §8. Phases 1 (security refactor), 2 (command library), 3 (modern UI redesign) and 5 (local standalone `.app`) are done. Phase 4 is mostly done (global shortcut, title-bar fix, window placement); the Dock-icon decision is still open.
   - Build with `./packaging/build_macos.sh`; test with `./packaging/smoke_test_app.sh`. Both use throwaway data only.
   - Never install into `/Applications`, sign with a real identity, notarize or publish without explicit approval.
   - Never bundle data files, databases, logs or credentials. `verify_bundle.py` enforces this.
   - Keep `--self-test` guarded so it can't run against the real library.
3. Keep the layers separate:
   - UI views (render and emit only)
   - the controller
   - service rules
   - repositories / SQL
   - platform adapters

   Use modern type hints and small, testable units.
4. **Clipboard:**
   - **Never read the system clipboard** on Vibe-Board's own initiative: not in the background, and not while the user is browsing or searching.
   - Don't add any monitor, polling timer, recorder thread or "recording" preference.
   - The clipboard adapter is **write-only** (`ClipboardWriter.write_text`). Write only on an explicit user copy action.
5. **Commands are data:**
   - Never execute, parse or shell-expand command text.
   - No `subprocess`, `os.system`/`exec*`/`spawn*`, `QProcess`, `eval` or `shlex`.
   - No keyboard injection or automatic pasting into other apps.
6. **Privacy:**
   - Never log or print command text, titles, descriptions, search terms or clipboard data. Log ids, counts and exception type names only.
   - No network, telemetry or sync.
   - Never import `~/.zsh_history` or other shell history automatically.
7. **Secrets:**
   - Keep the best-effort secret policy (`services/secret_scanner.py`): block private keys, warn on recognizable tokens and passwords.
   - Be honest about its limitations.
   - Tests must use synthetic, runtime-assembled fake secrets, never real ones.
8. **Legacy data:**
   - Never delete, display, import or silently migrate the legacy `clipboard_entries` table or its `recording_*` settings.
   - Only `scripts/legacy_history.py` touches it, and only when the user runs it.
9. Use parameterized SQL and additive, idempotent migrations via `PRAGMA user_version`. The database files and directory must be user-only.
10. **Global shortcut** (default ⌃⌥⌘V; D15):
    - It's implemented with Carbon `RegisterEventHotKey` behind `platform/hotkey.py` and `platform/macos_hotkey.py`.
    - It may only show or hide the window.
    - Never add event taps, global or local key monitors, synthetic input, Accessibility, Input Monitoring or Screen Recording. `tests/test_security.py` enforces this.
    - Keep a single process-wide Carbon handler.
    - Register the new shortcut before releasing the old one, and keep the menu-bar fallback.
11. Every production button and shortcut must work. No decorative or inert settings. Don't claim tests pass without running them.
    - Preferences live only under whitelisted `ui.*` keys (`PreferencesRepository.KEYS`) and are saved only on explicit Save.
    - Window geometry (`ui.window_geometry`) is UI state, saved automatically when the window hides and on quit.
    - Settings must never offer recording, clipboard reading, command execution or launch at login.
    - UI changes: keep themes token-based (`ui/theme.py`) with the WCAG contrast test passing.
    - Render visual states with `scripts/render_ui_states.py` and look at them before claiming a visual fix.
    - Keep AppKit/PyObjC imports inside `platform/macos_*.py`.
12. Write unit tests with fakes and temporary SQLite, keep the security tests in `tests/test_security.py` green, and maintain `tests/manual_macos_checklist.md`. Report automated results separately from manual macOS checks.
13. Use one dependency source (`pyproject.toml`; `requirements.txt` is the generated lock).
14. Never enable launch at login by default.
15. Do **not** stage, commit, push, publish, remove unrelated work, or change the user's machine-level security settings unless explicitly asked.

## Work-session response format

At each milestone, state:
- Implemented features and files changed.
- Commands run and real test results (or the exact reason they weren't run).
- macOS/manual checks the user should perform.
- Known limitations and the next milestone.

If the environment can't run the macOS GUI, label native behavior as unverified and give the user a verification script or checklist. Never fake integration results.
