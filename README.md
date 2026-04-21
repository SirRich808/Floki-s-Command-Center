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
│   ├── dashboard/    # FastAPI Mission Control + Pipecat WS (Phase 5)
│   ├── memory/       # Washing Machine: store, Washer ABC, heuristic, injector (Phase 3)
│   ├── hive/         # HiveMind query API (Phase 4 surface)
│   └── security/     # PIN hashing/verification
└── tests/            # queue, routing, adapters, hive, dashboard
```

## Phase 5 — The War Room

`scripts/run_dashboard.py` serves Mission Control at `http://127.0.0.1:8787`.
Expose via Cloudflare Tunnel and paste the URL into `.env` as `DASHBOARD_TUNNEL_URL`
— Telegram's `/dashboard` returns it.

**Routing rules** (shared between Telegram, dashboard, and Pipecat):

1. Keyword — broadcast words (`everyone`, `team`, …) → floki
2. Prefix  — `Comms, ...` → comms
3. Logic   — regex rules in `agents.yaml::logic_rules` → classified agent
4. Default — floki triage

**Pipecat integration**

Pipecat runs anywhere on the Mac and connects to the router via either:

```
# WebSocket (streaming voice loop)
ws://127.0.0.1:8787/ws/pipecat?key=$PIPECAT_WS_SECRET
>>> {"transcript": "Ops: log expense $42", "enqueue": true}
<<< {"agent":"ops","routing_reason":"prefix:ops","envelope_id":17}

# or one-shot HTTP (easier for per-utterance classification)
POST /api/voice/route?key=$PIPECAT_WS_SECRET
```

The router never sees LLM context — the three envelope rules are pure code.

**Daily.co**

Set `DAILY_ROOM_URL` to a pre-created room. The dashboard renders it as
"Enter War Room". Auto-room creation via API is left for a later iteration.

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

# Terminal C — Mission Control:
python scripts/run_dashboard.py    # → http://127.0.0.1:8787

# Terminal D — Washing Machine (optional until you have traffic):
python scripts/run_washer.py
```

## Phase 3 — Washing Machine

`memory/` ships a `Washer` ABC with a working `HeuristicWasher` (regex-based
pinned/decaying extraction). Swap in a `GeminiWasher` by subclassing `Washer`
and returning LLM-classified `MemoryDraft`s — nothing else changes.

Injection: `MemoryInjector.build(agent_name)` concatenates
pinned → insights → agent-scoped decaying → `OBSIDIAN_ROOT/<agent vault>/**.md`
into a single .md blob to paste at the top of the agent's terminal session.

Retention: `decay_days` is per-memory; `MemoryStore.prune_decayed()` runs on
every washer pass. Pinned memories (`decay_days IS NULL`) survive forever.

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
