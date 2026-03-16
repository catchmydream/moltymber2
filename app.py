"""
==============================================================================
MOLTY ROYALE - MONITORING DASHBOARD
==============================================================================
Dashboard web untuk memantau semua agent dari HP.
Berjalan sebagai Flask server, baca data JSON dari tiap agent.

ENV:
  DASHBOARD_PORT=8080        (default 8080)
  DASHBOARD_PASSWORD=secret  (wajib diset untuk keamanan)
  AGENT_COUNT=5
  DATA_BASE_DIR=data         (lokasi folder data/)
==============================================================================
"""

import os
import json
import time
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify, render_template, request, abort

app = Flask(__name__)

# Config
PORT          = int(os.environ.get("DASHBOARD_PORT", "8080"))
PASSWORD      = os.environ.get("DASHBOARD_PASSWORD", "")
AGENT_COUNT   = int(os.environ.get("AGENT_COUNT", "5"))
DATA_BASE_DIR = os.environ.get("DATA_BASE_DIR", "data")

# ─── Auth middleware ──────────────────────────────────────────────────────────
@app.before_request
def check_auth():
    if not PASSWORD:
        return  # Kalau password tidak diset, akses bebas (tidak disarankan)
    token = request.args.get("token") or request.cookies.get("token")
    if request.path == "/login":
        return
    if token != PASSWORD:
        if request.path.startswith("/api/"):
            abort(401)
        return render_template("login.html")

# ─── Data reader ─────────────────────────────────────────────────────────────
def read_json(path: Path, default):
    try:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return default

def get_agent_data(index: int) -> dict:
    """Baca semua data dari 1 agent."""
    data_dir = Path(DATA_BASE_DIR) / f"agent_{index}"

    history  = read_json(data_dir / "game_history.json", [])
    weights  = read_json(data_dir / "strategy_weights.json", {})
    combat   = read_json(data_dir / "combat_log.json", [])

    # Hitung statistik
    total_games = len(history)
    wins        = sum(1 for g in history if g.get("is_winner"))
    total_kills = sum(g.get("kills", 0) for g in history)
    total_moltz = sum(g.get("moltz_earned", 0) for g in history)
    win_rate    = (wins / total_games * 100) if total_games > 0 else 0

    # 10 game terakhir
    recent = history[-10:] if history else []
    recent_wins = sum(1 for g in recent if g.get("is_winner"))
    recent_wr   = (recent_wins / len(recent) * 100) if recent else 0

    # Game sekarang (game terakhir yang belum selesai atau sedang berjalan)
    current_game = None
    if history:
        last = history[-1]
        # Anggap "current" kalau dimulai dalam 2 jam terakhir
        started = last.get("started_at", 0)
        if isinstance(started, str):
            try:
                started = datetime.fromisoformat(started).timestamp()
            except Exception:
                started = 0
        if time.time() - started < 7200:
            current_game = last

    # Combat stats
    total_combat  = len(combat)
    combat_wins   = sum(1 for c in combat if c.get("won"))
    combat_wr     = (combat_wins / total_combat * 100) if total_combat > 0 else 0

    # Death causes
    death_causes = {}
    for g in history:
        dc = g.get("death_cause", "unknown") or "unknown"
        death_causes[dc] = death_causes.get(dc, 0) + 1

    # API key (tampilkan parsial untuk identifikasi)
    api_key = os.environ.get(f"API_KEY_{index}", "")
    key_display = f"{api_key[:12]}...{api_key[-4:]}" if len(api_key) > 16 else "***"

    wallet = os.environ.get(f"WALLET_{index}", "")
    wallet_display = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else "***"

    return {
        "index"        : index,
        "key_display"  : key_display,
        "wallet_display": wallet_display,
        "name"         : os.environ.get(f"AGENT_NAME_{index}", f"MoltyBot_{index}"),
        "active"       : bool(api_key and len(api_key) > 10),
        "stats": {
            "total_games" : total_games,
            "wins"        : wins,
            "win_rate"    : round(win_rate, 1),
            "total_kills" : total_kills,
            "total_moltz" : total_moltz,
            "recent_wr"   : round(recent_wr, 1),
            "combat_wr"   : round(combat_wr, 1),
        },
        "weights"      : weights,
        "recent_games" : list(reversed(recent)),
        "current_game" : current_game,
        "death_causes" : death_causes,
    }

def get_all_agents():
    return [get_agent_data(i) for i in range(1, AGENT_COUNT + 1)]

def get_summary(agents):
    active    = [a for a in agents if a["active"]]
    total_g   = sum(a["stats"]["total_games"] for a in active)
    total_w   = sum(a["stats"]["wins"] for a in active)
    total_k   = sum(a["stats"]["total_kills"] for a in active)
    total_m   = sum(a["stats"]["total_moltz"] for a in active)
    avg_wr    = (total_w / total_g * 100) if total_g > 0 else 0
    return {
        "total_agents"  : len(active),
        "total_games"   : total_g,
        "total_wins"    : total_w,
        "total_kills"   : total_k,
        "total_moltz"   : total_m,
        "avg_win_rate"  : round(avg_wr, 1),
    }

# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("dashboard.html", password=PASSWORD)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("password","")
        if pw == PASSWORD:
            from flask import make_response, redirect
            resp = make_response(redirect("/"))
            resp.set_cookie("token", pw, max_age=86400*7)
            return resp
    return render_template("login.html", error=request.method=="POST")

@app.route("/api/agents")
def api_agents():
    agents  = get_all_agents()
    summary = get_summary(agents)
    return jsonify({"agents": agents, "summary": summary, "ts": int(time.time())})

@app.route("/api/agent/<int:index>")
def api_agent(index):
    if index < 1 or index > AGENT_COUNT:
        abort(404)
    return jsonify(get_agent_data(index))

# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Dashboard running on port {PORT}")
    if not PASSWORD:
        print("⚠ WARNING: DASHBOARD_PASSWORD tidak diset — akses tidak terproteksi!")
    app.run(host="0.0.0.0", port=PORT, debug=False)
