import os, json, time, requests
from pathlib import Path
from flask import Flask, jsonify, render_template, request, abort, redirect, make_response

app = Flask(__name__)

PORT          = int(os.environ.get("DASHBOARD_PORT", "8080"))
PASSWORD      = os.environ.get("DASHBOARD_PASSWORD", "")
AGENT_COUNT   = int(os.environ.get("AGENT_COUNT", "5"))
DATA_BASE_DIR = os.environ.get("DATA_BASE_DIR", "data")
BASE_URL      = os.environ.get("BASE_URL", "https://cdn.moltyroyale.com/api")

def is_auth():
    if not PASSWORD:
        return True
    pw = request.args.get("pw","") or request.cookies.get("pw","")
    return pw == PASSWORD

def api_get(endpoint, api_key, timeout=8):
    try:
        r = requests.get(
            f"{BASE_URL}{endpoint}",
            headers={"X-API-Key": api_key},
            timeout=timeout
        )
        if r.status_code == 200:
            d = r.json()
            return d.get("data", d)
    except Exception:
        pass
    return None

def read_json(path, default):
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return default

def get_agent_live(index):
    api_key = os.environ.get(f"API_KEY_{index}", "")
    if not api_key or len(api_key) < 10:
        return {"index": index, "active": False, "error": "API key tidak diset"}

    account = api_get("/accounts/me", api_key)
    if not account:
        return {"index": index, "active": False, "error": "UNAUTHORIZED"}

    # Cari game aktif dan ambil state karakter
    character    = None
    current_game = None

    current_games = account.get("currentGames", [])
    if isinstance(current_games, dict):
        current_games = [current_games]

    for g in current_games:
        gid    = g.get("gameId") or g.get("id", "")
        aid    = g.get("agentId", "")
        status = g.get("gameStatus", g.get("status",""))
        if not gid or not aid:
            continue
        if status not in ("running","waiting"):
            continue

        state = api_get(f"/games/{gid}/agents/{aid}/state", api_key)
        if state:
            sd  = state.get("self", {})
            reg = state.get("currentRegion", {})
            character = {
                "name"            : sd.get("name", account.get("name","?")),
                "hp"              : sd.get("hp", 0),
                "ep"              : sd.get("ep", 0),
                "max_ep"          : sd.get("maxEp", 10),
                "atk"             : sd.get("atk", 10),
                "def"             : sd.get("def", 5),
                "kills"           : sd.get("kills", 0),
                "is_alive"        : sd.get("isAlive", True),
                "weapon"          : (sd.get("equippedWeapon") or {}).get("typeId","Fist"),
                "inventory"       : sd.get("inventory", []),
                "region"          : reg.get("name","?"),
                "is_dz"           : reg.get("isDeathZone", False),
                "weather"         : reg.get("weather","clear"),
                "connections"     : len(reg.get("connections",[])),
                "visible_agents"  : len(state.get("visibleAgents",[])),
                "visible_monsters": len(state.get("visibleMonsters",[])),
                "game_status"     : state.get("gameStatus","?"),
            }
            current_game = {
                "game_id"   : gid,
                "agent_id"  : aid,
                "is_alive"  : g.get("isAlive", True),
                "entry_type": g.get("entryType","free"),
                "status"    : status,
            }
        break

    # Data karir dari file lokal
    d       = Path(DATA_BASE_DIR) / f"agent_{index}"
    history = read_json(d / "game_history.json", [])
    weights = read_json(d / "strategy_weights.json", {})
    tg = len(history)
    w  = sum(1 for g in history if g.get("is_winner"))
    tk = sum(g.get("kills",0) for g in history)
    tm = sum(g.get("moltz_earned",0) for g in history)
    wr = round(w/tg*100,1) if tg else 0
    recent = history[-10:]
    rwr    = round(sum(1 for g in recent if g.get("is_winner"))/len(recent)*100,1) if recent else 0

    wl = os.environ.get(f"WALLET_{index}","")
    return {
        "index"             : index,
        "name"              : account.get("name", f"MoltyBot_{index}"),
        "key_display"       : f"{api_key[:12]}...{api_key[-4:]}",
        "wallet_display"    : f"{wl[:6]}...{wl[-4:]}" if len(wl)>10 else "***",
        "active"            : True,
        "balance"           : account.get("balance", 0),
        "total_wins_server" : account.get("totalWins", 0),
        "total_games_server": account.get("totalGames", 0),
        "character"         : character,
        "current_game"      : current_game,
        "stats": {
            "total_games": tg, "wins": w, "win_rate": wr,
            "total_kills": tk, "total_moltz": tm, "recent_wr": rwr,
        },
        "weights"      : weights,
        "recent_games" : list(reversed(recent[-8:])),
        "error"        : None,
    }

