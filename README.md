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
├── config/           # agents.yaml, security.yaml (gitignored secrets live in .env)
├── data/             # queue.db (gitignored)
├── scripts/          # init_db, run_telegram, future run_dispatcher
├── src/floki/
│   ├── config.py
│   ├── queue/        # Waiting Room: schema, store, dispatcher
│   ├── telegram/     # aiogram bot, allowlist middleware, PIN gate, handlers
│   ├── agents/       # Sub-agent registry (modular — drop in new frameworks)
│   └── security/     # PIN hashing/verification
└── tests/
```

## Phase 2 quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env      # fill in BOT_TOKEN, ALLOWED_CHAT_IDS, PIN, TUNNEL_URL
python scripts/init_db.py
python scripts/run_telegram.py
```

In another terminal (this becomes the single-consumer dispatcher in Phase 2b):

```bash
python scripts/run_dispatcher.py
```

Collision prevention: exactly one message leaves the Waiting Room at a time, gated by an
asyncio lock + SQLite `BEGIN IMMEDIATE` transaction in `floki/queue/dispatcher.py`.
