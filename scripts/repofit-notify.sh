#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_TERMINAL_PROMPT=0
/usr/bin/git -C "$REPO_DIR" pull --ff-only origin main

DIGEST="$(/usr/bin/find "$REPO_DIR/digests" -type f -name '????-??-??.md' | /usr/bin/sort | /usr/bin/tail -n 1)"
[[ -n "$DIGEST" ]] || { echo 'No digest available' >&2; exit 1; }
TOP_THREE="$(/usr/bin/sed -nE 's/^### [0-9]+\. \[([^]]+)\].*/\1/p' "$DIGEST" | /usr/bin/head -n 3 | /usr/bin/paste -sd ',' -)"
[[ -n "$TOP_THREE" ]] || { echo 'No picks in digest' >&2; exit 1; }
# Generate private recommendations after pulling; any failure keeps the original alert.
UV="$(command -v uv || true)"
if [[ -n "$UV" ]] && FIT_NOTIFICATION="$(cd "$REPO_DIR" && "$UV" run gt fit --input "$DIGEST" --notification 2>/dev/null)"; then
  [[ -z "$FIT_NOTIFICATION" ]] || TOP_THREE="$FIT_NOTIFICATION"
fi
if [[ "$(/usr/bin/basename "$DIGEST" .md)" != "$(/bin/date +%F)" ]]; then
  TOP_THREE="[$(/usr/bin/basename "$DIGEST" .md)] $TOP_THREE"
fi
# Pass repository names as data, never as executable AppleScript source.
/usr/bin/osascript - "$TOP_THREE" <<'APPLESCRIPT'
on run argv
    display notification (item 1 of argv) with title "repofit 오늘의 오픈소스"
end run
APPLESCRIPT
