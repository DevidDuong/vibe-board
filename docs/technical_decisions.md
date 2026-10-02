# Technical decisions

## Environment (verified 2026-10-01)

| Item | Value |
|---|---|
| macOS | 26.5.2 (build 25F84), Apple Silicon `arm64` |
| Python | 3.13.1 from python.org (universal2, running natively as arm64) |
| PySide6 / Qt | 6.11.2, platform plugin `cocoa` |
| PyObjC | 12.2.2 (`pyobjc-framework-Cocoa`) |
| `QSystemTrayIcon.isSystemTrayAvailable()` | `True` |

Reproduce with `python scripts/macos_probe.py --check`.

## D0: Scope change: clipboard recorder → command library (2026-10-01)

The product changed from automatic clipboard history to a command library, so the recording path was **removed rather than disabled**. A disabled monitor could be re-enabled by a preference, a regression or a merge mistake. A deleted monitor can't.

**Removed:**
- `services/clipboard_monitor.py`, `services/history_service.py` and `services/retention_service.py`
- `repositories/history_repository.py` and `repositories/settings_repository.py`
- `models/{clipboard_entry,settings}.py` and `platform/pasteboard.py`
- `ui/{popup,history_list,onboarding_dialog}.py`
- `scripts/phase0_probe.py`, which read clipboard contents. It was replaced by `scripts/macos_probe.py`, which never touches the clipboard.

**Reused:**
- `repositories/database.py`: connection setup, migrations, transactions, and the Unicode `cf_contains` search function
- `config.py` (paths, private directories, privacy-safe logging)
- `single_instance.py`
- `ui/icons.py`
- `platform/macos_app.py`
- the menu-bar wiring in `app.py`

**Retention removed:** the old app ran retention on every start, which would have deleted legacy entries after 30 days. That code is gone, so legacy data is now preserved indefinitely.

**Guarded by tests:** `tests/test_security.py` asserts:
- the removed modules can't be imported
- the source contains no pasteboard-read APIs
- the writer exposes only `write_text`
- launch and restart, even with `recording_consent=true` persisted, leave no active timers and make no clipboard reads

The old recording design's findings (`changeCount` semantics, pasteboard privacy prompts) are kept in the original spec's history only. They don't apply any more.

## D1: Clipboard: write-only adapter

- `ClipboardWriter` is a protocol with a single method, `write_text`. `MacClipboardWriter` calls `clearContents()` followed by `setString:forType:` on the general pasteboard.
- No read method exists anywhere in ClipFlow's code.
- Writing doesn't trigger macOS's "paste from other apps" prompt, which applies to reads only.
- Writes happen only from `ClipFlowController.copy_command`, which is reached from the Copy button, Enter, or a double-click.
- **Caveat:** Qt's own text fields read the clipboard when the user pastes into them (Cmd+V or the context menu). That read is a user action, and ClipFlow code is not involved.
- **Caveat:** on app activation, Qt's Cocoa clipboard integration may check the pasteboard's change counter in order to emit `QClipboard.dataChanged`. Change-counter checks don't read contents. ClipFlow never connects to that signal, and its own code makes no `changeCount` call.

## D2: Commands are inert data

- No module imports `subprocess`, `pty`, `shlex`, `multiprocessing`, `socket`, `http`, `urllib` and so on, or uses `os.system`, `os.exec*`, `os.spawn*`, `QProcess`, `eval` or `exec`. An AST test enforces this.
- `PySide6.QtNetwork` is used only for `QLocalServer`/`QLocalSocket` in `single_instance.py`, which is a per-user Unix-domain socket, not a network socket.
- A runtime test patches the execution entry points so they fail if called. It then saves, copies, searches and edits a command that would create a marker file if run. The marker never appears.
- Copying never pastes and never injects keystrokes.
- Note for the user: in Terminal, a pasted command runs only after pressing Return. zsh's bracketed paste also stops an embedded trailing newline from executing. Other shells may differ, so the manual checklist covers it.

## D3: Storage

