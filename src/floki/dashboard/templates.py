from __future__ import annotations

LOGIN_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Floki — War Room</title>
<style>
  body { background:#0b0e14; color:#e6e1cf; font:15px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; }
  .card { background:#10141c; border:1px solid #1f2430; padding:32px; border-radius:10px; width:320px; }
  h1 { margin:0 0 18px; font-size:18px; letter-spacing:1px; color:#ffd580; }
  input { width:100%; box-sizing:border-box; padding:10px; background:#0b0e14; color:#e6e1cf; border:1px solid #1f2430; border-radius:6px; font:inherit; }
  button { margin-top:12px; width:100%; padding:10px; background:#ffd580; color:#0b0e14; border:0; border-radius:6px; cursor:pointer; font:inherit; font-weight:600; }
  .err { color:#ff6b6b; margin-top:10px; min-height:1.2em; }
</style></head><body>
<form class="card" method="POST" action="/login">
  <h1>FLOKI // WAR ROOM</h1>
  <input name="pin" type="password" placeholder="PIN" autofocus required />
  <button type="submit">Unlock</button>
  <div class="err">__ERR__</div>
</form></body></html>
"""


def _room_block(daily_url: str) -> str:
    if not daily_url:
        return '<div class="muted">DAILY_ROOM_URL not configured.</div>'
    return (
        f'<a class="btn" href="{daily_url}" target="_blank" rel="noopener">'
        f"Enter War Room (Daily.co) &rarr;</a>"
    )


def dashboard_html(daily_url: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Floki — Mission Control</title>
<style>
  :root {{ --bg:#0b0e14; --panel:#10141c; --border:#1f2430; --text:#e6e1cf; --accent:#ffd580; --muted:#6c7580; --ok:#bae67e; --err:#ff6b6b; }}
  body {{ background:var(--bg); color:var(--text); font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; margin:0; padding:24px; }}
  h1 {{ margin:0 0 6px; color:var(--accent); letter-spacing:1px; font-size:16px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; margin-top:16px; }}
  .panel {{ background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:16px; }}
  .panel h2 {{ margin:0 0 10px; font-size:12px; color:var(--muted); letter-spacing:2px; text-transform:uppercase; }}
  table {{ width:100%; border-collapse:collapse; }}
  td, th {{ text-align:left; padding:6px 4px; border-bottom:1px solid var(--border); }}
  th {{ color:var(--muted); font-weight:400; font-size:12px; }}
  .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; background:#1a1f2b; font-size:12px; }}
  .btn {{ display:inline-block; padding:10px 14px; background:var(--accent); color:var(--bg); border-radius:6px; font-weight:600; text-decoration:none; }}
  .muted {{ color:var(--muted); }}
  form.row {{ display:flex; gap:8px; }}
  form.row input, form.row textarea {{ flex:1; background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:8px; font:inherit; }}
  form.row button {{ background:var(--accent); color:var(--bg); border:0; border-radius:6px; padding:8px 14px; font:inherit; font-weight:600; cursor:pointer; }}
  .agent {{ display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--border); }}
  .agent:last-child {{ border-bottom:0; }}
  .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--ok); margin-right:8px; }}
</style></head><body>
<h1>FLOKI // MISSION CONTROL</h1>
<div class="muted">last updated <span id="ts">—</span></div>

<div class="grid">
  <div class="panel">
    <h2>War Room</h2>
    {_room_block(daily_url)}
    <p class="muted" style="margin-top:14px">Pipecat voice loop connects to <code>ws://&lt;host&gt;/ws/pipecat?key=…</code></p>
  </div>

  <div class="panel">
    <h2>Council of Agents</h2>
    <div id="agents"></div>
  </div>

  <div class="panel">
    <h2>Waiting Room</h2>
    <div>Pending: <span id="pending" class="pill">—</span></div>
    <form class="row" id="task-form" style="margin-top:12px">
      <input name="payload" placeholder="New task (auto-routed)…" autocomplete="off" required />
      <button type="submit">Queue</button>
    </form>
    <div id="task-result" class="muted" style="margin-top:8px"></div>
  </div>

  <div class="panel" style="grid-column:1/-1">
    <h2>Hive Mind — Recent Activity</h2>
    <table>
      <thead><tr><th>#</th><th>Agent</th><th>Event</th><th>Detail</th><th>Time</th></tr></thead>
      <tbody id="hive"></tbody>
    </table>
  </div>
</div>

<script>
async function refresh() {{
  const r = await fetch('/api/status');
  if (!r.ok) return;
  const s = await r.json();
  document.getElementById('ts').textContent = new Date().toLocaleTimeString();
  document.getElementById('pending').textContent = s.pending;
  document.getElementById('agents').innerHTML = s.agents.map(a =>
    `<div class="agent"><span><span class="dot"></span>${{a.name}}</span>`
    + `<span class="muted">${{a.role}} · ${{s.counts[a.name] || 0}}</span></div>`
  ).join('');

  const h = await (await fetch('/api/hive?limit=15')).json();
  document.getElementById('hive').innerHTML = h.events.map(e =>
    `<tr><td>${{e.envelope_id ?? '-'}}</td><td>${{e.agent}}</td><td>${{e.event_type}}</td>`
    + `<td class="muted">${{e.detail ?? ''}}</td><td class="muted">${{e.created_at}}</td></tr>`
  ).join('') || '<tr><td colspan=5 class="muted">no activity</td></tr>';
}}
document.getElementById('task-form').addEventListener('submit', async (ev) => {{
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const r = await fetch('/api/tasks', {{
    method:'POST', headers:{{'content-type':'application/json'}},
    body: JSON.stringify({{payload: fd.get('payload')}})
  }});
  const j = await r.json();
  document.getElementById('task-result').textContent =
    `Queued #${{j.envelope_id}} → ${{j.agent}} [${{j.routing_reason}}]`;
  ev.target.reset();
  refresh();
}});
refresh(); setInterval(refresh, 5000);
</script>
</body></html>
"""
