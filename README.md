# Vibe-Board

Vibe-Board is a menu-bar command library for macOS. You save terminal commands you use often, find them quickly, and copy one to the clipboard when you need it. Everything stays on your Mac.

- **No clipboard monitoring.** Vibe-Board never reads your clipboard. It only writes to it when you click **Copy**.
- **Never runs anything.** Commands are stored and copied as plain text. You paste and run them yourself.
- **Local only.** There is no account, network access or telemetry.

**Status:** the security refactor, the command library, the modern UI redesign and the standalone macOS app are done. Phase 4 hardening is under way: the global shortcut, the title-bar fix and window placement are done; the Dock-icon decision is still open. See [CLIPFLOW_SPEC.md](CLIPFLOW_SPEC.md) and [docs/technical_decisions.md](docs/technical_decisions.md).

> Vibe-Board used to be an automatic clipboard-history recorder. That mode has been removed.
> Any history it recorded is still in the database, untouched. See [Legacy clipboard history](#legacy-clipboard-history).

> **Renamed:** Vibe-Board was called ClipFlow until 2026-10-02. Only the visible name changed.
> Behind the scenes the old name stays so nothing moves:
> - your library is still in `~/Library/Application Support/ClipFlow/`
> - logs are still in `~/Library/Logs/ClipFlow/`
> - the code lives in the `clipflow` Python package
> - the developer variables are still `CLIPFLOW_*`
> - the bundle identifier is unchanged

## Standalone app (no VS Code or Python needed)

```bash
./packaging/build_macos.sh        # builds and verifies dist/Vibe-Board.app (~20 s, ~80 MB, arm64)
./packaging/smoke_test_app.sh     # tests the built app against a throwaway database
```

- **Output:** `~/clipboard-manager/dist/Vibe-Board.app`
- **Install:** quit Vibe-Board, then drag `dist/Vibe-Board.app` onto **Applications** in Finder, or run `ditto dist/Vibe-Board.app /Applications/Vibe-Board.app`.
- **Launch:** press ⌘Space, type **Vibe-Board**, press Return. If it's already running in the menu bar, this brings its window forward.
- **Uninstall:** quit Vibe-Board, then trash `/Applications/Vibe-Board.app`. Your commands stay in `~/Library/Application Support/ClipFlow/` until you delete that folder yourself.

Full details are in [docs/packaging.md](docs/packaging.md): first-launch backup, updating, Gatekeeper, and signing/notarization for a future public release.

## Requirements

- macOS on Apple Silicon. Developed on macOS 26.5.
- Python 3.12 or later. Developed with python.org Python 3.13. The system `/usr/bin/python3` (3.9) is too old.
- VS Code with the Python and Ruff extensions (recommended in `.vscode/extensions.json`).

## Setup

```bash
cd ~/clipboard-manager
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt   # exact pinned versions
python -m pip install -e . --no-deps        # makes `import clipflow` work everywhere
```

`pyproject.toml` is the source of truth for dependency ranges. `requirements.txt` is a generated lock, made with `python -m pip freeze --exclude-editable`.

## Run

```bash
python main.py                                          # your real library
CLIPFLOW_DATA_DIR=./.clipflow-dev-data python main.py   # separate dev library (git-ignored)
CLIPFLOW_DEBUG=1 python main.py                         # also print the diagnostic log
python scripts/macos_probe.py                           # menu-bar click probe (no clipboard access)
python scripts/render_ui_states.py                      # render every UI state to ./ui-review/*.png
python scripts/hotkey_probe.py --listen                 # press ⌃⌥⌘V in other apps; prints each press
python scripts/window_probe.py                          # title-bar spacing on each display (shows windows)
```

Press Ctrl+C in the terminal to quit.

### In VS Code

1. Open the folder. Press Cmd+Shift+P, choose **Python: Select Interpreter**, and pick `./.venv/bin/python`.
2. Open **Run and Debug** (Cmd+Shift+D) and choose one of these:
   - **Vibe-Board (dev data)**
   - **Vibe-Board (real data)**
   - **macOS menu-bar probe**
3. Press F5. Stop the app with **Quit** in the window, **Quit** in the right-click menu-bar menu, Cmd+Q, or the debugger's stop button.

## Using it

The window opens when Vibe-Board starts. After that you can open it in three ways:

- **Global shortcut: ⌃⌥⌘V** (Control-Option-Command-V) from any app.
  - Pressing it shows the palette in front with the cursor in the search field.
  - Pressing it again while the palette is in front hides it and returns focus to the app you were using.
  - If the palette is open but behind other windows, it's brought to the front instead.
  - If an editor is open, the editor comes forward and your unsaved text is kept.
  - You can change or turn off the shortcut in Settings.
- **Menu bar:** left-click the clipboard icon to show or hide the window. Right-click it for Open, New Command… and Quit.
- **Spotlight, Finder or the Dock:** launching Vibe-Board while it's running brings the palette forward.

**Where it opens:** the palette opens on the display under your mouse pointer, at the size and position you last left it.
- If that position no longer fits, it opens centred near the top of that display instead. That happens after unplugging a monitor, changing resolution, or moving to another display.
- The whole window is always kept on screen.

**The palette**
- **Search** has focus whenever the window opens. Start typing to filter by title, command or description. Typing while the list has focus also goes to search.
- **Filter chips:** All, Pinned, each category, and Uncategorized (shown only when some commands have no category). ⌘] and ⌘[ cycle through the chips.
- **Command cards** show the title, a category pill, a pin marker, a monospace preview of the first few lines (adjustable in Settings), the description, and "+N more lines" for longer commands.
- **Wide windows** also show a detail pane with the full command. **Narrow windows** hide it, but the Copy / Edit / Pin / Delete bar stays at the bottom.

**Keyboard**

| Key | Action |
|---|---|
| ↑ / ↓ | Move between commands (from search or the list) |
| Enter / double-click / **Copy** | Copy the selected command. A green "Copied …" confirmation appears. |
| Esc | Clear the search; press again to hide the window |
| ⌘N | Add a command |
| ⌘E | Edit the selected command |
| ⌘P | Pin or unpin |
| ⌘⌫ | Delete (asks first) |
| ⌘F / ⌘L | Focus search |
| ⌘, | Open Settings |
| ⌘Q | Quit |

Right-clicking a card also offers Copy, Edit, Pin and Delete.

**Add or edit a command**
1. Click **Add Command** (⌘N), or select a command and press ⌘E.
2. Fill in the title and the command (multiple lines are fine; the editor shows the line and character count). Category and description are optional.
3. Click **Save** (⌘S). Nothing is stored until you save. Enter in a field never saves, and cancelling with changes asks first.

**Copying never pastes or runs anything.** Switch to your terminal and press ⌘V yourself.

**Settings** (gear icon or ⌘,)

| Setting | Options |
|---|---|
| Theme | Match System (follows macOS light/dark live), Light, Dark |
| Card preview | 1–8 command lines per card |
| Hide the window after copying | Off by default. When on, the "Copied" confirmation shows briefly and the window then hides. |
| Blend the title bar into the window | macOS only, on by default. Turn it off for the standard title bar. |
| Global shortcut | On by default, ⌃⌥⌘V. Click the shortcut and press a new combination; **Reset to Default** restores ⌃⌥⌘V. Use ⌘ or ⌃ plus at least one more modifier. Combinations macOS already uses (e.g. ⌘Space) and common ones such as ⇧⌘V (Paste and Match Style) are refused with the reason. If the new shortcut can't be registered, nothing is saved and the old one keeps working. |

Settings change only when you click **Save**. They're stored as `ui.*` keys next to your commands. Vibe-Board has no recording, clipboard-reading, command-running or launch-at-login setting.

## Security and privacy

- **Storage:** your library is in `~/Library/Application Support/ClipFlow/clipflow.sqlite3`.
  - The folder is `0700` and all database files are `0600`.
  - **The database isn't encrypted.** Treat it like any other file in your home folder.
- **Secret checks:** when you save, Vibe-Board checks every field for recognizable secrets.
  - **Private keys are refused.**
  - These trigger a warning you must confirm with **Save Anyway**:
    - AWS, GitHub, GitLab, Slack, Stripe and Google keys
    - `sk-…` keys and JWTs
    - passwords in URLs
    - `Authorization:` headers
    - `PASSWORD=`/`TOKEN=`-style assignments
    - `--password`/`--token` options
  - Variable references such as `$API_TOKEN` are fine.
- **Limits of the secret checks.** They recognize formats, not secrets:
  - A plain password (`mysql -pHunter2`), an unknown token format, or a secret split across lines will **not** be caught.
  - Keep secrets in environment variables or a password manager, and reference them as `$VAR`.
- **Logging:** the log (`~/Library/Logs/ClipFlow/clipflow.log`) records event types and ids only, never command text, titles or searches.
- **Shell history:** never imported automatically.
- **Launch at login:** not enabled.
- **Permissions:** Vibe-Board asks for none. Writing to the clipboard doesn't need permission, and Vibe-Board never reads it.

## Legacy clipboard history

The earlier recording build may have saved clipboard text in the `clipboard_entries` table of the same database.

- The app no longer shows, imports, prunes or deletes it.
- Your saved recording preferences are kept too, but nothing reads them.

To review or remove that data safely:

```bash
python scripts/legacy_history.py summary                         # counts and dates only
python scripts/legacy_history.py export ~/Desktop/legacy.json    # new file, readable only by you
python scripts/legacy_history.py delete                          # type DELETE to confirm
```

- The script never prints clipboard contents to the terminal.
- `export` refuses to overwrite an existing file. Delete the export when you're done with it.
- `delete` removes only legacy entries. Your commands are untouched. It also scrubs the freed space (`secure_delete` + `VACUUM`) so deleted text doesn't linger in the file.

## Test and lint

```bash
python -m pytest -q                # unit, offscreen UI, security, and private-pasteboard AppKit tests
python -m pytest -q -m macos       # only the real-AppKit tests
python -m ruff check . && python -m ruff format --check .
```

None of the automated tests touch your real clipboard or your real database. Behavior that needs a real Mac, such as menu-bar clicks and pasting into Terminal, is covered by [tests/manual_macos_checklist.md](tests/manual_macos_checklist.md).

## Checking the interface

- `python scripts/render_ui_states.py` renders each state in both themes to `ui-review/`:
  - wide and narrow layouts
  - the copy confirmation
  - the editor and Settings
  - empty, no-match and error states

  It uses a throwaway database, shows nothing on screen, and never touches your clipboard.
- Native window chrome, real menu-bar clicks, dragging, live appearance switching and Retina sharpness have to be checked on the running app. See [tests/manual_macos_checklist.md](tests/manual_macos_checklist.md), section U.

## Known limitations

- **Global shortcut limits:**
  - Shortcuts that *other apps* registered globally, such as Raycast or Alfred, can't be detected. macOS lets both apps hold the same shortcut. If ⌃⌥⌘V doesn't respond, choose another in Settings.
  - A global shortcut also takes precedence over the same combination inside apps, such as a menu shortcut in your editor.
  - It needs no permissions. A real key press from other apps can only be confirmed by you (`tests/manual_macos_checklist.md`, section H; `python scripts/hotkey_probe.py --listen`).
- **Active display:** the display you're "working on" is the one under the mouse pointer. Finding another app's focused window would need Accessibility permission, which Vibe-Board doesn't request.
- The Dock icon is still shown.
- Theme colors are applied by Vibe-Board. Some native pieces, such as menu-bar menus and the standard confirmation dialogs' own chrome, follow macOS.
- The blended title bar needs Qt 6.9 or later. Its spacing is verified on real windows (`scripts/window_probe.py`); dragging is a manual check. If anything looks wrong, turn it off in Settings.
- The Qt text fields read the clipboard only when *you* paste into them (⌘V or the context menu).
- The packaged app is ad-hoc signed and not notarized. It's fine on the Mac that built it, but it would be blocked by Gatekeeper on other Macs (see docs/packaging.md).
- The packaged app is arm64 only.
- The shared UI and service code is pure Qt, but Windows would still need a clipboard writer adapter and its own testing.
