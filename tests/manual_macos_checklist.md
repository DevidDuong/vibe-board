# Manual macOS checklist

The automated tests use a fake clipboard, the offscreen Qt platform, and a private AppKit pasteboard. Run the checks below on the Mac and record each one as pass, fail or notes.

Tip: use a separate library while testing:
`CLIPFLOW_DATA_DIR=./.clipflow-dev-data python main.py` (git-ignored).

## Menu bar (`python scripts/macos_probe.py`)

- [ ] M-1 A dot icon appears in the menu bar. The terminal shows `System tray available: True`.
- [ ] M-2 **Left-click** the icon. The terminal prints `tray activated: Trigger` and the window toggles.
- [ ] M-3 **Right-click** (or Ctrl-click) the icon. The terminal prints `tray activated: Context` and a "Quit probe" menu appears.

## Security refactor (`python main.py` with your real data)

- [ ] S-1 Vibe-Board opens the Command Library. There is **no** welcome or "Start Recording" dialog, and no Pause/Recording control anywhere.
- [ ] S-2 Copy text in VS Code, Safari and Terminal while Vibe-Board runs. None of it appears in Vibe-Board.
- [ ] S-3 No macOS "paste from other apps" alert appears while you browse or search.
- [ ] S-4 Quit and relaunch twice. Recording is still absent, and `~/Library/Logs/ClipFlow/clipflow.log` has no "monitor" line after the restart.
- [ ] S-5 `python scripts/legacy_history.py summary` reports the same legacy count as before the update. Nothing from it is shown in the app.
- [ ] S-6 `ls -la ~/Library/Application\ Support/ClipFlow` shows `-rw-------` for every `clipflow.sqlite3*` file.
- [ ] S-7 Activity Monitor shows Vibe-Board at about 0% CPU when idle, with the window hidden.

## Command library

- [ ] C-1 Click **New Command**. Paste a multiline command containing tabs and a trailing newline, give it a title and category, then click **Save**. It appears in the list.
- [ ] C-2 Click **New Command**, type something, press **Enter** in the Title field. Nothing is saved. Click **Cancel** and choose **Discard**. Nothing is saved.
- [ ] C-3 Select the command and click **Copy**. In Terminal, press Cmd+V. The text pastes exactly and **doesn't run** until you press Return. With zsh's bracketed paste, a trailing newline is also not executed. Note the result for your shell.
- [ ] C-4 Double-click a row, and press Enter from the search box. Both copy. A single click doesn't.
- [ ] C-5 Edit the command, change a line, and save. The detail pane shows the change.
- [ ] C-6 Pin a command. It moves to the top with "Pinned ·".
- [ ] C-7 Search by part of a title, a command and a description, in any case. Each finds the command. Filter by category and by Uncategorized.
- [ ] C-8 Delete a command. A confirmation appears; Cancel keeps it and Delete removes it.
- [ ] C-9 Save a command containing a fake token such as `ghp_` followed by 36 letters. A **Possible Secret** warning appears. **Go Back** doesn't save; **Save Anyway** does.
- [ ] C-10 Try to save `-----BEGIN RSA PRIVATE KEY-----`. **Can't Save Command** appears.
- [ ] C-11 Esc (with an empty search) and the red close button hide the window. A left-click on the menu-bar icon brings it back with the search field focused.
- [ ] C-12 Launch a second copy while one is running. The second exits and the first window comes forward.
- [ ] C-13 Quit and relaunch. Commands, pins and categories persist.
- [ ] C-14 Press Ctrl+C in the launching terminal. Vibe-Board quits promptly.
- [ ] C-15 Switch between light and dark appearance. The menu-bar icon stays visible. Window theming is covered in U-2.

## U: Redesigned interface (`python main.py`)

Run `python scripts/render_ui_states.py` first and look through `ui-review/*.png`. Then check the live behavior that can't be rendered offscreen:

