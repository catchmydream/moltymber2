"""
==============================================================================
MOLTY ROYALE BOT - MULTI-AGENT LAUNCHER (1 Service, 5 Agents)
==============================================================================
Jalankan 5 agent sekaligus dalam 1 Railway service menggunakan threading.
Setiap agent berjalan di thread terpisah dengan API key & wallet sendiri.

ENV Variables yang dibutuhkan:
  AGENT_COUNT=5
  API_KEY_1=mr_live_...   WALLET_1=0xAAA...
  API_KEY_2=mr_live_...   WALLET_2=0xBBB...
  API_KEY_3=mr_live_...   WALLET_3=0xCCC...
  API_KEY_4=mr_live_...   WALLET_4=0xDDD...
  API_KEY_5=mr_live_...   WALLET_5=0xEEE...
==============================================================================
"""

import os
import time
import logging
import threading
import sys
from typing import Optional

from core.api_client import APIClient, APIError
from core.analyzer import StateAnalyzer
from core.strategy import StrategyEngine
from learning.memory import GameMemory
from learning.ml_engine import LearningEngine

# =============================================================================
# GLOBAL CONFIG
# =============================================================================
BASE_URL            = os.environ.get("BASE_URL", "https://cdn.moltyroyale.com/api")
AGENT_COUNT         = int(os.environ.get("AGENT_COUNT", "5"))
LOG_LEVEL           = os.environ.get("LOG_LEVEL", "INFO")
PREFERRED_GAME_TYPE = os.environ.get("PREFERRED_GAME_TYPE", "free")
AUTO_CREATE_GAME    = os.environ.get("AUTO_CREATE_GAME", "false").lower() == "true"
GAME_MAP_SIZE       = os.environ.get("GAME_MAP_SIZE", "medium")
HP_CRITICAL         = int(os.environ.get("HP_CRITICAL", "65"))
HP_LOW              = int(os.environ.get("HP_LOW", "45"))
EP_MIN_ATTACK       = int(os.environ.get("EP_MIN_ATTACK", "2"))
EP_REST_THRESHOLD   = int(os.environ.get("EP_REST_THRESHOLD", "3"))
LEARNING_ENABLED    = os.environ.get("LEARNING_ENABLED", "true").lower() == "true"
MIN_GAMES_FOR_ML    = int(os.environ.get("MIN_GAMES_FOR_ML", "5"))
TURN_INTERVAL       = int(os.environ.get("TURN_INTERVAL", "60"))
POLL_INTERVAL_WAITING = int(os.environ.get("POLL_INTERVAL_WAITING", "5"))
POLL_INTERVAL_DEAD  = int(os.environ.get("POLL_INTERVAL_DEAD", "60"))
ROOM_HUNT_INTERVAL  = int(os.environ.get("ROOM_HUNT_INTERVAL", "2"))

# =============================================================================
# LOGGING - warna berbeda per agent
# =============================================================================
AGENT_COLORS = {
    1: "\033[1;36m",  # Cyan
    2: "\033[1;32m",  # Green
    3: "\033[1;35m",  # Magenta
    4: "\033[1;33m",  # Yellow
    5: "\033[1;34m",  # Blue
}

class AgentFormatter(logging.Formatter):
    RESET = "\033[0m"
    DIM   = "\033[2m"
    LEVEL_COLORS = {
        "DEBUG"   : "\033[0;36m",
        "INFO"    : "\033[0;37m",
        "WARNING" : "\033[1;33m",
        "ERROR"   : "\033[0;31m",
        "CRITICAL": "\033[1;31m",
    }
    def format(self, record):
        ts    = self.formatTime(record, "%H:%M:%S")
        lvl   = record.levelname
        lc    = self.LEVEL_COLORS.get(lvl, "")
        name  = record.name.split(".")[0]
        idx   = int(name.replace("Agent","")) if name.startswith("Agent") else 0
        ac    = AGENT_COLORS.get(idx, "")
        return (
            f"{self.DIM}{ts}{self.RESET}  "
            f"{lc}{lvl:<7}{self.RESET}  "
            f"{ac}[{name:<8}]{self.RESET}  "
            f"{record.getMessage()}"
        )

