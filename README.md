# Floki's Command Center

A modular multi-agent terminal ecosystem for OpenClaw, running on Mac Studio M3 Ultra.

## Architecture Phases

1. **Terminal Ecosystem & Delegation** — Floki (triage) + Comms / Content / Ops / Research sub-agents.
2. **Messaging Subsystem & Telegram Queue** *(this scaffold)* — Telegram → Waiting Room → single-consumer dispatcher.
3. **Washing Machine Memory Engine** — Gemini Flash parses logs into pinned / decaying / insight memories.
4. **Hive Mind & Task Auto-Assignment** — Unified SQLite task ledger + LLM triage to agent buckets.
5. **War Room** — Daily.co video + Pipecat voice loop with keyword / prefix / logic routing.
6. **Autostart** — `launchd` plists for every daemon.

## Repo layout

```
floki-command-center/
├── config/           # agents.yaml (Elephant-Agent registry)
├── data/             # queue.db (gitignored)
├── launchd/          # .plist templates + install.sh (Phase 6)
├── scripts/          # init_db · run_telegram · run_dispatcher
├── src/floki/
│   ├── config.py
│   ├── queue/        # Waiting Room: schema, store, dispatcher
│   ├── telegram/     # aiogram bot, allowlist middleware, PIN gate, /hive, /status
│   ├── agents/       # Sub-agent registry + AgentAdapter (Tmux / Stub)
│   ├── hive/         # HiveMind query API (Phase 4 surface)
│   └── security/     # PIN hashing/verification
└── tests/            # queue, routing, adapters, hive
```

## Phase 1 — agent adapters (Elephant-Agent protocol)

Every sub-agent runs in its own tmux session (`floki-comms`, `floki-ops`, …).
`TmuxAdapter` pastes envelope payloads via `load-buffer`/`paste-buffer` so
multi-line content doesn't need shell escaping. Grafting a new OSS framework =
subclass `AgentAdapter.deliver`; nothing in the dispatcher changes.

Dry-run without tmux: `FLOKI_ADAPTER=stub python scripts/run_dispatcher.py`.

## Phase 6 — autostart

```bash
./launchd/install.sh /path/to/.venv/bin/python
```

Installs `com.floki.telegram` and `com.floki.dispatcher` as LaunchAgents. The
dispatcher plist is a *singleton* on purpose — duplicating it breaks collision
prevention.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env      # fill in BOT_TOKEN, ALLOWED_CHAT_IDS, PIN_HASH, TUNNEL_URL
python -m floki.security.pin hash 1234   # paste output as PIN_HASH
python scripts/init_db.py

# Terminal A:
python scripts/run_telegram.py

# Terminal B (start tmux sessions floki-comms/content/ops/research first, or use FLOKI_ADAPTER=stub):
python scripts/run_dispatcher.py
```

Collision prevention: exactly one message leaves the Waiting Room at a time, gated by an
asyncio lock + SQLite `BEGIN IMMEDIATE` transaction in `floki/queue/dispatcher.py`.

## Telegram commands

| Command          | Unlocked? | What it does |
|------------------|-----------|--------------|
| `/start`         | no        | Greeting + PIN prompt |
| `/pin <code>`    | no        | Unlocks War Room for 30 min |
| `/lock`          | yes       | Clear PIN session |
| `/dashboard`     | yes       | Returns Cloudflare Tunnel URL |
| `/status`        | yes       | Pending queue + Hive Mind counts |
| `/hive [agent]`  | yes       | Recent 10 events, optionally filtered |
| *(free text)*    | yes       | Routed: broadcast keyword → prefix → default (floki) |