- The database is at `~/Library/Application Support/ClipFlow/clipflow.sqlite3`. The schema is version 2: v1 tables are kept, and the `commands` table was added.
- The migration is additive and idempotent. A newer schema is refused.
- **Permissions:** the database file is pre-created with `0600` before SQLite opens it. SQLite gives `-wal`/`-shm` files the main file's mode, and the first build created the main file `0644` and chmod-ed it afterwards, which left `-shm` at `0644`. Every open now also tightens existing sidecars. The directory is `0700`.
- Search runs `cf_contains`, which uses Python `casefold()`, over title, command and description. Wildcards and SQL text are treated literally.
- Ordering: pinned first, then title (`COLLATE NOCASE`), then id.
- Title, category and description are trimmed. The command text is stored verbatim, including leading and trailing whitespace and newlines.
- The database isn't encrypted at rest.

## D4: Secret policy

- `services/secret_scanner.py` runs a fixed set of regexes, and `CommandService` applies them on every create and update.
- Private key headers are blocked. Recognizable tokens and passwords produce a warning, which requires an explicit **Save Anyway** in the UI (`acknowledge_warnings=True` in the service).
- Values that look like placeholders are ignored: `$VAR`, `${…}`, `$(…)`, `<…>`, `{{…}}`, `****`, `xxxx`.
- Findings carry only the kind of secret and the field. Messages and logs never include the matched value.
- **Limitations:**
  - It is pattern matching only.
  - It misses ordinary passwords passed as plain arguments (`mysql -pX`, `curl -u user:pass`), unknown token formats, and encoded or split secrets.
  - It can raise false positives on look-alike strings.
  - It is documented as best effort in the UI note, the README and the spec.

## D5: Legacy history isolation

- `clipboard_entries` and the `recording_*` rows in `app_settings` are left byte-for-byte unchanged. A test compares full table dumps before and after the migration and an app lifecycle.
- The running app never imports `repositories/legacy_history.py`.
- `scripts/legacy_history.py` provides `summary` (metadata), `export` (a new `0600` JSON file; it refuses to overwrite) and `delete`.
- `delete` requires typing DELETE. It runs `PRAGMA secure_delete=ON`, `DELETE`, `VACUUM` and `wal_checkpoint(TRUNCATE)`, and a test confirms the old text no longer appears anywhere in the database file bytes.

## D6: Menu bar and window

- `QSystemTrayIcon` is used without `setContextMenu()`: on macOS that would replace left-click activation. Left click (`Trigger`) toggles the window; `Context` opens a manual `QMenu`.
- **Unverified until someone clicks it on this Mac.** Run `scripts/macos_probe.py`.
- The palette is a normal top-level window, which suits forms and dialogs better than an auto-hiding popup. It can optionally use the unified title bar (D11).
- Close or Escape hides the window. If no menu-bar icon is available, closing quits instead, so the user is never stranded.
- The add/edit dialog is window-modal (`open()`, non-blocking). Its buttons are never the default button, so Enter can't save by accident.
- Every label that shows user data uses `Qt.PlainText`, so titles containing `<b>` render literally.

## D7: Lifecycle

- After startup there are **no timers, threads or polling**. The only timers are one-shots: the initial load, the toast hide, and the optional hide-after-copy. The last two are started by a user's copy action.
- Ctrl+C in the launching terminal now terminates the app (`SIGINT` → `SIG_DFL`). Previously, the custom `sys.excepthook` logged `KeyboardInterrupt` and kept running. It now quits on `KeyboardInterrupt`.
- No launch at login: there is no `SMAppService` or LaunchAgent registration.
- Single instance: a second launch asks the first to show its window, then exits.

## D8: Global hotkey: options considered (implemented in D15)

Superseded by D15, which records the spike results. Two corrections to the table below: the API does **not** report conflicts with other apps, and the macOS 15 Option-only rejection wasn't observed on macOS 26.5.

