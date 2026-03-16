"""
==============================================================================
MOLTY ROYALE - MONITORING DASHBOARD
==============================================================================
"""

import os
import json
import time
from pathlib import Path
from flask import Flask, jsonify, render_template, request, abort, redirect

app = Flask(__name__)

PORT          = int(os.environ.get("DASHBOARD_PORT", "8080"))
PASSWORD      = os.environ.get("DASHBOARD_PASSWORD", "")
AGENT_COUNT   = int(os.environ.get("AGENT_COUNT", "5"))
DATA_BASE_DIR = os.environ.get("DATA_BASE_DIR", "data")

def is_auth(req):
    if not PASSWORD:
        return True
    # Cek dari query string ?pw=xxx ATAU cookie
    return (
        req.args.get("pw") == PASSWORD or
        req.args.get("token") == PASSWORD or
        req.cookies.get("pw") == PASSWORD
    )

def read_json(path, default):
    try:
        if Path(path).exists():
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return default

def get_agent_data(index):
    data_dir = Path(DATA_BASE_DIR) / f"agent_{index}"
    history  = read_json(data_dir / "game_history.json", [])
    weights  = read_json(data_dir / "strategy_weights.json", {})
    combat   = read_json(data_dir / "combat_log.json", [])

    total_games = len(history)
    wins        = sum(1 for g in history if g.get("is_winner"))
    total_kills = sum(g.get("kills", 0) for g in history)
    total_moltz = sum(g.get("moltz_earned", 0) for g in history)
    win_rate    = round(wins / total_games * 100, 1) if total_games > 0 else 0

    recent      = history[-10:] if history else []
    recent_wins = sum(1 for g in recent if g.get("is_winner"))
    recent_wr   = round(recent_wins / len(recent) * 100, 1) if recent else 0

    total_combat = len(combat)
    combat_wins  = sum(1 for c in combat if c.get("won"))
    combat_wr    = round(combat_wins / total_combat * 100, 1) if total_combat > 0 else 0

    api_key = os.environ.get(f"API_KEY_{index}", "")
    wallet  = os.environ.get(f"WALLET_{index}", "")

    return {
        "index"         : index,
        "name"          : os.environ.get(f"AGENT_NAME_{index}", f"MoltyBot_{index}"),
        "key_display"   : f"{api_key[:12]}...{api_key[-4:]}" if len(api_key) > 16 else "***",
        "wallet_display": f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else "***",
        "active"        : bool(api_key and len(api_key) > 10),
        "stats": {
            "total_games": total_games,
            "wins"       : wins,
            "win_rate"   : win_rate,
            "total_kills": total_kills,
            "total_moltz": total_moltz,
            "recent_wr"  : recent_wr,
            "combat_wr"  : combat_wr,
        },
        "weights"      : weights,
        "recent_games" : list(reversed(recent)),
        "death_causes" : {},
    }

def get_summary(agents):
    active  = [a for a in agents if a["active"]]
    total_g = sum(a["stats"]["total_games"] for a in active)
    total_w = sum(a["stats"]["wins"] for a in active)
    total_k = sum(a["stats"]["total_kills"] for a in active)
    total_m = sum(a["stats"]["total_moltz"] for a in active)
    return {
        "total_agents" : len(active),
        "total_games"  : total_g,
        "total_wins"   : total_w,
        "total_kills"  : total_k,
        "total_moltz"  : total_m,
        "avg_win_rate" : round(total_w / total_g * 100, 1) if total_g > 0 else 0,
    }

@app.route("/")
def index():
    if not is_auth(request):
        return render_template("login.html", error=False)
    pw = request.args.get("pw", "")
    return render_template("dashboard.html", pw=pw)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == PASSWORD:
            resp = redirect(f"/?pw={pw}")
            resp.set_cookie("pw", pw, max_age=86400 * 30)
            return resp
        return render_template("login.html", error=True)
    return render_template("login.html", error=False)

@app.route("/api/agents")
def api_agents():
    if not is_auth(request):
        abort(401)
    agents  = [get_agent_data(i) for i in range(1, AGENT_COUNT + 1)]
    summary = get_summary(agents)
    return jsonify({"agents": agents, "summary": summary, "ts": int(time.time())})

if __name__ == "__main__":
    print(f"Dashboard running on :{PORT}")
    if not PASSWORD:
        print("WARNING: DASHBOARD_PASSWORD tidak diset!")
    app.run(host="0.0.0.0", port=PORT, debug=False)
