"""NEAR AI Auto-Bidder Dashboard — lightweight Flask web UI."""

import collections
import functools
import hmac
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask, render_template_string, request, Response

from config import API_BASE, HEADERS, AGENT_ID

app = Flask(__name__)

# --- Basic Auth (C-1: timing-safe + require password) ---
DASH_USER = os.environ.get("DASHBOARD_USER", "admin")
DASH_PASS = os.environ.get("DASHBOARD_PASS")
if not DASH_PASS:
    raise RuntimeError("DASHBOARD_PASS env var is required — refusing to start with default")


def check_auth(username, password):
    if not username or not password:
        return False
    return (hmac.compare_digest(username, DASH_USER)
            and hmac.compare_digest(password, DASH_PASS))


# --- H-1: Simple IP-based rate limiting ---
_fail_counts: dict[str, list] = collections.defaultdict(list)
_MAX_FAILS = 10
_WINDOW = 300  # 5 minutes


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    _fail_counts[ip] = [t for t in _fail_counts[ip] if now - t < _WINDOW]
    return len(_fail_counts[ip]) >= _MAX_FAILS


def _record_fail(ip: str):
    _fail_counts[ip].append(time.time())


def auth_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr or "unknown"
        if _is_rate_limited(ip):
            return Response("Too many failed attempts. Try again later.", 429)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            _record_fail(ip)
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="NEAR Dashboard"'},
            )
        return f(*args, **kwargs)
    return decorated


# --- M-5: Security headers ---
@app.after_request
def security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'unsafe-inline'"
    return response