def setup_logging():
    os.makedirs("logs", exist_ok=True)
    level   = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(AgentFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    for noisy in ["urllib3","requests","redis","charset_normalizer"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

# =============================================================================
# AGENT RUNNER - 1 instance per agent
# =============================================================================
class AgentRunner:
    def __init__(self, index: int):
        self.index      = index
        self.api_key    = os.environ.get(f"API_KEY_{index}") or os.environ.get("API_KEY","")
        self.wallet     = os.environ.get(f"WALLET_{index}") or os.environ.get("WALLET_ADDRESS","")
        self.name       = os.environ.get(f"AGENT_NAME_{index}", f"MoltyBot_{index}")
        self.data_dir   = f"data/agent_{index}"
        self.logger     = logging.getLogger(f"Agent{index}.Loop")
        self.game_id    : Optional[str] = None
        self.agent_id   : Optional[str] = None
        self.agent_name : str = self.name
        self.valid      : bool = False

        # Validasi API key
        if not self.api_key or len(self.api_key) < 10:
            self.logger.error(f"API_KEY_{index} tidak diset! Agent ini dilewati.")
            return

        os.makedirs(self.data_dir, exist_ok=True)

        self.api      = APIClient(BASE_URL, self.api_key)
        self.memory   = GameMemory(data_dir=self.data_dir, redis_client=None)
        self.learning = LearningEngine(self.memory, min_games_for_ml=MIN_GAMES_FOR_ML)
        self.analyzer = StateAnalyzer(
            hp_critical=HP_CRITICAL, hp_low=HP_LOW,
            ep_min_attack=EP_MIN_ATTACK, ep_rest_threshold=EP_REST_THRESHOLD
        )
        self.strategy = StrategyEngine(self.analyzer, self.memory, self.learning)
        self.valid = True
        self.logger.info(f"Agent {index} siap | key:{self.api_key[:12]}... | wallet:{self.wallet[:10]}...")

    # ------ Account -------------------------------------------------------
    def ensure_account(self):
        try:
            account         = self.api.get_account()
            self.agent_name = account.get("name", self.name)
            self.logger.info(
                f"Login OK: {self.agent_name} | "
                f"Wins:{account.get('totalWins')}/{account.get('totalGames')}"
            )
            # Daftarkan wallet jika belum
            wallet_server = account.get("walletAddress") or account.get("wallet")
            if not wallet_server and self.wallet and len(self.wallet) == 42:
                try:
                    self.api.set_wallet(self.wallet)
                    self.logger.info(f"Wallet terdaftar: {self.wallet[:10]}...")
                except Exception as e:
                    self.logger.warning(f"Gagal daftar wallet: {e}")
            elif not wallet_server:
                self.logger.warning("Wallet belum dikonfigurasi!")

            # Cek game aktif
            current_games = (
                account.get("currentGames") or
                account.get("activeGames") or
                account.get("currentGame") or []
            )
            if isinstance(current_games, dict):
                current_games = [current_games]

            for game in current_games:
                gid    = game.get("gameId") or game.get("id","")
                aid    = game.get("agentId") or game.get("agent_id","")
                status = game.get("gameStatus") or game.get("status","")
                alive  = game.get("isAlive", True)
                etype  = game.get("entryType", PREFERRED_GAME_TYPE)
                if not gid or status == "finished":
                    continue
                if status in ("running","waiting"):
                    if alive and etype == PREFERRED_GAME_TYPE:
                        self.game_id  = gid
                        self.agent_id = aid
                        self.logger.info(f"Resuming game {gid[:8]}...")
                        return "resume"
                    else:
                        self._active_game_id = gid
                        return "waiting"
        except APIError as e:
            self.logger.error(f"Account error: {e}")
            return "error"
        return False

    def wait_for_game_finish(self, game_id: str):
        self.logger.info(f"Tunggu game {game_id[:8]}... selesai...")
        while True:
            try:
                game = self.api.get_game(game_id)
                if game.get("status") == "finished":
                    return
                time.sleep(POLL_INTERVAL_DEAD)
            except APIError as e:
                if e.code == "GAME_NOT_FOUND":
                    return
                time.sleep(15)
            except Exception:
                time.sleep(15)

    # ------ Join game ------------------------------------------------------
    def find_and_join_game(self) -> bool:
        import re
        attempt = 0
        while True:
            attempt += 1
            try:
                games    = self.api.list_games_fast(status="waiting")
                matching = [g for g in games if g.get("entryType") == PREFERRED_GAME_TYPE]

                if matching:
                    game_id = matching[0]["id"]
                    try:
                        agent         = self.api.register_agent_fast(game_id, self.agent_name)
                        self.game_id  = game_id
                        self.agent_id = agent["id"]
                        self.logger.info(f"Joined {game_id[:8]}... sebagai '{self.agent_name}'")
                        return True
                    except APIError as e:
                        if e.code in ("GAME_ALREADY_STARTED","MAX_AGENTS_REACHED"):
                            continue
                        elif e.code == "ACCOUNT_ALREADY_IN_GAME":
                            m = re.search(r"[Cc]urrent game[: ]+([0-9a-f-]{36})", str(e))
                            if m:
                                self.wait_for_game_finish(m.group(1))
                            else:
                                time.sleep(60)
                            continue
                        elif e.code == "ONE_AGENT_PER_API_KEY":
                            self.logger.warning("Sudah ada agent di game ini")
                            return False
                        self.logger.error(f"Join error: {e}")
                        continue
                elif AUTO_CREATE_GAME:
                    try:
                        self.api.create_game(
                            host_name=f"{self.agent_name}_Room",
                            map_size=GAME_MAP_SIZE,
                            entry_type=PREFERRED_GAME_TYPE
                        )
                    except APIError:
                        pass

                if attempt % 15 == 1:
                    self.logger.info(f"Hunting room... (attempt #{attempt})")
                time.sleep(ROOM_HUNT_INTERVAL)

            except Exception as e:
                self.logger.error(f"Error saat hunting: {e}")
                time.sleep(10)

    def wait_for_game_start(self):
        self.logger.info("Menunggu game mulai...")
        while True:
            try:
                status = self.api.get_game(self.game_id).get("status")
                if status == "running":
                    self.logger.info("Game MULAI!")
                    return
                elif status == "finished":
                    self.game_id = self.agent_id = None
                    return
                time.sleep(POLL_INTERVAL_WAITING)
            except APIError as e:
                self.logger.error(f"Error cek status: {e}")
                time.sleep(10)

    # ------ Game loop ------------------------------------------------------
    def run_game(self):
        self.memory.start_game(self.game_id, self.agent_id, self.agent_name)
        self.strategy.reset_for_new_game()

        turn_count       = 0
        last_action_time = 0
        death_cause      = None
        prev_kills       = 0
        prev_hp          = 100.0
        prev_action_type = ""
        prev_target      = {}
        prev_target_type = ""
        prev_my_stats    = {}

        if LEARNING_ENABLED and self.memory.games_played() >= MIN_GAMES_FOR_ML:
            self.learning.retrain(self.memory.get_recent_games(50))

        while True:
            loop_start = time.time()

            # Get state
            try:
                state = self.api.get_state(self.game_id, self.agent_id)
            except APIError as e:
                if e.code in ("GAME_NOT_FOUND","AGENT_NOT_FOUND"):
                    self.memory.end_game(
                        is_winner=False, final_rank=99,
                        final_hp=0, moltz_earned=0, death_cause="game_not_found"
                    )
                    self.game_id = self.agent_id = None
                    return False, 99
                self.logger.error(f"get_state error: {e}")
                time.sleep(10)
                continue

            # Cek game over
            game_status = state.get("gameStatus")
            self_data   = state.get("self", {})
            is_alive    = self_data.get("isAlive", True)

            if game_status == "finished" or not is_alive:
                result     = state.get("result") or {}
                is_winner  = result.get("isWinner", False)
                final_rank = result.get("finalRank") or 99
                rewards    = result.get("rewards", 0)
                final_hp   = self_data.get("hp", 0)

                label = "MENANG!" if is_winner else f"Rank #{final_rank}"
                self.logger.info(
                    f"GAME SELESAI — {label} | "
                    f"Rewards:{rewards} $Moltz | Turns:{turn_count}"
                )
                game_record = self.memory.end_game(
                    is_winner=is_winner, final_rank=final_rank,
                    final_hp=final_hp, moltz_earned=rewards,
                    death_cause=death_cause
                )
                if LEARNING_ENABLED and game_record:
                    self.learning.post_game_update(game_record)
                self.game_id = self.agent_id = None
                return is_winner, final_rank

            intel = self.analyzer.parse(state)

            # Timing
            elapsed = time.time() - last_action_time
            wait    = max(0, TURN_INTERVAL - elapsed - 1)
            if last_action_time > 0 and wait > 0:
                time.sleep(wait)

            # Decide & act
            main_action, reasoning, free_actions = self.strategy.decide(intel)

            for fa in free_actions:
                try:
                    self.api.take_action(self.game_id, self.agent_id, fa)
                except APIError:
                    pass

            thought = {"reasoning": reasoning, "plannedAction": main_action.get("type")}
            try:
                result = self.api.take_action(
                    self.game_id, self.agent_id, main_action, thought
                )
                last_action_time = time.time()
                turn_count += 1

                if result.get("success"):
                    atype = main_action.get("type","")
                    self.memory.record_turn(turn_count, intel, main_action, result)
                    self.memory.update_region_intel(
                        region_id=intel["region_id"],
                        region_name=intel["region_name"],
                        is_dz=intel["is_death_zone"],
                        terrain=intel.get("terrain",""),
                    )
                    if intel["is_death_zone"]:
                        death_cause = "death_zone"

                    dz  = " ⚡DZ!" if intel["is_death_zone"] else ""
                    ene = f" 👤x{len(intel['local_agents'])}" if intel["local_agents"] else ""
                    self.logger.info(
                        f"T{turn_count:03d} {atype:<8} "
                        f"HP:{intel['hp']:>3.0f} EP:{intel['ep']} "
                        f"{intel['region_name'][:12]}{dz}{ene}"
                    )

                    # Combat tracking
                    cur_kills = intel.get("kills", 0)
                    if prev_action_type == "attack" and prev_target:
                        still_here = any(
                            a.get("id") == prev_target.get("id")
                            for a in intel["local_agents"] + intel["local_monsters"]
                        )
                        won = (cur_kills > prev_kills) or (not still_here and prev_target.get("id"))
                        dd  = self.analyzer.calc_damage(
                            prev_my_stats.get("atk", 10),
                            prev_my_stats.get("weapon_bonus", 0),
                            prev_target.get("def", 5)
                        )
                        self.memory.record_combat(
                            target_id=prev_target.get("id","?"),
                            target_type=prev_target_type,
                            target_data=prev_target,
                            won=won,
                            damage_dealt=dd,
                            damage_taken=int(max(0, prev_hp - intel["hp"])),
                            my_stats=prev_my_stats,
                        )
                    prev_hp = intel["hp"]; prev_kills = cur_kills; prev_action_type = atype
                    if atype == "attack":
                        tid = main_action.get("targetId")
                        prev_target_type = main_action.get("targetType","agent")
                        all_t = intel["local_agents"] + intel["local_monsters"]
                        prev_target   = next((t for t in all_t if t.get("id")==tid), {"id":tid})
                        prev_my_stats = self.strategy._my_combat_stats(intel)
                    else:
                        prev_target = {}; prev_target_type = ""; prev_my_stats = {}

            except APIError as e:
                if e.code not in ("INSUFFICIENT_EP","GAME_NOT_RUNNING","ALREADY_ACTED"):
                    self.logger.error(f"Action error: {e}")

            elapsed = time.time() - loop_start
            if elapsed < 2.0:
                time.sleep(2.0 - elapsed)

    # ------ Main run loop --------------------------------------------------
    def run(self):
        if not self.valid:
            return

        self.logger.info(f"=== Agent {self.index} START ===")
        account_status = self.ensure_account()

        if account_status == "error":
            self.logger.error(f"Agent {self.index} berhenti — cek API_KEY_{self.index}")
            return

        if account_status == "waiting":
            gid = getattr(self, "_active_game_id", None)
            if gid:
                self.wait_for_game_finish(gid)
            account_status = False

        game_count = 0
        while True:
            try:
                game_count += 1
                self.logger.info(
                    f"--- GAME #{game_count} "
                    f"(career: {self.memory.games_played()}) ---"
                )
                if account_status != "resume":
                    if not self.find_and_join_game():
                        time.sleep(30)
                        continue
                account_status = False

                if self.game_id:
                    self.wait_for_game_start()

                if self.game_id and self.agent_id:
                    self.run_game()
                    time.sleep(5)

            except KeyboardInterrupt:
                self.logger.info(f"Agent {self.index} dihentikan.")
                self.memory.save_all()
                return
            except Exception as e:
                self.logger.error(f"Error: {e}", exc_info=True)
                self.memory.save_all()
                time.sleep(30)


# =============================================================================
# ENTRY POINT - jalankan semua agent dalam thread terpisah
# =============================================================================
if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger("Main")

    logger.info("=" * 60)
    logger.info(f"  MOLTY ROYALE MULTI-AGENT — {AGENT_COUNT} agents")
    logger.info("=" * 60)

    # Buat dan validasi semua agent
    agents  = [AgentRunner(i) for i in range(1, AGENT_COUNT + 1)]
    valid   = [a for a in agents if a.valid]
    invalid = AGENT_COUNT - len(valid)

    if invalid:
        logger.warning(f"{invalid} agent dilewati karena API key tidak diset.")

    if not valid:
        logger.error("Tidak ada agent yang valid! Periksa env variables.")
        sys.exit(1)

    logger.info(f"{len(valid)} agent akan dijalankan.")

    # Jalankan setiap agent di thread terpisah
    threads = []
    for agent in valid:
        t = threading.Thread(
            target=agent.run,
            name=f"Agent-{agent.index}",
            daemon=True
        )
        t.start()
        threads.append(t)
        time.sleep(2)  # Sedikit jeda antar start agar tidak serempak hit API

    logger.info(f"Semua {len(threads)} thread berjalan.")

    # Jaga proses utama tetap hidup
    try:
        while True:
            alive = sum(1 for t in threads if t.is_alive())
            logger.info(f"[HEARTBEAT] {alive}/{len(threads)} agent aktif")
            time.sleep(300)
    except KeyboardInterrupt:
        logger.info("Dihentikan oleh user. Semua agent akan stop.")
        sys.exit(0)
