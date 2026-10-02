# Building and installing Vibe-Board.app

Vibe-Board ships as a standalone macOS app built with PyInstaller. The app contains its own Python runtime, PySide6/Qt and PyObjC, so it runs without VS Code, a terminal, or the project's `.venv`.

## Build

Requirements: Apple Silicon Mac, macOS 13 or later, and the project `.venv` set up as in the README.

```bash
cd ~/clipboard-manager
./packaging/build_macos.sh
```

The script:
1. Checks that you're on macOS/arm64 with Python 3.12+, and that the installed PySide6, PyObjC and PyInstaller versions match `requirements.txt`.
2. Deletes `build/` and `dist/`, so every build starts clean.
3. Generates the placeholder app icon (`build/icon/ClipFlow.icns`) with `packaging/make_icon.py`.
4. Runs PyInstaller with `packaging/ClipFlow.spec`: onedir, windowed `.app`, arm64.
5. Runs `packaging/verify_bundle.py`, which checks:
   - the bundle id
   - that it's arm64-only
   - the ad-hoc signature
   - the icon
   - that the cocoa platform plugin is present
   - that no login item or permission prompts are declared
   - that **no database, log, credential or test file** was packaged
   - that unused Qt plugins (QtQuick/QML, PDF, TLS, virtual keyboard) were excluded

A build takes about 20 seconds and produces an app of about 80 MB.

**Output:** `~/clipboard-manager/dist/Vibe-Board.app`

| Property | Value |
|---|---|
| Bundle identifier | `local.devidduong.clipflow` (set in `packaging/ClipFlow.spec`) |
| Version | 0.1.0 (from `pyproject.toml`) |
| Architecture | arm64 only |
| Minimum macOS | 13.0 |
| Signature | ad-hoc (not Developer ID, not notarized) |
| Icon | generated placeholder: a terminal glyph on an indigo tile. To replace it, put a designed `ClipFlow.icns` in `packaging/` and rebuild; the build uses it automatically. |

The configuration is reproducible (pinned dependencies, a fixed spec, clean builds), but the output isn't bit-for-bit identical between builds. PyInstaller and code signing embed build-specific data.

## Test the built app (without touching your library)

```bash
./packaging/smoke_test_app.sh
```

This launches `dist/Vibe-Board.app` through LaunchServices, as Finder and Spotlight do, with a throwaway database. The window appears briefly a few times. It checks:

- the in-app self-test (26 checks run inside the packaged runtime: add, edit, delete, pin, search, filter, copy to a private pasteboard, settings, restart persistence, fonts, styles, window placement recovery, and the global-shortcut backend — using an obscure probe combination, never your shortcut)
- that it starts, migrates a fresh database, shows the menu-bar icon, and registers the global shortcut (released again on quit)
- that it has no network sockets and never opens your real library
- that a second launch hands off to the running instance
- graceful quit and relaunch
- that the signature is still valid after running
- that your real database and log are unchanged

You can also run only the self-test:

```bash
CLIPFLOW_DATA_DIR="$(mktemp -d)" dist/Vibe-Board.app/Contents/MacOS/Vibe-Board --self-test
```

It refuses to run without `CLIPFLOW_DATA_DIR`, or when that points at your real library.

## Install into /Applications

Quit any running Vibe-Board first (menu-bar icon → right-click → Quit Vibe-Board).

**Builds made before the rename are called ClipFlow.** Quit any running ClipFlow too. Old and new builds share the same library and hand off to each other, so launching Vibe-Board while ClipFlow is still running just brings the old ClipFlow window forward. Rebuilding replaces `dist/ClipFlow.app`. If you ever installed `/Applications/ClipFlow.app`, delete it after installing Vibe-Board. Your commands aren't stored in the app, so they stay.

**Finder:** open `~/clipboard-manager/dist`, then drag **Vibe-Board** onto **Applications** in the sidebar. To replace an older copy, choose **Replace**.

**Terminal:**

```bash
ditto ~/clipboard-manager/dist/Vibe-Board.app /Applications/Vibe-Board.app
```

`ditto` preserves the bundle's symlinks and signature. Avoid `cp -r`. After installing, remove the build copy (`rm -rf ~/clipboard-manager/dist`) so Spotlight doesn't list two copies. The next build recreates it.

A locally built app has no quarantine flag, so it opens without a Gatekeeper prompt (see below).

### Before the first launch with your real library

Your library is at `~/Library/Application Support/ClipFlow/`. On first launch, Vibe-Board upgrades its schema from v1 to v2 by **adding** the `commands` table. Nothing is deleted, and the legacy clipboard-history rows are kept as they are. If you'd like a backup first, with Vibe-Board not running:

```bash
ditto "$HOME/Library/Application Support/ClipFlow" "$HOME/Vibe-Board-backup-$(date +%Y%m%d)"
chmod 700 "$HOME/Vibe-Board-backup-"*
```

The backup includes the legacy clipboard history, which may contain sensitive text. Delete it when you no longer need it.

## Launch

- **Spotlight:** press ⌘Space, type `Vibe-Board`, press Return. If Vibe-Board is already running in the menu bar, this brings its window forward.
- **Finder / Launchpad:** open Applications and double-click Vibe-Board.
- The window opens on launch. Closing it (Esc or the red button) keeps Vibe-Board in the menu bar; click the menu-bar icon to bring it back. To quit, use **Quit** in the window, **Quit Vibe-Board** in the menu-bar icon's right-click menu, ⌘Q, or Activity Monitor (quits gracefully).
- Vibe-Board does **not** start at login. You can add it yourself under System Settings → General → Login Items. Vibe-Board never does this for you.

## Updating

Quit Vibe-Board, rebuild, and install again (Finder: **Replace**, or `ditto` as above). Your commands and settings live outside the app and are kept.

## Uninstall (keeping your saved commands)

1. Quit Vibe-Board.
2. Move `/Applications/Vibe-Board.app` to the Trash (Finder, or `rm -rf /Applications/Vibe-Board.app`).

That removes only the app. **Your commands, settings and legacy history stay** in `~/Library/Application Support/ClipFlow/`, and reinstalling picks them up again. **Don't** use "app cleaner" tools that sweep Application Support unless you mean to delete your library.

To remove everything, including saved commands, which can't be undone:

```bash
rm -rf "$HOME/Library/Application Support/ClipFlow"   # commands, settings, legacy history
rm -rf "$HOME/Library/Logs/ClipFlow"                  # diagnostic logs (no command text)
```

Export or back up first if there is anything you want to keep. Vibe-Board creates no other files: no LaunchAgents, login items or caches. Its temporary style images are removed automatically when it quits.

## Gatekeeper, signing and notarization

- **Signature:** the local build is ad-hoc signed. Apple Silicon requires every executable to carry a signature, and PyInstaller applies one automatically. `codesign --verify --deep --strict` passes.
- **Gatekeeper:**
  - `spctl --assess` **rejects** the app, because it isn't signed with a Developer ID and isn't notarized.
  - That doesn't matter for an app you built yourself. Gatekeeper only checks quarantined files, and files created or copied locally aren't quarantined.
  - Verified: no `com.apple.quarantine` attribute, and the app launches normally through LaunchServices.
- **Copying to another Mac:** if you AirDrop, download or email the app to another Mac, it **will** be quarantined. macOS will then say it "can't be opened" or can't verify the developer. Opening it would require **System Settings → Privacy & Security → Open Anyway** on that Mac. Don't disable Gatekeeper (`spctl --master-disable`) to get around this.
- **Permissions:** Vibe-Board needs none. It doesn't read the clipboard; writing to it needs no permission. There is no Accessibility, Input Monitoring, Automation, network or Screen Recording access, and its Info.plist declares no usage descriptions.

### For a future public release

All of the following are **not done yet**:

1. Join the Apple Developer Program and create a **Developer ID Application** certificate.
2. Change `BUNDLE_ID` in `packaging/ClipFlow.spec` (and in `verify_bundle.py`) to a reverse-DNS name you own.
3. Sign with the hardened runtime:
   - set `codesign_identity="Developer ID Application: …"` and an `entitlements_file` in the spec, or re-sign afterwards with `codesign --deep --force --options runtime --timestamp --sign "Developer ID Application: …"`
   - Python/PyInstaller apps may need `com.apple.security.cs.allow-unsigned-executable-memory` or `disable-library-validation`; test without them first
4. Notarize: `xcrun notarytool submit Vibe-Board.zip --keychain-profile … --wait`, then `xcrun stapler staple dist/Vibe-Board.app`.
5. Verify on a clean Mac, or a fresh user account, with a downloaded (quarantined) copy.
6. Optionally distribute as a signed `.dmg`.

Until then, treat the build as personal: run it on the Mac that built it.

## Known packaging limitations

- **arm64 only.** Intel Macs aren't supported by this build (`target_arch="arm64"`).
- **Quick relaunches:** LaunchServices can ignore an `open` issued within a split second of the app quitting, because it still lists the old instance. Relaunching a moment later works. The smoke test covers this.
- **Live checks:** menu-bar clicks, real window chrome, keyboard behavior and theme switching in the packaged app need a person to check them (`tests/manual_macos_checklist.md`, section P). No automation uses Accessibility permission.