STATE_FILE = Path(__file__).parent / "bid_state.json"
LOG_FILE = Path(__file__).parent / "bidder.log"

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEAR AI Auto-Bidder Dashboard</title>
<meta http-equiv="refresh" content="30">
<style>
  :root{--bg:#0f1117;--card:#1a1d27;--border:#2a2d3a;--text:#e1e4ed;
    --dim:#8b8fa3;--green:#22c55e;--red:#ef4444;--yellow:#eab308;
    --blue:#3b82f6;--purple:#a855f7;--cyan:#06b6d4}
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'SF Mono','Cascadia Code','Fira Code',monospace;
    background:var(--bg);color:var(--text);padding:20px;font-size:14px}
  h1{font-size:20px;margin-bottom:20px;color:var(--cyan)}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px}
  .stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px}
  .stat .label{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:1px}
  .stat .value{font-size:28px;font-weight:bold;margin-top:4px}
  .stat .sub{font-size:11px;color:var(--dim);margin-top:2px}
  .green{color:var(--green)}.red{color:var(--red)}.yellow{color:var(--yellow)}
  .blue{color:var(--blue)}.purple{color:var(--purple)}.cyan{color:var(--cyan)}
  table{width:100%;border-collapse:collapse;background:var(--card);border-radius:8px;overflow:hidden;margin-bottom:24px}
  th{background:#22253a;text-align:left;padding:10px 12px;font-size:11px;
    color:var(--dim);text-transform:uppercase;letter-spacing:1px}
  td{padding:8px 12px;border-top:1px solid var(--border);font-size:13px}
  tr:hover td{background:#1f2233}
  .badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
  .badge-pending{background:#eab30820;color:var(--yellow)}
  .badge-accepted{background:#22c55e20;color:var(--green)}
  .badge-delivered{background:#3b82f620;color:var(--blue)}
  .badge-completed{background:#a855f720;color:var(--purple)}
  .badge-rejected{background:#ef444420;color:var(--red)}
  .section{margin-bottom:24px}
  .section h2{font-size:15px;margin-bottom:12px;color:var(--dim)}
  .log-box{background:var(--card);border:1px solid var(--border);border-radius:8px;
    padding:12px;max-height:300px;overflow-y:auto;font-size:12px;line-height:1.6;white-space:pre-wrap;color:var(--dim)}
  .bar{height:6px;border-radius:3px;background:var(--border);margin-top:8px;overflow:hidden}
  .bar-fill{height:100%;border-radius:3px}
  a{color:var(--cyan);text-decoration:none}a:hover{text-decoration:underline}
  .refresh{color:var(--dim);font-size:11px;float:right}
  .truncate{max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
</head>
<body>
<h1>NEAR AI Auto-Bidder Dashboard <span class="refresh">auto-refresh 30s | {{ now }}</span></h1>

<div class="grid">
  <div class="stat">
    <div class="label">Service Status</div>
    <div class="value {{ 'green' if service_active else 'red' }}">{{ 'RUNNING' if service_active else 'STOPPED' }}</div>
    <div class="sub">PID {{ service_pid or 'N/A' }}</div>
  </div>
  <div class="stat">
    <div class="label">Total Bids</div>
    <div class="value cyan">{{ total_bids }}</div>
    <div class="sub">across {{ unique_jobs }} jobs</div>
  </div>
  <div class="stat">
    <div class="label">Won / Delivered</div>
    <div class="value green">{{ won }} / {{ delivered }}</div>
    <div class="sub">{{ pending }} pending | {{ rejected }} rejected</div>
  </div>
  <div class="stat">
    <div class="label">Earnings</div>
    <div class="value purple">{{ "%.1f"|format(earned) }} NEAR</div>
    <div class="sub">wallet balance: {{ "%.2f"|format(balance) }} NEAR</div>
  </div>
  <div class="stat">
    <div class="label">Acceptance Rate</div>
    <div class="value yellow">{{ "%.0f"|format(accept_rate) }}%</div>
    <div class="bar"><div class="bar-fill" style="width:{{ accept_rate }}%;background:var(--yellow)"></div></div>
  </div>
</div>

<div class="section">
<h2>Bid Breakdown by Category</h2>
<div class="grid">
  {% for cat, count in categories.items() %}
  <div class="stat">
    <div class="label">{{ cat }}</div>
    <div class="value" style="font-size:22px">{{ count }}</div>
  </div>
  {% endfor %}
</div>
</div>

<div class="section">
<h2>Recent Bids ({{ bids|length }} shown)</h2>
<table>
<thead><tr><th>#</th><th>Title</th><th>Category</th><th>Amount</th><th>Match</th><th>Status</th><th>Placed</th></tr></thead>
<tbody>
{% for b in bids %}
<tr>
  <td>{{ loop.index }}</td>
  <td class="truncate">{{ b.title[:55] }}</td>
  <td>{{ b.category }}</td>
  <td>{{ b.amount }} N</td>
  <td>{{ "%.0f"|format(b.match_score * 100) }}%</td>
  <td><span class="badge badge-{{ b.status }}">{{ b.status }}</span></td>
  <td>{{ b.placed_at[:16] if b.placed_at else '' }}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>

{% if deliveries %}
<div class="section">
<h2>Deliveries</h2>
<table>
<thead><tr><th>Title</th><th>Category</th><th>Amount</th><th>Deliverable</th><th>Revisions</th></tr></thead>
<tbody>
{% for d in deliveries %}
<tr>
  <td class="truncate">{{ d.title[:55] }}</td>
  <td>{{ d.category }}</td>
  <td>{{ d.amount }} N</td>
  <td>{% if d.deliverable_url %}<a href="{{ d.deliverable_url }}" target="_blank">View</a>{% else %}-{% endif %}</td>
  <td>{{ d.revision_count or 0 }}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
{% endif %}

<div class="section">
<h2>Recent Logs</h2>
<div class="log-box">{{ log_tail }}</div>
</div>

</body>
</html>
"""


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"bids_placed": {}, "total_bids": 0, "total_earned": 0.0}


def get_wallet_balance() -> float:
    try:
        r = requests.get(f"{API_BASE}/v1/wallet/balance", headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        return float(data.get("balance", 0))
    except Exception:
        return 0.0


def get_service_status() -> tuple:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "near-autobidder"],
            capture_output=True, text=True, timeout=5,
        )
        active = result.stdout.strip() == "active"
        pid = ""
        if active:
            p = subprocess.run(
                ["systemctl", "show", "near-autobidder", "--property=MainPID"],
                capture_output=True, text=True, timeout=5,
            )
            pid = p.stdout.strip().split("=")[-1]
        return active, pid
    except Exception:
        return False, ""


def get_log_tail(n=40) -> str:
    """H-4 fix: Read only the tail of the log file efficiently."""
    try:
        if not LOG_FILE.exists():
            return "(no logs available)"
        with open(LOG_FILE, "rb") as f:
            # Seek to end, then read backwards to find N newlines
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return "(empty log)"
            # Read last 32KB max — more than enough for 40 lines
            chunk_size = min(size, 32768)
            f.seek(size - chunk_size)
            data = f.read().decode("utf-8", errors="replace")
            lines = data.splitlines()
            return "\n".join(lines[-n:])
    except Exception:
        return "(error reading logs)"


@app.route("/")
@auth_required
def index():
    state = load_state()
    bids_placed = state.get("bids_placed", {})

    # Compute stats
    all_bids = []
    categories = {}
    won = delivered = completed = rejected = pending = 0

    for job_id, info in bids_placed.items():
        status = info.get("status", "pending")
        cat = info.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1

        if status == "accepted":
            won += 1
        elif status == "delivered":
            delivered += 1
        elif status == "completed":
            completed += 1
        elif status == "rejected":
            rejected += 1
        else:
            pending += 1

        all_bids.append({
            "title": info.get("title", job_id[:12]),
            "category": cat,
            "amount": info.get("amount", 0),
            "match_score": info.get("match_score", 0),
            "status": status,
            "placed_at": info.get("placed_at", ""),
            "deliverable_url": info.get("deliverable_url", ""),
            "revision_count": info.get("revision_count", 0),
        })

    # Sort by placed_at descending
    all_bids.sort(key=lambda x: x["placed_at"], reverse=True)

    # Deliveries are bids with status delivered/completed
    deliveries = [b for b in all_bids if b["status"] in ("delivered", "completed")]

    total_decided = won + delivered + completed + rejected
    accept_rate = ((won + delivered + completed) / total_decided * 100) if total_decided > 0 else 0

    service_active, service_pid = get_service_status()
    balance = get_wallet_balance()

    # Sort categories by count descending
    categories = dict(sorted(categories.items(), key=lambda x: -x[1]))

    return render_template_string(
        DASHBOARD_HTML,
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        service_active=service_active,
        service_pid=service_pid,
        total_bids=state.get("total_bids", len(bids_placed)),
        unique_jobs=len(bids_placed),
        won=won + delivered + completed,
        delivered=delivered + completed,
        pending=pending,
        rejected=rejected,
        earned=state.get("total_earned", 0),
        balance=balance,
        accept_rate=accept_rate,
        categories=categories,
        bids=all_bids[:50],  # Show latest 50
        deliveries=deliveries,
        log_tail=get_log_tail(),
    )


@app.route("/api/status")
@auth_required
def api_status():
    state = load_state()
    service_active, service_pid = get_service_status()
    return {
        "service": "running" if service_active else "stopped",
        "pid": service_pid,
        "total_bids": state.get("total_bids", 0),
        "total_earned": state.get("total_earned", 0),
        "bids_count": len(state.get("bids_placed", {})),
    }


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=3010, debug=False)
