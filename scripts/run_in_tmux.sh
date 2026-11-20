#!/usr/bin/env bash
# Keep a foreground command attached to its own tmux session; never restart it.
# Usage: bash scripts/run_in_tmux.sh SESSION [--] COMMAND [ARG ...]
# Artifacts default to runs/current/tmux/SESSION; RSI_TMUX_LOG_ROOT may override.
set -euo pipefail

if [[ $# -lt 2 || ! "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ ]]; then
  echo "Usage: bash $0 SESSION [--] COMMAND [ARG ...]" >&2
  exit 2
fi
SESSION=$1
shift
if [[ "$1" == -- ]]; then shift; fi
if [[ $# -eq 0 ]]; then echo "A command is required" >&2; exit 2; fi
TMUX_BIN=$(command -v tmux) || { echo "tmux is required" >&2; exit 2; }
CAFFEINATE_BIN=$(command -v caffeinate) || { echo "caffeinate is required on this macOS host" >&2; exit 2; }
if "$TMUX_BIN" has-session -t "=$SESSION" 2>/dev/null; then
  echo "Session already exists: $SESSION; inspect or attach, never automatically restart." >&2
  exit 2
fi
REPO_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
LOG_ROOT=${RSI_TMUX_LOG_ROOT:-"$REPO_DIR/runs/current/tmux"}
mkdir -p -- "$LOG_ROOT"
LOG_ROOT=$(cd -- "$LOG_ROOT" && pwd)
DIRECTORY="$LOG_ROOT/$SESSION"
mkdir -- "$DIRECTORY"  # A previous exited attempt is not overwritten.
WORKER="$DIRECTORY/command.sh"
{
  printf '#!/usr/bin/env bash\nset -uo pipefail\n'
  printf 'TMUX_BIN=%q\nCAFFEINATE_BIN=%q\nDIRECTORY=%q\n' "$TMUX_BIN" "$CAFFEINATE_BIN" "$DIRECTORY"
  printf 'cd -- %q\n' "$PWD"
  printf 'COMMAND=('
  printf ' %q' "$@"
  printf ' )\n'
  cat <<'BASH'
"$TMUX_BIN" set-option -p -t "$TMUX_PANE" remain-on-exit on
"$CAFFEINATE_BIN" -i -w $$ &
INHIBITOR=$!
cleanup() {
  code=$?
  trap - EXIT
  kill "$INHIBITOR" 2>/dev/null || true
  wait "$INHIBITOR" 2>/dev/null || true
  printf '%s\n' "$code" > "$DIRECTORY/exit-code"
  date -u '+%Y-%m-%dT%H:%M:%SZ' > "$DIRECTORY/finished-at"
  printf '\nCommand exited with status %s. No restart was attempted.\n' "$code"
  exit "$code"
}
trap cleanup EXIT
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$DIRECTORY/started-at"
"${COMMAND[@]}" 2>&1 | tee -a "$DIRECTORY/console.log"
code=${PIPESTATUS[0]}
exit "$code"
BASH
} > "$WORKER"
printf -v START_COMMAND 'exec /bin/bash %q' "$WORKER"
"$TMUX_BIN" new-session -d -s "$SESSION" "$START_COMMAND"
printf 'Session: %s\nLog: %s/console.log\nExit status after completion: %s/exit-code\n' "$SESSION" "$DIRECTORY" "$DIRECTORY"
printf 'Attach: tmux attach-session -t %q\n' "$SESSION"
printf 'Inspect: tmux capture-pane -p -t %q\n' "$SESSION:0.0"