| Option | Permissions | Notes |
|---|---|---|
| `QShortcut` | none | Works only in a focused ClipFlow window. Not global. Used only for in-window shortcuts. |
| Carbon `RegisterEventHotKey` (`ctypes`) | **none** | The preferred option. Reports conflicts. Since macOS 15, combinations whose only modifiers are Option or Option+Shift are rejected. |
| `NSEvent` global monitor / `CGEventTap` | Accessibility / Input Monitoring | Rejected: too broad, and the spec forbids keyboard monitoring and injection. |

Avoid Cmd+Shift+V. In many apps it is Paste and Match Style.

## D10: UI redesign (2026-10-01)

- **Palette structure:**
  - The window `ui/palette_window.py` stays a pure view.
  - Cards are a `QListView` with a `QAbstractListModel` and a painting `QStyledItemDelegate` (`ui/command_list.py`), rather than per-row widgets. That keeps scrolling cheap and makes the hover, selected and focused states precise.
  - The delegate draws all user text as plain text through `drawText`. The model's Display/Accessible text is a plain summary for screen readers.
- **Theme:**
  - `ui/theme.py` builds a `QPalette` plus QSS from the tokens on the **Fusion** style. The native macOS style ignores parts of QSS, while Fusion renders consistently on macOS and Windows.
  - Light and Dark also call `styleHints().setColorScheme()`, so native chrome such as the title bar and message boxes match. Match System calls `unsetColorScheme()` and re-applies on `colorSchemeChanged`.
- **Combo-box chevrons:** QSS can't draw the arrow once the drop-down subcontrol is restyled. A themed chevron is rendered to a private `QTemporaryDir` (1x and @2x) and referenced from the QSS. Only icon pixels are written to disk.
- **Contrast:** a unit test enforces WCAG AA for every token pair. It caught that the spec's light `muted` (`#667184`) was only 4.16:1 on a selected card, so it is now `#606A7C`. Light `danger` is `#C5363E`, for 4.64:1 on its banner tint.
- **Visual verification:**
  - `scripts/render_ui_states.py` renders every state offscreen (`WA_DontShowOnScreen` + `grab()`).
  - This found and fixed several issues: stale filter chips painted over a tinted block, a clipped chip row, missing or boxed combo arrows, a misaligned editor column, and disabled buttons that looked enabled.
  - The clipped-row fix is confirmed by renders, but reverting the individual changes didn't reproduce it headlessly. Its test therefore checks the invariant only, and the manual check U-10 stays.
- **Responsive layout:** the detail pane shows at 760 px and wider, and the shortcut hints at 640 px and wider. The action bar always stays, so narrow windows lose no functionality.
- **Escape:** clears an active search first, then dismisses (Spotlight-like).
- **Copy confirmation:** a toast shown for 2.4 s. Its one-shot timer starts only on a user action, so there is still no idle timer.

## D11: Unified title bar (macOS)

- It uses Qt 6.9+ `Qt.WindowType.ExpandedClientAreaHint` + `NoTitleBarBackgroundHint`. That is pure Qt, with no NSWindow hacks.
- **Superseded by D16.** The original design added a `title_strip` spacer sized from the safe area. That double-counted the title bar and caused the blank band; it's been removed.
- **Verified programmatically on macOS 26.5:**
  - safe area top is 28 px, and the strip plus margin is at least 28 px
  - toggling at runtime removes the flags, re-shows the window, and collapses the strip
- **Not verified:** the visual result (traffic lights over the strip) and how dragging feels. These are on the manual checklist (U-1), and Settings offers a toggle back to the standard title bar.
- It is ignored on non-Cocoa platforms.

## D12: Preferences

- `UiPreferences` holds `theme`, `preview_lines` (1–8), `hide_after_copy`, `unified_title_bar`, and (from D15) `hotkey_enabled` and `hotkey`.
- `PreferencesRepository` reads and writes only the whitelisted keys `ui.theme`, `ui.preview_lines`, `ui.hide_after_copy`, `ui.unified_title_bar`, `ui.hotkey_enabled` and `ui.hotkey`.
- Window geometry is UI *state*, not a preference. It's stored separately under `ui.window_geometry` (D17).
- Values must match the expected type exactly, and out-of-range values are clamped.
- Nothing is written until the user presses Save in Settings. A fresh launch writes no preference rows (confirmed on a real launch).
- On platforms where the unified title bar doesn't apply, saving Settings keeps the stored value instead of resetting it.