- [ ] U-1 **Unified title bar.** The traffic lights sit in the empty strip above the header and overlap nothing. Dragging that strip, or empty header space, moves the window. Settings → turn off "Blend the title bar" → Save: the standard title bar appears immediately and the window stays open.
- [ ] U-2 **Theme.** In Settings, choose Dark, then Light, then Match System, and Save each time. Colors switch without a restart. With Match System selected, change System Settings → Appearance: Vibe-Board follows within a second.
- [ ] U-3 **Focus.** Opening from the menu bar puts the cursor in search. Typing filters immediately. Tab moves search → list → buttons, and each control shows a visible accent focus ring. The selected card has a thicker accent border while the list has focus.
- [ ] U-4 **Hover.** Moving the mouse over cards shows a subtle hover background. The selected card is clearly distinct in both themes.
- [ ] U-5 **Copy confirmation.** Enter, double-click and Copy each show a green "Copied '…'" toast at the bottom for about 2 seconds. Paste into Terminal: the text is exact and doesn't run until you press Return.
- [ ] U-6 **Hide after copy.** Turn it on in Settings. After a copy the toast is visible briefly, then the window hides.
- [ ] U-7 **Resizing.** Narrow the window below about 760 px: the detail pane disappears. Below about 640 px: the shortcut hints disappear. The Copy / Edit / Pin / Delete bar stays usable. At the minimum size (420×380) nothing overlaps.
- [ ] U-8 **Display scaling.** On a Retina screen, and at a scaled resolution or on an external monitor if you have one, icons, card corners and monospace text stay sharp.
- [ ] U-9 **Escape.** With text in search, Esc clears it. A second Esc hides the window.
- [ ] U-10 **Filters.** Chips show All, Pinned, each category, and Uncategorized only when relevant. With many categories in a narrow window, the chip row scrolls sideways. ⌘] and ⌘[ cycle through the chips.
- [ ] U-11 **Editor.** Line and character counts update as you type. Long lines scroll sideways rather than wrapping. Tab moves between fields. Category suggests existing categories.
- [ ] U-12 **VoiceOver** (⌘F5), optional. Search, the command list, cards (title, category, first line, line count) and buttons are announced with meaningful names.

## P: Packaged app (`dist/Vibe-Board.app` or `/Applications/Vibe-Board.app`)

Run `./packaging/smoke_test_app.sh` first; it covers launch, hand-off, quit, relaunch and data isolation automatically. Then quit Vibe-Board everywhere, including any `python main.py` run, and check the following by hand.

- [ ] P-1 **Finder launch.** With VS Code closed, double-click Vibe-Board in Finder. No "can't be opened" or "unidentified developer" dialog appears. The window opens with the Vibe-Board icon in the Dock, and the clipboard icon appears in the menu bar.
- [ ] P-2 **Spotlight.** After installing to /Applications: press ⌘Space, type "Vibe-Board", press Return. It launches, or, if already running, its window comes forward.
- [ ] P-3 **Menu bar.** Left-click the menu-bar icon: the palette toggles. Right-click: Open / New Command… / Quit Vibe-Board.
- [ ] P-4 **Close keeps running.** Esc or the red button hides the window and focus returns to the previous app. Vibe-Board stays in the menu bar and Dock. A menu-bar click or Spotlight brings it back.
- [ ] P-5 **Quit.** Each way quits completely (menu-bar icon disappears, no Vibe-Board in Activity Monitor): the in-window Quit button, ⌘Q, menu-bar → Quit Vibe-Board, Dock icon → right-click → Quit.
- [ ] P-6 **Reopen.** After quitting, launch again from Spotlight or Finder. Your commands and settings are still there.
- [ ] P-7 **Commands.** In the packaged app: add (multiline), edit, pin, search, filter, delete (with confirmation), copy (paste into Terminal: exact text, not executed), and Settings (theme, preview lines, hide after copy, title bar) all work.
- [ ] P-8 **Look.** System font and monospace previews, icons, rounded cards, chips and focus rings look the same as the source run (compare with `python scripts/render_ui_states.py`). Dark, Light and Match System all work. The app icon shows in the Dock, Finder and ⌘Tab.
- [ ] P-9 **Keyboard.** All of section U's keys work in the packaged app: ↑↓, Enter, Esc, ⌘N, ⌘E, ⌘P, ⌘⌫, ⌘F, ⌘,, ⌘] / ⌘[.
- [ ] P-10 **Logout.** With Vibe-Board running, log out or restart. Vibe-Board doesn't block it.
- [ ] P-11 **No prompts.** Through all of the above, macOS shows no permission prompts (clipboard, Accessibility, network, Automation).
- [ ] P-12 **Real library.** On the first real launch your existing library opens. `python scripts/legacy_history.py summary` still reports the same legacy count.

## H: Global shortcut (default ⌃⌥⌘V)

Quit any other Vibe-Board or ClipFlow copy first: macOS lets two apps hold the same shortcut, and only one receives each press. To test the shortcut mechanism without the app, run `python scripts/hotkey_probe.py --listen`. It prints a line for each press.

- [ ] H-1 **From Terminal.** Hide Vibe-Board (Esc), click into a Terminal window and press ⌃⌥⌘V. The palette appears in front with the cursor in the search field. Typing filters immediately.
- [ ] H-2 **From Safari and from VS Code.** Repeat H-1 with each app focused. It works the same, and the keystroke does **not** also reach Safari or VS Code.
- [ ] H-3 **Toggle.** With the palette in front, press ⌃⌥⌘V: it hides and focus returns to the previous app. Press again: it comes back. If the palette is open but behind another app, the shortcut brings it to the front instead of hiding it.
- [ ] H-4 **Editor safety.** Open Add Command, type a title, then press ⌃⌥⌘V. The editor comes to the front and your text is still there; nothing is hidden or lost.
- [ ] H-5 **Change it.** In Settings, click the shortcut, press ⌃⇧⌘K and Save. The new shortcut works from another app and ⌃⌥⌘V no longer does. Relaunch: ⌃⇧⌘K still works.
- [ ] H-6 **Conflict with macOS.** In Settings, record ⌥⌘Space or ⌘Space. The status line says it's a macOS shortcut and Save is refused with that reason. The previous shortcut keeps working.
- [ ] H-7 **Refused combinations.** Record ⇧⌘V (Paste and Match Style), ⌘C, or ⌥Space. Each shows a clear reason and can't be saved.
- [ ] H-8 **Reset to Default and turning off.** Reset to Default shows ⌃⌥⌘V. Unticking the checkbox and saving turns the shortcut off; the menu bar still opens the palette.
- [ ] H-9 **No prompts.** Throughout H, macOS shows no permission dialog (Accessibility, Input Monitoring, Screen Recording), and Vibe-Board doesn't appear under System Settings → Privacy & Security for any of them.
- [ ] H-10 **Taken by another app (optional).** If you use Raycast, Alfred or similar, assign it ⌃⌥⌘V too. Note which app responds. Vibe-Board can't detect this case; choose a different shortcut if needed.

## M2: Menu bar and relaunch still work with the shortcut enabled

- [ ] M2-1 Left-click the menu-bar icon: the palette toggles. Right-click: the menu appears.
- [ ] M2-2 Hide the palette, then ⌘Space → "Vibe-Board" → Return. The palette comes forward with the search field focused.

## W: Window placement

- [ ] W-1 **Size and position memory.** Resize and move the palette, hide it (Esc), show it again with ⌃⌥⌘V. It's in the same place and size. Quit and relaunch: same again.
- [ ] W-2 **Multiple displays.** With an external display attached, move the mouse onto the external display and press ⌃⌥⌘V (or click its menu bar icon). The palette opens fully on that display. Move the mouse back to the built-in display and reopen: it opens there.
- [ ] W-3 **Unplugging.** Place the palette on the external display, hide it, unplug the display, and reopen. It opens fully visible on the built-in display, with its remembered size if that fits.
- [ ] W-4 **Unplugging while open.** With the palette open on the external display, unplug it. The palette ends up fully visible on the remaining display.
- [ ] W-5 **Resolution change.** In System Settings → Displays, pick a smaller "Looks like" resolution and reopen the palette. It fits entirely on screen, never partly off it, and isn't smaller than its minimum size.
- [ ] W-6 **Breakpoints.** Narrow the window: the detail pane disappears below about 760 pt and the hints below about 640 pt, as before.

## T: Title bar (after the gap fix)

- [ ] T-1 **Gap.** With "Blend the title bar" on, the header (Commands, Add Command) starts just below the traffic lights, about 8 pt under the title bar, not about 30 pt as before. `python scripts/window_probe.py` reports `gap 8 pt` on each display.
- [ ] T-2 **Traffic lights.** The red, yellow and green buttons sit in the blended title bar, don't overlap anything, and work.
- [ ] T-3 **Dragging.** Drag the window by the title-bar area, by empty header space, and by the empty strip above the search field. The window moves each time.
- [ ] T-4 **Standard mode.** Turn the blended title bar off in Settings and Save. The standard title bar appears immediately with normal spacing, and the window stays open.
- [ ] T-5 **Themes.** T-1 to T-4 look right in Dark, Light and Match System.
- [ ] T-6 **Retina.** On the built-in Retina display, and on an external non-Retina display if you have one, the title bar, icons and text are sharp and the gap is the same.
- [ ] T-7 **Search focus.** Every way of opening the palette (⌃⌥⌘V, menu-bar icon, Spotlight, Finder, Dock) leaves the cursor in the search field.

Opt-in automated check of T-1 on real windows: `CLIPFLOW_GUI_TESTS=1 python -m pytest tests/test_title_bar.py`. Windows appear briefly.

## Not yet applicable

- Launch at login (deliberately not implemented).
- Running on another Mac (needs Developer ID signing and notarization; see docs/packaging.md).
