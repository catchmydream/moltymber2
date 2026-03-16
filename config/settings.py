import os

"""
==============================================================================
MOLTY ROYALE BOT - CONFIGURATION (MULTI-AGENT RAILWAY EDITION)
==============================================================================
Mendukung 5 agent sekaligus via environment variables.
Setiap Railway service cukup set AGENT_INDEX=1 s/d 5.

Di Railway, set variabel berikut per service:
  AGENT_INDEX=1          ← nomor agent (1-5)
  API_KEY_1=mr_live_...  ← API key agent 1
  WALLET_1=0xABC...      ← wallet agent 1
  API_KEY_2=mr_live_...  ← API key agent 2
  WALLET_2=0xDEF...      ← dst...
"""

# =============================================================================
# MULTI-AGENT RESOLVER
# =============================================================================
AGENT_INDEX = int(os.environ.get("AGENT_INDEX", "1"))

API_KEY = (
    os.environ.get(f"API_KEY_{AGENT_INDEX}")
    or os.environ.get("API_KEY", "mr_live_xxxxxxxxxxxxxxxxxxxx")
)

WALLET_ADDRESS = (
    os.environ.get(f"WALLET_{AGENT_INDEX}")
    or os.environ.get("WALLET_ADDRESS", "0xYourWalletAddressHere")
)

# =============================================================================
# API CONFIG
# =============================================================================
BASE_URL = os.environ.get("BASE_URL", "https://cdn.moltyroyale.com/api")

# =============================================================================
# GAME PREFERENCES
# =============================================================================
PREFERRED_GAME_TYPE = os.environ.get("PREFERRED_GAME_TYPE", "free")
AUTO_CREATE_GAME    = os.environ.get("AUTO_CREATE_GAME", "false").lower() == "true"
GAME_MAP_SIZE       = os.environ.get("GAME_MAP_SIZE", "medium")

# =============================================================================
# SURVIVAL THRESHOLDS
# =============================================================================
HP_CRITICAL        = int(os.environ.get("HP_CRITICAL", "65"))
HP_LOW             = int(os.environ.get("HP_LOW", "45"))
EP_MIN_ATTACK      = int(os.environ.get("EP_MIN_ATTACK", "2"))
EP_REST_THRESHOLD  = int(os.environ.get("EP_REST_THRESHOLD", "3"))

# =============================================================================
# COMBAT DECISION THRESHOLDS
# =============================================================================
WIN_PROBABILITY_ATTACK     = float(os.environ.get("WIN_PROBABILITY_ATTACK", "0.65"))
WIN_PROBABILITY_AGGRESSIVE = float(os.environ.get("WIN_PROBABILITY_AGGRESSIVE", "0.80"))

# =============================================================================
# LEARNING SYSTEM
# Data dir dipisah per agent agar tidak saling timpa
# =============================================================================
LEARNING_ENABLED = os.environ.get("LEARNING_ENABLED", "true").lower() == "true"
DATA_DIR         = os.environ.get("DATA_DIR", f"data/agent_{AGENT_INDEX}")
MIN_GAMES_FOR_ML = int(os.environ.get("MIN_GAMES_FOR_ML", "5"))
LEARNING_RATE    = float(os.environ.get("LEARNING_RATE", "0.1"))

# =============================================================================
# REDIS (OPTIONAL — bisa pakai Railway Redis add-on)
# =============================================================================
REDIS_ENABLED = os.environ.get("REDIS_ENABLED", "false").lower() == "true"
REDIS_HOST    = os.environ.get("REDIS_HOST", os.environ.get("REDISHOST", "localhost"))
REDIS_PORT    = int(os.environ.get("REDIS_PORT", os.environ.get("REDISPORT", "6379")))
REDIS_DB      = int(os.environ.get("REDIS_DB", str(AGENT_INDEX - 1)))  # DB 0-4 per agent

# =============================================================================
# LOGGING
# =============================================================================
LOG_LEVEL   = os.environ.get("LOG_LEVEL", "INFO")
LOG_TO_FILE = os.environ.get("LOG_TO_FILE", "true").lower() == "true"
LOG_FILE    = os.environ.get("LOG_FILE", f"logs/bot_agent_{AGENT_INDEX}.log")

# =============================================================================
# TIMING
# =============================================================================
TURN_INTERVAL         = int(os.environ.get("TURN_INTERVAL", "60"))
POLL_INTERVAL_WAITING = int(os.environ.get("POLL_INTERVAL_WAITING", "5"))
POLL_INTERVAL_DEAD    = int(os.environ.get("POLL_INTERVAL_DEAD", "60"))
ROOM_HUNT_INTERVAL    = int(os.environ.get("ROOM_HUNT_INTERVAL", "2"))
HEARTBEAT_INTERVAL    = int(os.environ.get("HEARTBEAT_INTERVAL", "300"))

# =============================================================================
# AGENT NAME (auto-generate jika tidak diset)
# =============================================================================
_default_name = f"MoltyBot_{AGENT_INDEX}"
AGENT_NAME = (
    os.environ.get(f"AGENT_NAME_{AGENT_INDEX}")
    or os.environ.get("AGENT_NAME", _default_name)
)
