#!/usr/bin/env bash
# Bootstrap one tmux session per agent, each pre-seeded with its memory brief.
# The dispatcher's TmuxAdapter targets these session names.
#
# Usage: ./scripts/start_sessions.sh
set -euo pipefail

PROJECT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_PATH"

BRIEF_DIR="$PROJECT_PATH/runtime/briefs"
mkdir -p "$BRIEF_DIR"

PY="${PYTHON:-$PROJECT_PATH/.venv/bin/python}"
FLOKI="$PY -m floki.cli"

# Session names MUST match agents.yaml::terminal_session values.
AGENTS=(floki comms content ops research)

for agent in "${AGENTS[@]}"; do
  session="floki-${agent}"
  brief="$BRIEF_DIR/${agent}.md"

  # Render the brief (pinned + insights + decaying + Obsidian vault).
  $FLOKI brief "$agent" --out "$brief" >/dev/null

  if tmux has-session -t "$session" 2>/dev/null; then
    echo "session exists: $session"
    continue
  fi

  # Start detached session running a shell in the project dir; show the brief on entry.
  tmux new-session -d -s "$session" -c "$PROJECT_PATH" \
    "echo '== $session =='; cat '$brief'; echo; exec \"\$SHELL\" -l"
  echo "started:       $session  (brief: $brief)"
done

echo
echo "Attach with:  tmux attach -t floki-comms   (etc.)"
echo "List:         tmux ls | grep floki-"