## D13: Standalone app packaging (2026-10-02)

- **PyInstaller 6.22.3, onedir + `BUNDLE`, windowed, `target_arch="arm64"`.** The python.org Python and the PySide6 wheels are universal2; PyInstaller thins every collected binary to arm64, and the verifier checks this.
- **Onedir rather than onefile:** onefile unpacks to a temp folder on every launch, which is slow and breaks the bundle's signature model. Onedir inside `.app` is PyInstaller's supported macOS layout.
- **No data files are bundled** (`datas=[]`). Icons are painted and QSS is generated in code, and the combo-box chevrons go to a `QTemporaryDir` at runtime. So resource-path resolution inside the bundle isn't a problem: there are no bundle resources to resolve except the `.icns`.
- **Excluded Qt plugins:**
  - virtual-keyboard input context (it pulls in QtQuick, QtQml and QtVirtualKeyboard)
  - `qpdf` image format (QtPdf)
  - TLS backends and network information, since ClipFlow makes no network connections
  - the TUIO touch plugin

  This took the bundle from about 100 MB to about 80 MB. The packaged self-test passes without them.
- **Identity:** bundle id `local.devidduong.clipflow`, a personal placeholder to change before any public release. `LSUIElement=false`, so the Dock icon is kept pending the Phase 4 decision. `LSMinimumSystemVersion` is 13.0. There are no usage descriptions and no login-item keys.
- **Icon:** the placeholder is `ui.icons.app_icon_pixmap` (a terminal glyph on an indigo tile), rendered into an `.iconset` and turned into an `.icns` with `iconutil`. A designed `packaging/ClipFlow.icns`, if present, wins automatically.
- **Signing:** ad-hoc, which PyInstaller applies and Apple Silicon requires. `spctl` rejects the app, as expected. A local build carries no quarantine attribute, so Gatekeeper doesn't intervene. Developer ID signing and notarization are documented in `docs/packaging.md` but not done.
- **Data location:** the same as source runs (`~/Library/Application Support/ClipFlow`). Verified: the database is created outside the bundle, and the code signature is still valid after the app runs, so nothing was written into the bundle.
- **`--self-test`** (`clipflow/selftest.py`):
  - Exercises the core flows inside the frozen runtime, because GUI automation would need Accessibility permission.
  - Hard guard: it exits with 2 unless `CLIPFLOW_DATA_DIR` points somewhere other than the real library.
  - Copies go to a private pasteboard created in `platform/macos_clipboard.py` (the AppKit import boundary still holds), and that pasteboard is never read.
  - It renders screenshots of the packaged UI.
- **Lifecycle fixes found while packaging:**
  - Launching again from Spotlight, Finder or the Dock only *re-activates* a running app. `applicationStateChanged(Active)` now shows the hidden palette, so a relaunch is never a silent no-op.
  - Dismissing the palette calls `NSApp.hide()`, so focus returns to the previous app. `activate_app()` un-hides it again.
  - SIGTERM (`kill`, Activity Monitor) and SIGINT now quit gracefully: `signal.set_wakeup_fd` writes to a pipe watched by a `QSocketNotifier`. There's no polling timer and no `socket` import. Previously SIGTERM killed the app immediately.
- **Verified on macOS 26.5:** a Cocoa `NSApp.terminate:` (the path used by Dock Quit, the app-menu Quit and logout) quits cleanly even though the palette's `closeEvent` hides instead of closing. I had suspected the ignored close would cancel the quit; it doesn't.
- **LaunchServices quirk:** an `open` issued the instant after a quit that followed a second-instance hand-off was ignored, because LaunchServices still listed the old instance. Relaunching 0.5–2 s later works. The smoke test pauses 1 s, as a person would.

## D14: Display name "Vibe-Board" (2026-10-02)

