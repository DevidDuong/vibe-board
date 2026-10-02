#!/usr/bin/env bash
# Build dist/<APP_NAME>.app (macOS, Apple Silicon) from a clean slate and verify it.
# APP_NAME (currently "Vibe-Board") comes from src/clipflow/__init__.py.
#
#   ./packaging/build_macos.sh
#
# Uses the project's .venv and the pinned dependencies in requirements.txt. Never touches
# ~/Library/Application Support/ClipFlow; never installs into /Applications.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"

[[ "$(uname -s)" == "Darwin" ]] || { echo "macOS is required." >&2; exit 1; }
[[ "$(uname -m)" == "arm64" ]] || { echo "Apple Silicon (arm64) is required." >&2; exit 1; }
[[ -x "$PY" ]] || { echo "Missing .venv — see README 'Setup'." >&2; exit 1; }
"$PY" -c "import sys; assert sys.version_info >= (3, 12)" || { echo "Python 3.12+ required." >&2; exit 1; }
APP_NAME="$(PYTHONPATH="$ROOT/src" "$PY" -c "from clipflow import APP_NAME; print(APP_NAME)")"
APP_PATH="$ROOT/dist/$APP_NAME.app"

echo "==> Checking pinned build dependencies"
"$PY" - <<'EOF'
import importlib.metadata as md, pathlib, re, sys
pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s]+)$", pathlib.Path("requirements.txt").read_text(), re.M))
wanted = ("PySide6", "pyobjc-core", "pyobjc-framework-Cocoa", "pyinstaller")
bad = [f"{n} {md.version(n)} != {pins[n]}" for n in wanted if md.version(n) != pins[n]]
sys.exit("Installed versions differ from requirements.txt: " + "; ".join(bad) if bad else 0)
EOF

echo "==> Cleaning previous build output"
rm -rf "$ROOT/build" "$ROOT/dist"

echo "==> Generating app icon"
"$PY" packaging/make_icon.py build/icon

echo "==> Running PyInstaller"
"$PY" -m PyInstaller --clean --noconfirm --log-level WARN \
  --distpath "$ROOT/dist" --workpath "$ROOT/build/pyinstaller" \
  packaging/ClipFlow.spec

echo "==> Verifying bundle"
"$PY" packaging/verify_bundle.py "$APP_PATH"

echo
echo "Built: $APP_PATH"
