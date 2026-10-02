# Vibe-Board — macOS Command Library

**Status:** implementation-ready product and engineering specification (revised 2026-10-02; modern UI and local standalone app implemented)
**Target:** Apple Silicon macOS first; developed in VS Code
**Language:** Python 3.12+
**UI:** PySide6 Qt Widgets + QSS
**macOS integration:** PyObjC/AppKit (menu bar, app activation, clipboard *write*)
**Storage:** local SQLite via stdlib `sqlite3`
**Distribution:** PyInstaller `.app` (macOS `--onedir --windowed`)

**Name:** Vibe-Board, renamed from ClipFlow on 2026-10-02. The rename is display-only.
- `clipflow.APP_NAME` drives the window title, menu-bar tooltip and menu, dialogs, and the `.app` bundle name.
- Internal names deliberately keep the old name: the `clipflow` Python package, `config.STORAGE_NAME` (the library and log folders under `ClipFlow`), the `CLIPFLOW_*` environment variables, the bundle identifier, and file names such as this spec and `packaging/ClipFlow.spec`.
- This keeps existing libraries working without a data migration.

## 0. Scope change (2026-10-01)

Vibe-Board began as an automatic clipboard-history recorder. **That design is superseded.** Vibe-Board is now a privacy-first **command library**: a place to save, search and copy terminal commands you use often.

All earlier requirements about the following are **withdrawn**:

- background clipboard observation
- `NSPasteboard.changeCount` polling
- concealed/transient marker filtering
- recording opt-in and pause
- clipboard retention

The following are **prohibited**:

- reading the system clipboard in the background
- any recording mode
- any setting that could re-enable one

**Legacy data:** the earlier build may have stored clipboard history in the `clipboard_entries` table of the same database.

- It is preserved as-is.
- It is never displayed, imported, migrated or pruned by the app.
- The user can review or delete it only by running `scripts/legacy_history.py` (§5.3).

## 1. Vision and guardrails

Vibe-Board is a fast, local-only macOS utility that lives in the menu bar. The user saves commands they reuse (shell, git, docker, kubectl and so on) with a title, optional description and category, finds them with search and filters, and copies one to the clipboard with an explicit action. Then the user pastes and runs it themselves.

**Non-negotiable:**

- Data:
  - No account, server, sync, telemetry, analytics or network calls.
  - No AI integration.
- Clipboard:
  - **Never read the system clipboard** on Vibe-Board's own initiative: not in the background, and not while the user is browsing or searching. The only read is the standard paste action (Cmd+V or the context menu) inside an edit field, which the user performs.
  - **Clipboard writes happen only on an explicit copy action** (Copy button, Enter, or double-click).
  - **No keyboard injection or automatic pasting** into Terminal or any other app.
- Commands:
  - **Never execute command text.** No shell, `subprocess`, `os.system`, `QProcess`, `eval`, or command parsing or expansion. Commands are opaque data.
  - **No automatic import** of `~/.zsh_history`, `~/.bash_history` or other shell history.
- Privacy:
  - **Never log** command text, titles, descriptions, search terms or clipboard data.
  - Don't request Accessibility, Input Monitoring or other permissions unless a verified feature truly needs them.

## 2. Product scope, ordered

### MVP (implemented: functional UI)
- [x] Menu-bar icon. Left-click toggles the command palette window; right-click shows Open / New Command / Quit.
- [x] Closing the window keeps the app in the menu bar. If no menu bar icon is available, closing quits.
- [x] Command palette window: command cards, pinned first then by title, plus a detail pane in wide windows (see §3).
- [x] Add a command by typing or pasting into a form. Title and command are required; description and category are optional.
- [x] **Explicit Save.** Typing alone persists nothing, and Enter in a field doesn't save. Cancelling with unsaved changes asks before discarding.
- [x] Edit an existing command.
- [x] Delete, with a confirmation.
- [x] Search title, command and description. It is case-insensitive and Unicode-aware, and `%`/`_` and SQL text are treated literally.
- [x] Filter chips: All, Pinned, each category, or Uncategorized. A new category reuses an existing one's spelling when they differ only in case.
- [x] Pin and unpin.
- [x] Copy to the clipboard with the Copy button, Enter, or double-click. A single click only selects.
- [x] Multiline commands are preserved exactly: whitespace, tabs, CRLF, trailing newline and Unicode.
- [x] States:
  - loading
  - empty library
  - no matches
  - nothing selected
  - storage error banner
  - clipboard-write error