def get_my_game_rooms(agents):
    """
    Ambil hanya room yang ada agent kamu.
    Kumpulkan game_id unik dari semua agent, lalu fetch state tiap room.
    """
    # Kumpulkan game_id unik + api_key yang bisa dipakai + agent per game
    game_map = {}  # game_id -> {api_key, agents:[]}
    for a in agents:
        if not a.get("active") or not a.get("current_game"):
            continue
        cg  = a["current_game"]
        gid = cg.get("game_id","")
        if not gid:
            continue
        if gid not in game_map:
            game_map[gid] = {
                "api_key"   : os.environ.get(f"API_KEY_{a['index']}",""),
                "status"    : cg.get("status","?"),
                "entry_type": cg.get("entry_type","free"),
                "agents"    : [],
            }
        # Tambahkan karakter agent ini ke room
        if a.get("character"):
            c = a["character"]
            game_map[gid]["agents"].append({
                "name"    : a["name"],
                "hp"      : c["hp"],
                "ep"      : c["ep"],
                "kills"   : c["kills"],
                "isAlive" : c["is_alive"],
                "region"  : c["region"],
                "weapon"  : c["weapon"],
                "agent_index": a["index"],
            })

    rooms = []
    for gid, info in game_map.items():
        # Fetch info game dari server
        ak   = info["api_key"]
        gdata = api_get(f"/games/{gid}", ak) if ak else None

        room = {
            "id"           : gid,
            "name"         : (gdata or {}).get("name", "Battle Room"),
            "status"       : info["status"],
            "mapSize"      : (gdata or {}).get("mapSize","?"),
            "maxAgents"    : (gdata or {}).get("maxAgents","?"),
            "currentAgents": (gdata or {}).get("currentAgents", len(info["agents"])),
            "entry_type"   : info["entry_type"],
            "agents"       : info["agents"],
        }
        rooms.append(room)

    return rooms

# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if not is_auth():
        return render_template("login.html")
    pw   = request.args.get("pw","")
    resp = make_response(render_template("dashboard.html", pw=pw))
    if pw:
        resp.set_cookie("pw", pw, max_age=86400*30, samesite="Lax")
    return resp

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("password","")
        if pw == PASSWORD:
            resp = make_response(redirect(f"/?pw={pw}"))
            resp.set_cookie("pw", pw, max_age=86400*30, samesite="Lax")
            return resp
        return render_template("login.html", error=True)
    return render_template("login.html", error=False)

@app.route("/api/dashboard")
def api_dashboard():
    if not is_auth():
        abort(401)

    agents = []
    for i in range(1, AGENT_COUNT+1):
        try:
            a = get_agent_live(i)
            if a:
                agents.append(a)
        except Exception as e:
            agents.append({"index":i,"error":str(e),"active":False})

    rooms = get_my_game_rooms(agents)

    total_g = sum(a.get("stats",{}).get("total_games",0) for a in agents if a.get("active"))
    total_w = sum(a.get("stats",{}).get("wins",0) for a in agents if a.get("active"))
    total_m = sum(a.get("balance",0) for a in agents if a.get("active"))

    return jsonify({
        "agents" : agents,
        "rooms"  : rooms,
        "summary": {
            "total_agents": sum(1 for a in agents if a.get("active")),
            "total_games" : total_g,
            "avg_win_rate": round(total_w/total_g*100,1) if total_g else 0,
            "total_moltz" : total_m,
            "in_game"     : sum(1 for a in agents if a.get("character")),
        },
        "ts": int(time.time())
    })

if __name__ == "__main__":
    print(f"Dashboard :{PORT}")
    if not PASSWORD:
        print("WARNING: DASHBOARD_PASSWORD tidak diset!")
    app.run(host="0.0.0.0", port=PORT, debug=False)