- **What changed:** the user-visible name is now `clipflow.APP_NAME = "Vibe-Board"`. That covers:
  - the window title (the text in the title bar) and its accessible name
  - the menu-bar tooltip and "Quit Vibe-Board"
  - error dialogs, the editor's secret notice and the Settings privacy text
  - log lines
  - the `.app` bundle: `Vibe-Board.app`, its executable, `CFBundleName` and `CFBundleDisplayName`, which are what the Dock, Finder, Spotlight, ⌘Tab and the app menu show
- **Single source:** the PyInstaller spec, `build_macos.sh`, `verify_bundle.py` and `smoke_test_app.sh` all read `APP_NAME` from the package.
- **Storage is decoupled from the name:** `config.STORAGE_NAME = "ClipFlow"`.
  - Before this, `default_paths()` built both folders from `APP_NAME`, so a plain rename would have pointed the app at a new, empty `Application Support/Vibe-Board` folder and the user's commands would have seemed to disappear.
  - The library and logs stay where they are, and no migration is needed.
  - The self-test guard uses `STORAGE_NAME`, so it still refuses the real library.
- **Kept on purpose:**
  - the `clipflow` package name
  - the `CLIPFLOW_*` variables
  - the bundle id `local.devidduong.clipflow`, so macOS treats the renamed bundle as the same app
  - the single-instance key, which is derived from the data folder, so old and new builds hand off to each other and never run side by side on one database
  - internal file names (`ClipFlow.spec`, `ClipFlow.icns`)
- **Tests (`tests/test_branding.py`):**
  - the display name
  - that the storage paths still resolve to the `ClipFlow` folders (mutation-tested: making storage follow `APP_NAME` fails it)
  - the window title and visible texts
  - an AST scan that allows the literal `ClipFlow` only as `STORAGE_NAME` (mutation-tested with a hardcoded title)
  - that the spec uses `APP_NAME`

## D15: Global shortcut (2026-10-02)

