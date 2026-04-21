#!/usr/bin/env bash
# Render the .plist templates with absolute paths and install them.
# Usage: ./launchd/install.sh [path/to/python]
set -euo pipefail

PROJECT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${1:-$PROJECT_PATH/.venv/bin/python}"
DEST="$HOME/Library/LaunchAgents"

mkdir -p "$DEST" "$PROJECT_PATH/logs"

for plist in com.floki.telegram.plist com.floki.dispatcher.plist com.floki.dashboard.plist com.floki.washer.plist; do
  sed "s|__PROJECT_PATH__|$PROJECT_PATH|g; s|__PYTHON__|$PYTHON|g" \
    "$PROJECT_PATH/launchd/$plist" > "$DEST/$plist"
  launchctl unload "$DEST/$plist" 2>/dev/null || true
  launchctl load   "$DEST/$plist"
  echo "loaded: $plist"
done
