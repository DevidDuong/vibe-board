#!/usr/bin/env bash
# Smoke-test a built app bundle against a throwaway database (never your real library).
#
#   ./packaging/smoke_test_app.sh [path/to/Vibe-Board.app]
#
# Launches the bundle through LaunchServices (`open`, like Finder/Spotlight), checks the
# lifecycle via the app's own log (event names and counts only), and confirms the real data
# folder is untouched by comparing file metadata (it is never opened).
# The app window will appear on screen briefly a few times.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="$(PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" -c "from clipflow import APP_NAME; print(APP_NAME)")"
APP_ARG="${1:-$ROOT/dist/$APP_NAME.app}"
APP="$(cd "$(dirname "$APP_ARG")" && pwd)/$(basename "$APP_ARG")"
EXE="$APP/Contents/MacOS/$(plutil -extract CFBundleExecutable raw "$APP/Contents/Info.plist" 2>/dev/null)"
# The library and log folders keep the former name "ClipFlow" (config.STORAGE_NAME).
REAL="$HOME/Library/Application Support/ClipFlow"
REAL_LOG="$HOME/Library/Logs/ClipFlow"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/clipflow-smoke.XXXXXX")"
LOG="$TMP/logs/clipflow.log"
FAILURES=0

[[ -x "$EXE" ]] || { echo "No app at $APP — run ./packaging/build_macos.sh first." >&2; exit 1; }

pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; FAILURES=$((FAILURES + 1)); }
check() { if eval "$2"; then pass "$1"; else fail "$1"; fi; }
fingerprint() { stat -f "%N %z %m" "$REAL"/clipflow.sqlite3 "$REAL"/clipflow.sqlite3-wal "$REAL_LOG"/clipflow.log 2>/dev/null; }
app_pid() { pgrep -n -f "^$EXE" || true; }
wait_for_log() { for _ in $(seq 1 40); do grep -q "$1" "$LOG" 2>/dev/null && return 0; sleep 0.25; done; return 1; }
wait_for_exit() { for _ in $(seq 1 40); do kill -0 "$1" 2>/dev/null || return 0; sleep 0.25; done; return 1; }
launch() { open "$@" --env CLIPFLOW_DATA_DIR="$TMP" --stdout "$TMP/stdout.txt" --stderr "$TMP/stderr.txt" "$APP"; }

echo "App:      $APP"
echo "Scratch:  $TMP"
BEFORE="$(fingerprint)"
[[ -z "$(app_pid)" ]] || { echo "This build is already running; quit it first." >&2; exit 1; }

echo "== Self-test inside the packaged runtime"
CLIPFLOW_DATA_DIR="$TMP/selftest-data" "$EXE" --self-test > "$TMP/selftest.txt" 2>&1
SELFTEST_RC=$?
check "frozen self-test passed ($(tail -1 "$TMP/selftest.txt"))" '[[ $SELFTEST_RC -eq 0 ]]'
check "self-test ran frozen" 'grep -q "PASS  frozen bundle" "$TMP/selftest.txt"'
check "self-test refuses without a throwaway data dir" '! env -u CLIPFLOW_DATA_DIR "$EXE" --self-test >/dev/null 2>&1'

echo "== Launch through LaunchServices (as Finder/Spotlight do)"
launch
check "app started" 'wait_for_log "Window shown (launch)"'
PID="$(app_pid)"
check "process running (pid ${PID:-none})" '[[ -n "$PID" ]] && kill -0 "$PID"'
check "fresh database migrated to v2" 'grep -q "Migrated database schema to v2" "$LOG"'
check "menu bar icon shown" 'grep -q "Menu bar icon shown (visible=True)" "$LOG"'
check "global shortcut registered (no permission prompt needed)" 'wait_for_log "Global shortcut active"'
check "library loaded" 'wait_for_log "Library loaded (0 commands)"'
check "database created outside the bundle" '[[ -f "$TMP/clipflow.sqlite3" ]] && [[ "$(stat -f %Lp "$TMP/clipflow.sqlite3")" == 600 ]]'
check "no network sockets open" '! lsof -a -p "$PID" -i >/dev/null 2>&1'
check "real library not opened" '! lsof -p "$PID" 2>/dev/null | grep -q "Application Support/ClipFlow"'
check "no errors on stderr" '! grep -qiE "error|traceback|could not" "$TMP/stderr.txt"'

echo "== Second launch hands off to the running instance"
launch -n
check "running instance showed its window" 'wait_for_log "Window shown (second launch)"'
check "second process exited" 'sleep 1; [[ "$(pgrep -f "^$EXE" | wc -l | tr -d " ")" == 1 ]]'

echo "== Quit (SIGTERM, as Activity Monitor's Quit sends) and relaunch"
kill -TERM "$PID"
check "quit gracefully" 'wait_for_exit "$PID" && grep -q "exited (0)" "$LOG"'
check "global shortcut released on quit" 'grep -q "Global shortcut turned off" "$LOG"'
# LaunchServices can swallow an `open` issued the instant an app exits (it may still list the
# old instance), so pause briefly as a person relaunching would.
sleep 1
launch
check "relaunched after quit" 'for _ in $(seq 1 40); do [[ "$(grep -c "Window shown (launch)" "$LOG")" == 2 ]] && break; sleep 0.25; done; [[ "$(grep -c "Window shown (launch)" "$LOG")" == 2 ]]'
PID="$(app_pid)"
check "relaunch running (pid ${PID:-none})" '[[ -n "$PID" ]]' 
kill -TERM "$PID" 2>/dev/null
check "quit again" 'wait_for_exit "$PID"'

echo "== Bundle integrity and Gatekeeper"
check "signature still valid after running (nothing written into the bundle)" 'codesign --verify --deep --strict "$APP" 2>/dev/null'
check "not quarantined (local build)" '! xattr -p com.apple.quarantine "$APP" >/dev/null 2>&1'
SPCTL="$(spctl --assess --type execute "$APP" 2>&1)"
echo "INFO  Gatekeeper assessment: ${SPCTL:-accepted} (expected: rejected — ad-hoc signed, not notarized)"

echo "== Real data untouched"
check "real database and log unchanged" '[[ "$(fingerprint)" == "$BEFORE" ]]'

echo
if [[ $FAILURES -eq 0 ]]; then echo "Smoke test PASSED (scratch data: $TMP)"; else echo "Smoke test FAILED: $FAILURES check(s)"; fi
exit $FAILURES