**Decision:** Carbon `RegisterEventHotKey` + `InstallEventHandler` on the application event target, called through `ctypes` (PyObjC doesn't wrap Carbon).

- It's wrapped by a platform adapter: `platform/hotkey.py` (protocol), `platform/macos_hotkey.py` (Carbon), and `services/hotkey_manager.py` (rules and switching, Qt-free). A Windows backend can implement the same protocol later.
- Qt's QHotkey library uses the same approach inside Qt apps.

**Spike (macOS 26.5, PySide6 6.11, real Cocoa event loop):**

| Check | Result |
|---|---|
| Register ⌃⌥⌘V | `noErr` |
| Same combination again, same process | `-9878` (`eventHotKeyExistsErr`): detected |
| Same combination held by **another process** | `noErr`: **not detected**; macOS accepts both |
| ⌥Space, ⌥⇧V | `noErr` (the macOS 15 Option-only restriction wasn't observed) |
| ⌃⌘Space, an enabled macOS shortcut | `noErr`: **not detected** by registration |
| In-process Carbon hot-key event | reaches our ctypes callback with the right id |
| `CopySymbolicHotKeys` | lists 171 enabled macOS shortcuts and finds ⌘Space and ⌃⌘Space |

**Permissions:**
- None. Accessibility, Input Monitoring and Screen Recording are all unnecessary.
- The unified log shows the WindowServer making 2 Input Monitoring *preflight* checks when the hotkey is registered. A baseline Qt app that registers **no** hotkey triggers the same 2 checks, so they're routine for any GUI app.
- No user-facing request (`preflight=no`) was logged.

**Conflict handling:**
1. Hard rules: ⌘ or ⌃ plus at least one more modifier; supported keys only.
2. A static list of combinations that are always refused (e.g. ⇧⌘V Paste and Match Style, screenshots, log out, lock screen).
3. macOS's *enabled* shortcuts, read live from `CopySymbolicHotKeys`, so the user's custom System Settings shortcuts are respected.
4. Registration errors.

Other apps' global shortcuts can't be detected (no public API). This is documented in Settings and the README.

**Default ⌃⌥⌘V:**
- not ⌘⇧V
- not a macOS shortcut on this Mac (checked live)
- not ⌃⌥Space, which is the input-source switcher and is enabled here
- three modifiers keep it clear of app menus

**Switching:** the new combination is registered **before** the old one is released, and preferences are saved only after registration succeeds. If saving fails, the previous combination is re-activated, so a failed change always leaves the previous shortcut working.

**Delivery:** the callback leaves the Carbon handler immediately (`QTimer.singleShot(0)`).
- Palette hidden or behind other windows: it's shown, brought to the front, and the search field is focused.
- Palette in front: it's hidden.
- An editor or Settings dialog is open: that dialog is brought to the front instead, so unsaved text is never hidden.

**Lifetime bug found and fixed:** the first version installed one Carbon handler per backend instance and never removed it. A garbage-collected instance left Carbon holding a pointer to freed memory, and the next install at the same address failed with `-9866` (`eventHandlerAlreadyInstalledErr`). The handler is now process-wide: installed once, never freed, and dispatching by id.

**Not automatically verifiable:** a real key press reaching the app from other apps. That would need synthetic keyboard input, which is forbidden and itself requires Accessibility. It's covered by manual checks H-1 to H-3 and `scripts/hotkey_probe.py --listen`.

## D16: Blended title bar gap: root cause and fix (2026-10-02)

**Measured on your Retina display before the fix:**

| Source | Value |
|---|---|
| Qt safe-area top | 28 pt |
| AppKit title bar (`frame − contentLayoutRect`) | 28 pt |
| `NSView.safeAreaInsets.top` | 28 pt |
| Header y | **60 pt** (expected 32) |

The values all agreed, so this wasn't a scaling or measurement bug.

**Root cause:** double counting. With `ExpandedClientAreaHint`, Qt already insets a top-level widget's layout by the window's safe area, which is the title bar (`WA_ContentsMarginsRespectsSafeArea`). The palette *also* added a spacer sized from that same safe area, plus a margin and spacing: 28 + 12 + 8 + 12 = 60.

**Fix:**
- The spacer is removed.
- `WA_ContentsMarginsRespectsSafeArea` is set explicitly, so Qt alone applies the inset, and keeps tracking any future title-bar height.
- The top margin in blended mode is now `SPACE_2` (8 pt).
- Clicks under the transparent title bar reach the window itself, which calls `startSystemMove()`, so dragging is preserved. Empty header space drags too.

**Verified on real windows (dark and light):** blended mode puts the header at 36 pt (title bar 28 + gap 8); standard mode at 12 pt.

**Regression tests:**
- An always-on structural test: Qt's safe-area handling is on, and nothing sits above the header.
- An opt-in real-window test (`CLIPFLOW_GUI_TESTS=1`) using `scripts/window_probe.py`. It fails when the duplicate inset is put back (mutation-tested).

## D17: Window placement (2026-10-02)

- **Pure geometry:** `ui/placement.py`, Qt value types only.
- **Active display:** the one under the mouse pointer (`QGuiApplication.screenAt(QCursor.pos())`). This needs no permission; finding the frontmost window of *another* app would need Accessibility.
- **Size:** remembered, then shrunk to fit the display while respecting the minimum.
- **Position:** reused only if the whole window still fits on the active display. Otherwise the window is centred horizontally in the upper fifth.
- **Never partly off-screen:** an 8 pt margin is kept from the usable area (menu bar, Dock). The frame (standard title bar) is counted, using the platform's own frame margins.
- **Stored state:** `ui.window_geometry` (frame position + client size), written when the palette hides and when the app quits.
- **Display changes while open:** on `screenAdded`, `screenRemoved` or `availableGeometryChanged`, a one-shot check pulls a visible window fully back onto a display.
- **Signal cleanup:** app-wide signal connections are released in `shutdown()`. Leaving them connected had let a closed controller react to later events, which surfaced in tests.

## D9: Logging

- The log file is `~/Library/Logs/ClipFlow/clipflow.log` (512 KiB × 3, file mode `0600`).
- It records event kinds, command **ids**, counts and exception **type names**.
- `sys.excepthook` logs the type and stack without the exception message.
- Tests assert that titles, command text, search terms and synthetic tokens never reach the log.