- [x] Best-effort secret policy on save (§5.2).
- [x] Single instance. A second launch shows the existing window.

### Modern UI redesign (implemented)
- [x] Compact command palette:
  - rounded command cards: title, category pill, pin marker, monospace preview block, description, "+N more lines"
  - subtle hover, selected and focused states
- [x] Prominent search that has focus whenever the window opens. Typing on the list goes to search.
- [x] Filter chips. ⌘] and ⌘[ cycle through them.
- [x] Modern editor:
  - stacked labeled fields, with required ones marked
  - monospace command field with a live line and character count
  - inline errors and a secret notice
  - Save as the primary action and ⌘S, with no default button
- [x] Visible copy confirmation (toast). Optional hide-after-copy.
- [x] Esc clears an active search, then dismisses.
- [x] Themes:
  - Dark, Light and Match System (follows the macOS appearance live)
  - token-based QSS + QPalette on Fusion
  - a forced scheme also drives native chrome
- [x] Responsive layout:
  - the detail pane shows at 760 px and wider
  - the shortcut hints show at 640 px and wider
  - the action bar is always present
  - minimum size 420×380
  - logical px and painted icons, so display scaling works
- [x] macOS unified title bar (Qt `ExpandedClientAreaHint` + `NoTitleBarBackgroundHint`) with a safe-area drag strip. It can be turned off in Settings.
- [x] Settings dialog:
  - theme
  - card preview lines (1–8)
  - hide after copy
  - unified title bar
  - a privacy statement
  - **no** recording, clipboard-reading, execution or login options

### Later (needs a verified design first)
- [x] Global shortcut **to show or hide the window only**, default ⌃⌥⌘V, configurable in Settings. It uses Carbon `RegisterEventHotKey` and needs no permissions (technical decisions D15). It never injects keystrokes.
- [x] Window placement: opens on the display under the pointer and remembers size and position when they're still valid; never off-screen (D17).
- [x] Blended title-bar gap fixed at the root cause (D16).
- [ ] Explicit, user-initiated import/export of the library (a JSON file, with a warning). Never automatic, and never from shell history.
- [ ] Placeholder variables in commands (for example `{branch}`), filled in a dialog before copying. Still copy-only.
- [ ] Launch at login: **opt-in only**, after the packaged `.app` exists. Not enabled by default and not implemented now.

## 3. User experience and design system

**Style direction:** a refined, native-feeling macOS utility. Restrained surfaces, clear keyboard affordances, no web-dashboard look.

**Command palette (`ui/palette_window.py`)**
- **Title strip:** empty and draggable. It appears only when the unified title bar is on, sized from the window's safe-area margin.
- **Header:**
  - terminal glyph, "Commands" and the count ("N commands" or "N of M")
  - **Add Command** (primary)
  - Settings (gear)
- **Error banner:** dismissible, with an alert glyph and a danger tint.
- **Search:** large field with a leading search icon and a clear button. It has focus whenever the window opens.
- **Filter chips:** a horizontally scrolling, exclusive row: All, Pinned, each category, Uncategorized.
- **Body:**
  - card list (`ui/command_list.py`: model + painted delegate)
  - detail pane: title, meta, description, full read-only monospace command and line count
- **Action bar:**
  - **Copy** (primary), **Edit**, **Pin/Unpin**, **Delete…** (danger)
  - native-text shortcut hints
- **Toast:** a "Copied '…'" confirmation for 2.4 s, from a one-shot timer started by the user action.
- **Empty states:**
  - loading
  - empty library (with Add Command)
  - no matches (with Clear Filters)
  - load error
  - nothing selected
- **Shortcuts** (window-local; ⌘ on macOS, Ctrl elsewhere):
  - ⌘N new
  - ⌘E edit
  - ⌘P pin
  - ⌘⌫ delete
  - ⌘F / ⌘L search
  - ⌘, settings
  - ⌘] / ⌘[ cycle filters
  - ↑/↓ navigate
  - Enter copy
  - Esc clear, then dismiss
  - ⌘Q quit
- **Editor shortcuts:** ⌘S save; Esc cancels (with a discard prompt if needed).
- **Plain text only:** every label and card that shows user data is drawn as plain text, so markup renders literally.

**Theme tokens (implemented in `ui/theme.py`; the WCAG contrast is unit-tested)**
- Dark:
  - background `#10131B`
  - surface `#1A1F2A`
  - hover `#242D3B`
  - border `#333C4C`
  - text `#F4F6FB`
  - muted `#A1AABA`
  - accent `#8295FF`
  - success `#53C6A0`
  - danger `#F07178`
  - extra tokens: code `#131824`, selected `#252E4A`, on-accent `#0B0E15`, danger-bg `#3A1E24`
- Light:
  - background `#F7F8FB`
  - surface `#FFFFFF`
  - border `#E2E6EF`
  - text `#1B2433`
  - muted `#606A7C` (darkened from `#667184` so it keeps 4.5:1 on selected cards)
  - accent `#5669E9`
  - danger `#C5363E`
  - success `#17795A`
  - extra tokens: code `#F2F4F8`, selected `#E8EBFD`, hover `#EEF1F7`, danger-bg `#FDECEE`
- Typography:
  - The system UI font.
  - The system fixed-pitch font for command text.
- Spacing scale: 4/8/12/16/24 px.
- Minimum click target: 32–36 px.
- Icons:
  - Draw them with QPainter or use bundled SVGs. No emoji icons.
  - The menu-bar icon is a template image.

**Accessibility:**
- Focus:
  - a 2 px accent focus ring on inputs, buttons and chips
  - a thicker accent border on the focused selected card
- Accessible names and descriptions on search, the list, buttons, chips, editor fields, the toast and the banner.
- Cards expose `AccessibleTextRole`: title, pinned, category, first line and line count.
- Text contrast is at least 4.5:1, tested for every text/background token pair.
- No color-only state: pin is a glyph plus "Pinned" in the details, and errors use an icon plus text.

## 4. Architecture

```
UI (ui/palette_window.py, command_list.py, command_editor.py, settings_dialog.py, theme.py)
                                                      pure views: render state, emit intents
    |  Qt signals
    v
Controller (app.py: ClipFlowController)               wiring, menu bar, preferences, user actions
    |                                 \
    v                                  v
services/command_service.py            platform/clipboard.py → platform/macos_clipboard.py
  validation, normalization,             ClipboardWriter: write_text() only (no read API)
  secret policy (services/secret_scanner.py)
    |
    v
repositories/command_repository.py     parameterized SQL on `commands`
repositories/database.py               connection, permissions, migrations (user_version)
repositories/preferences_repository.py ui.* keys in app_settings (explicit whitelist)
repositories/legacy_history.py         used ONLY by scripts/legacy_history.py
```

**Rules**
- Views never run SQL or touch AppKit. The service never touches Qt widgets.
- There are no background timers, threads or polling. After startup the app only reacts to user actions. The only timers are one-shots: the initial load, the toast hide, and the optional hide-after-copy, the last two started by a copy.
- Errors (locked or full disk, clipboard write failure) are shown in the window and never crash the app. Logs record the exception **type** only.
- Single instance via `QLocalServer`. A per-user socket is used, and it is not a network socket.
- Preferences are read and written only through an explicit `ui.*` key whitelist (`PreferencesRepository.KEYS`). They're written only when the user presses Save in Settings. Legacy `recording_*` keys in `app_settings` are never selected. No setting may relate to recording, clipboard reading, execution or launch at login.
- Shared UI and service code is pure Qt and portable. AppKit/PyObjC imports live only in `platform/macos_*.py`, which a test enforces.

**Modules**
```
main.py                       tiny entry point
src/clipflow/app.py           controller + main()
src/clipflow/config.py        paths, limits, logging
src/clipflow/single_instance.py
src/clipflow/models/{command.py, preferences.py}
src/clipflow/platform/{clipboard.py, macos_clipboard.py, macos_app.py}
src/clipflow/repositories/{database.py, command_repository.py, preferences_repository.py, legacy_history.py}
src/clipflow/services/{command_service.py, secret_scanner.py}
src/clipflow/ui/{palette_window.py, command_list.py, command_editor.py, settings_dialog.py,
                 theme.py, widgets.py, icons.py}
scripts/macos_probe.py        menu-bar click/activation probe (no clipboard access)
scripts/legacy_history.py     summary / export / secure delete of legacy history
scripts/render_ui_states.py   offscreen PNG render of every UI state in both themes
src/clipflow/selftest.py      `--self-test`: core flows inside the packaged runtime (throwaway data only)
packaging/ClipFlow.spec       PyInstaller spec (bundle id, Info.plist, arm64, excluded Qt plugins)
packaging/build_macos.sh      clean build + icon + verification
packaging/make_icon.py        placeholder .icns from the painted app icon
packaging/verify_bundle.py    identity/arch/signature/forbidden-file checks
packaging/smoke_test_app.sh   LaunchServices launch test of the built .app
tests/…                       pytest + pytest-qt; tests/manual_macos_checklist.md
```

## 5. Storage, security and privacy

### 5.1 Storage
The database lives at `~/Library/Application Support/ClipFlow/clipflow.sqlite3`. This can be overridden with `CLIPFLOW_DATA_DIR` for development.

Permissions:
- The directory is `0700`.
- The database file is created `0600` before SQLite opens it, so the `-wal`/`-shm` sidecars inherit `0600`. Existing files are tightened on every open.

Other details:
- WAL journaling with `busy_timeout`.
- Explicit transactions.
- Parameterized queries only.
- Schema migrations are tracked by `PRAGMA user_version`. They are idempotent and additive, and a newer schema is refused.

```sql
-- v2 (current). v1 tables (clipboard_entries, app_settings) are kept unchanged.
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    command TEXT NOT NULL CHECK (length(command) > 0),
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    is_pinned INTEGER NOT NULL DEFAULT 0 CHECK (is_pinned IN (0,1)),
    created_at TEXT NOT NULL,      -- UTC ISO 8601
    updated_at TEXT NOT NULL       -- UTC ISO 8601; pinning does not change it
);
CREATE INDEX IF NOT EXISTS idx_commands_pin_title ON commands(is_pinned DESC, title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_commands_category ON commands(category);
```

Limits:
- Title: 120 characters.
- Category: 50 characters.
- Description: 2000 characters.
- Command: 32 KiB of UTF-8.

Normalization: the title, category and description are trimmed. The command text is stored **exactly** as entered.

**The database is not encrypted at rest.** File permissions only stop other macOS users from reading it.

### 5.2 Secret policy (best effort)
Every field is scanned when the user saves, and again on each update.

- **Blocked (cannot be saved):** private key blocks (`-----BEGIN … PRIVATE KEY-----`, including OpenSSH, RSA, EC, PGP and encrypted variants).
- **Warning ("Save Anyway" / "Go Back", default Go Back):**
  - AWS access key IDs
  - GitHub tokens (`ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_` and `github_pat_`)
  - GitLab tokens (`glpat-`)
  - Slack tokens (`xox?-`)
  - Stripe live keys
  - Google API keys (`AIza…`)
  - `sk-…` API keys
  - JSON Web Tokens
  - passwords in URLs (`scheme://user:pass@`)
  - `Authorization: Bearer|Basic|Token …` headers
  - `*PASSWORD|SECRET|TOKEN|API_KEY…=value` assignments
  - `--password|--token|--api-key|--secret` options and `sshpass -p`
- **Placeholders are allowed:** `$VAR`, `${VAR}`, `$(cmd)`, `<value>`, `{{x}}`, `****`.
- Findings report only the kind of secret and the field it was found in. The matched value is never shown or logged.
- **Limitations (state them in the UI and the docs):**
  - It recognizes formats, not secrets. An ordinary password typed as a plain argument (for example `mysql -pHunter2`) is **not** recognized.
  - Unknown token formats aren't recognized.
  - Secrets split across lines, encoded, or stored in variables defined elsewhere aren't recognized.
  - A warning can be overridden.
  - Users should keep secrets in environment variables or a password manager, and reference them as `$VAR`.

### 5.3 Legacy clipboard history
- Location: the `clipboard_entries` table, plus `recording_consent`/`recording_paused` in `app_settings`, in the same database file.
- The app never queries this table and never runs retention on it.
- Run `scripts/legacy_history.py` to deal with it:
  - `summary`: counts and dates only.
  - `export PATH`: writes a new `0600` JSON file and refuses to overwrite one.
  - `delete`: requires typing DELETE. It uses `secure_delete`, `VACUUM` and a WAL truncate so the removed text doesn't remain in free pages.
- The script never prints entry contents to the terminal.

## 6. macOS integration
- **Menu bar:** `QSystemTrayIcon` without `setContextMenu()`. Left click (`Trigger`) toggles the window; `Context` opens a manual `QMenu`. Click behavior must be verified on a real Mac with `scripts/macos_probe.py`.
- **Activation:** `NSApplication.activate()` is called only in response to a user action.
- **Clipboard:** `NSPasteboard.clearContents()` + `setString:forType:`. There is no read path. Writing doesn't trigger macOS's paste-privacy prompt.
- **Dock:** the Dock icon is kept until focus behavior is verified.
- **No launch at login.** Nothing is registered with `SMAppService` or LaunchAgents.

## 7. Quality and testing
Automated tests use `pytest`, `pytest-qt` with the offscreen platform, temporary SQLite databases, and a fake clipboard that records writes and counts any read attempt. macOS-native tests use a private, uniquely named `NSPasteboard` and never the user's clipboard.

They must cover:
1. The clipboard monitor, history and retention modules don't exist.
2. Source code contains no pasteboard-read APIs, and the writer exposes only `write_text`.
3. Launch and restart, including with a legacy database that has `recording_consent=true`, start no active timers and never read the clipboard.
4. Commands persist only after Save. Enter doesn't save. Cancel with changes prompts before discarding.
5. CRUD, search (all three fields, Unicode, literal wildcards), category filter, pinning order, and copy via button, double-click and Enter. Selecting or searching never copies.
6. Exact round-trip of multiline, Unicode and whitespace text through SQLite, the UI and a real `NSPasteboard`.
7. Execution traps: with `subprocess`, `os.system`/`exec*`/`spawn*`/`posix_spawn` and `QProcess` patched to fail, a dangerous command is stored and copied but never run. A static AST scan forbids execution and network modules.
8. The secret policy blocks and warns as specified, allows placeholders, and never puts values in findings.
9. Logs never contain command text, titles, search terms or tokens.
10. Legacy history survives the v1→v2 migration byte-for-byte, is never displayed, and is deleted only through the script, which scrubs the bytes.
11. Database files are `0600` (including sidecars) and the directory is `0700`.
12. UI:
    - loading, empty, no-match and error states
    - filter chips (All, Pinned, category, Uncategorized), and chips aren't rebuilt when nothing changed
    - Esc clears then dismisses; type-ahead; arrow and filter-cycle shortcuts
    - the toast appears on copy
    - the responsive detail pane and hints
    - cards grow with the preview-line setting and expose accessible text
    - markup renders literally
13. Theme and preferences:
    - every text/background token pair is at least 4.5:1 (text at least 7:1)
    - QSS includes focus rules
    - dark, light and system modes, including following OS appearance changes
    - preferences round-trip through `ui.*` keys only; bad values are ignored or clamped
    - legacy `recording_*` keys are never read or written
    - Settings Save persists and applies, Cancel changes nothing
    - Settings offers no recording, execution or login options
14. Portability: AppKit/PyObjC is imported only by `platform/macos_*.py`.

Manual checks are in `tests/manual_macos_checklist.md`. Never claim a manual check passed without running it on a real Mac.

## 8. Milestones
- **Phase 1: security refactor (done).**
  - Clipboard monitoring, recording UI, onboarding, retention and the settings repository were removed.
  - The clipboard adapter is now write-only.
  - The legacy data path is preserved and isolated.
  - Permissions were hardened and the Ctrl+C handling was fixed.
- **Phase 2: command library (done, functional UI).** §2 MVP.
- **Phase 3: modern UI redesign (done).** Palette, cards, themes, Settings and responsive layout. **Gate:** keyboard-only use and every control wired to real state. This is automated-tested. The live checks are in manual checklist section U.
- **Phase 4: hardening (mostly done).**
  - Done: the global shortcut after a spike (D15), the title-bar fix (D16), and window placement (D17).
  - Open: the Dock-icon decision.
  - **Gate:** no new permissions (verified: none needed), and manual checklist sections H, W and T pass.
- **Phase 5: packaging (done for local use).**
  - `./packaging/build_macos.sh` builds the PyInstaller onedir `.app` (arm64, about 80 MB, ad-hoc signed, placeholder icon) and verifies it with `packaging/verify_bundle.py`.
  - Data stays in Application Support, outside the bundle.
  - `./packaging/smoke_test_app.sh` launches it through LaunchServices against a throwaway database and runs the in-app `--self-test`.
  - **Gate:** launches through LaunchServices without a terminal (automated). Finder, Spotlight, menu-bar and keyboard use are on manual checklist section P.
  - Developer ID signing and notarization are **not** done (see `docs/packaging.md`).

## 9. Development commands
```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt && python -m pip install -e . --no-deps
python -m pytest -q
python -m ruff check . && python -m ruff format --check .
python main.py
```
`pyproject.toml` holds the dependency ranges. `requirements.txt` is the generated, pinned lock.

## 10. References
- Apple `NSPasteboard`: https://developer.apple.com/documentation/appkit/nspasteboard
- Qt `QSystemTrayIcon`: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html
- SQLite `secure_delete`: https://www.sqlite.org/pragma.html#pragma_secure_delete
- PyInstaller macOS bundles: https://pyinstaller.org/en/stable/usage.html
- Apple notarization: https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution
