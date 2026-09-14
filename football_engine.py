from __future__ import annotations

import math
import random
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# CONFIGURATION
# ============================================================

PITCH_WIDTH = 100.0
PITCH_HEIGHT = 60.0

MATCH_MINUTES = 90
MATCH_SECONDS = MATCH_MINUTES * 60

# 8 real minutes = 90 football minutes
REAL_MATCH_SECONDS = 480.0

# Engine update frequency
TICK_SECONDS = 0.20

# Football time advanced per real second
GAME_SECONDS_PER_REAL_SECOND = MATCH_SECONDS / REAL_MATCH_SECONDS

MAX_EVENTS = 400

HOME_GOAL_X = 100.0
AWAY_GOAL_X = 0.0

GOAL_Y_MIN = 23.0
GOAL_Y_MAX = 37.0

PENALTY_BOX_DEPTH = 18.0
PENALTY_BOX_WIDTH_MIN = 14.0
PENALTY_BOX_WIDTH_MAX = 46.0

HALFTIME_BREAK_SECONDS = 5.0

MAX_SUBSTITUTIONS = 5


# ============================================================
# FORMATIONS
# ============================================================

FORMATIONS: Dict[str, List[str]] = {
    "4-4-2": [
        "GK",
        "RB", "CB", "CB", "LB",
        "RM", "CM", "CM", "LM",
        "ST", "ST",
    ],

    "4-3-3": [
        "GK",
        "RB", "CB", "CB", "LB",
        "CM", "CM", "CM",
        "RW", "ST", "LW",
    ],

    "3-5-2": [
        "GK",
        "CB", "CB", "CB",
        "RWB", "CM", "CM", "CM", "LWB",
        "ST", "ST",
    ],

    "5-3-2": [
        "GK",
        "RWB", "CB", "CB", "CB", "LWB",
        "CM", "CM", "CM",
        "ST", "ST",
    ],

    "4-2-3-1": [
        "GK",
        "RB", "CB", "CB", "LB",
        "CDM", "CDM",
        "RW", "CAM", "LW",
        "ST",
    ],

    "4-1-4-1": [
        "GK",
        "RB", "CB", "CB", "LB",
        "CDM",
        "RM", "CM", "CM", "LM",
        "ST",
    ],
}


# ============================================================
# BASIC HELPERS
# ============================================================

def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_text(
    value: Any,
    fallback: str = "",
) -> str:
    if value is None:
        return fallback

    text = str(value).strip()

    return text if text else fallback


def distance(
    a: Dict[str, float],
    b: Dict[str, float],
) -> float:
    return math.hypot(
        a["x"] - b["x"],
        a["y"] - b["y"],
    )


def is_inside_box(
    x: float,
    y: float,
    defending_side: str,
) -> bool:

    if defending_side == "home":
        return (
            x <= PENALTY_BOX_DEPTH
            and PENALTY_BOX_WIDTH_MIN <= y <= PENALTY_BOX_WIDTH_MAX
        )

    return (
        x >= PITCH_WIDTH - PENALTY_BOX_DEPTH
        and PENALTY_BOX_WIDTH_MIN <= y <= PENALTY_BOX_WIDTH_MAX
    )


# ============================================================
# FOOTBALL MATCH
# ============================================================

class FootballMatch:

    def __init__(
        self,
        config: Dict[str, Any],
    ):

        self.lock = threading.RLock()

        self.match_id = normalize_text(
            config.get("matchId")
            or config.get("id"),
            str(uuid.uuid4()),
        )

        self.created_at = time.time()

        # created -> playing -> halftime -> playing -> finished
        self.status = "created"

        self.running = False
        self.finished = False

        # ----------------------------------------------------
        # MATCH CLOCK
        # ----------------------------------------------------

        # This is the real football clock.
        # It is NOT affected by frontend polling.
        self.match_clock_seconds = 0.0

        self.minute = 0
        self.second = 0

        self.injury_time_first_half = random.randint(1, 3)
        self.injury_time_second_half = random.randint(2, 5)

        self.halftime_done = False
        self.second_half_started = False

        self.halftime_started_at: Optional[float] = None

        self.last_tick = time.monotonic()

        # ----------------------------------------------------
        # SCORE
        # ----------------------------------------------------

        self.score = {
            "home": 0,
            "away": 0,
        }

        # ----------------------------------------------------
        # BALL
        # ----------------------------------------------------

        self.ball = {
            "x": 50.0,
            "y": 30.0,
            "vx": 0.0,
            "vy": 0.0,
            "owner": None,
            "team": None,
            "state": "dead",
        }

        self.possession_team = "home"
        self.attack_team = "home"

        self.possession_time = {
            "home": 0.0,
            "away": 0.0,
        }

        # ----------------------------------------------------
        # EVENTS
        # ----------------------------------------------------

        self.events: List[Dict[str, Any]] = []

        # ----------------------------------------------------
        # THREAD
        # ----------------------------------------------------

        self._loop_thread: Optional[threading.Thread] = None

        # ----------------------------------------------------
        # COOLDOWNS
        # ----------------------------------------------------

        self.cooldowns = {
            "shot": {
                "home": 0.0,
                "away": 0.0,
            },

            "corner": {
                "home": 0.0,
                "away": 0.0,
            },

            "foul": {
                "home": 0.0,
                "away": 0.0,
            },

            "action": {
                "home": 0.0,
                "away": 0.0,
            },
        }

        # ----------------------------------------------------
        # TEAMS
        # ----------------------------------------------------

        self.home = self._create_team(
            config.get("home") or {},
            "home",
            "Home",
        )

        self.away = self._create_team(
            config.get("away") or {},
            "away",
            "Away",
        )

        # ----------------------------------------------------
        # MATCH STATS
        # ----------------------------------------------------

        self.stats = {
            "home": self._empty_team_stats(),
            "away": self._empty_team_stats(),
        }

        # ----------------------------------------------------
        # POSITION PLAYERS
        # ----------------------------------------------------

        self._place_players()

        # ----------------------------------------------------
        # CREATE EVENT
        # ----------------------------------------------------

        self._event(
            "match_created",
            "Match created",
            None,
            None,
        )

    # ========================================================
    # TEAM CREATION
    # ========================================================

    def _create_team(
        self,
        source: Dict[str, Any],
        side: str,
        fallback_name: str,
    ) -> Dict[str, Any]:

        formation = normalize_text(
            source.get("formation"),
            "4-3-3",
        )

        if formation not in FORMATIONS:
            formation = "4-3-3"

        players_source = (
            source.get("players")
            or source.get("lineup")
            or source.get("squad")
            or []
        )

        bench_source = (
            source.get("bench")
            or source.get("substitutes")
            or []
        )

        players: List[Dict[str, Any]] = []

        if isinstance(players_source, list):

            for index, player in enumerate(
                players_source[:11]
            ):

                if isinstance(player, dict):

                    players.append(
                        self._create_player(
                            player,
                            index,
                            side,
                        )
                    )

        bench: List[Dict[str, Any]] = []

        if isinstance(bench_source, list):

            for index, player in enumerate(
                bench_source[:12]
            ):

                if isinstance(player, dict):

                    bench.append(
                        self._create_player(
                            player,
                            index + 11,
                            side,
                            is_bench=True,
                        )
                    )

        # ----------------------------------------------------
        # Fallback ONLY if frontend sent fewer than 11 players
        # ----------------------------------------------------

        while len(players) < 11:

            index = len(players)

            players.append(
                self._create_player(
                    {
                        "id": f"{side}-fallback-{index + 1}",
                        "name": f"{fallback_name} Player {index + 1}",
                        "number": index + 1,
                    },
                    index,
                    side,
                )
            )

        return {
            "id": normalize_text(
                source.get("id")
                or source.get("clubId"),
                side,
            ),

            "name": normalize_text(
                source.get("name")
                or source.get("clubName")
                or source.get("teamName"),
                fallback_name,
            ),

            "logo": normalize_text(
                source.get("logo")
                or source.get("logoUrl")
                or source.get("imageUrl"),
                "",
            ),

            "side": side,

            "formation": formation,

            "tactics": self._create_tactics(
                source.get("tactics") or {}
            ),

            "players": players,

            "bench": bench,

            "substitutionsUsed": 0,

            "stats": self._empty_team_stats(),

            "morale": 70.0,

            "momentum": 0.0,
        }

    # ========================================================
    # PLAYER CREATION
    # ========================================================

    def _create_player(
        self,
        source: Dict[str, Any],
        index: int,
        side: str,
        is_bench: bool = False,
    ) -> Dict[str, Any]:

        ratings = source.get("ratings")

        if not isinstance(ratings, dict):
            ratings = {}

        player_id = normalize_text(
            source.get("id")
            or source.get("playerId")
            or source.get("uid"),
            f"{side}-player-{index + 1}",
        )

        name = normalize_text(
            source.get("name")
            or source.get("displayName")
            or source.get("fullName"),
            f"Player {index + 1}",
        )

        position = normalize_text(
            source.get("position")
            or source.get("role")
            or source.get("preferredPosition"),
            "CM",
        ).upper()

        return {
            "id": player_id,

            "name": name,

            "number": safe_int(
                source.get("number")
                or source.get("shirtNumber"),
                index + 1,
            ),

            "position": position,

            "role": position,

            "side": side,

            "isBench": is_bench,

            "active": not is_bench,

            # Ratings
            "pace": self._rating(
                source,
                ratings,
                "pace",
                68,
            ),

            "passing": self._rating(
                source,
                ratings,
                "passing",
                68,
            ),

            "shooting": self._rating(
                source,
                ratings,
                "shooting",
                65,
            ),

            "dribbling": self._rating(
                source,
                ratings,
                "dribbling",
                67,
            ),

            "defending": self._rating(
                source,
                ratings,
                "defending",
                65,
            ),

            "stamina": self._rating(
                source,
                ratings,
                "stamina",
                75,
            ),

            "strength": self._rating(
                source,
                ratings,
                "strength",
                70,
            ),

            "vision": self._rating(
                source,
                ratings,
                "vision",
                68,
            ),

            "composure": self._rating(
                source,
                ratings,
                "composure",
                68,
            ),

            "goalkeeping": self._rating(
                source,
                ratings,
                "goalkeeping",
                65,
            ),

            # Physical state
            "energy": 100.0,

            "morale": 70.0,

            "injured": False,

            # Position
            "x": 50.0,

            "y": 30.0,

            "targetX": 50.0,

            "targetY": 30.0,

            # Ball
            "hasBall": False,

            "action": "idle",

            "lastActionAt": 0.0,

            "cooldown": 0.0,

            # Cards
            "yellowCards": 0,

            "redCard": False,

            "suspended": False,

            # Stats
            "stats": self._empty_player_stats(),
        }

    # ========================================================
    # RATINGS
    # ========================================================

    def _rating(
        self,
        source: Dict[str, Any],
        ratings: Dict[str, Any],
        key: str,
        default: float,
    ) -> float:

        value = source.get(key)

        if value is None:
            value = ratings.get(key)

        return clamp(
            safe_float(value, default),
            1,
            100,
        )

    # ========================================================
    # TACTICS
    # ========================================================

    def _create_tactics(
        self,
        source: Dict[str, Any],
    ) -> Dict[str, Any]:

        mentality = normalize_text(
            source.get("mentality"),
            "balanced",
        ).lower()

        if mentality not in [
            "defensive",
            "balanced",
            "attacking",
        ]:
            mentality = "balanced"

        pressing = normalize_text(
            source.get("pressing"),
            "medium",
        ).lower()

        if pressing not in [
            "low",
            "medium",
            "high",
        ]:
            pressing = "medium"

        defensive_line = normalize_text(
            source.get("defensiveLine"),
            "medium",
        ).lower()

        if defensive_line not in [
            "low",
            "medium",
            "high",
        ]:
            defensive_line = "medium"

        return {
            "mentality": mentality,

            "tempo": clamp(
                safe_float(
                    source.get("tempo"),
                    60,
                ),
                1,
                100,
            ),

            "pressing": pressing,

            "defensiveLine": defensive_line,

            "width": clamp(
                safe_float(
                    source.get("width"),
                    55,
                ),
                1,
                100,
            ),
        }

    # ========================================================
    # PLAYER STATS
    # ========================================================

    def _empty_player_stats(self) -> Dict[str, int]:

        return {
            "passes": 0,
            "passesCompleted": 0,
            "shots": 0,
            "shotsOnTarget": 0,
            "goals": 0,
            "assists": 0,
            "dribbles": 0,
            "tackles": 0,
            "interceptions": 0,
            "fouls": 0,
            "fouled": 0,
            "saves": 0,
            "corners": 0,
            "offsides": 0,
            "yellowCards": 0,
            "redCards": 0,
        }

    # ========================================================
    # TEAM STATS
    # ========================================================

    def _empty_team_stats(self) -> Dict[str, Any]:

        return {
            "possession": 50.0,
            "possessionTime": 0.0,

            "passes": 0,
            "passesCompleted": 0,

            "shots": 0,
            "shotsOnTarget": 0,

            "goals": 0,

            "corners": 0,

            "fouls": 0,

            "offsides": 0,

            "tackles": 0,

            "interceptions": 0,

            "saves": 0,

            "yellowCards": 0,

            "redCards": 0,

            "freeKicks": 0,

            "penalties": 0,
        }

    # ========================================================
    # FORMATION POSITIONS
    # ========================================================

    def _formation_positions(
        self,
        formation: str,
        side: str,
    ) -> List[Dict[str, float]]:

        if formation == "4-4-2":

            positions = [
                (8, 30),
                (22, 8),
                (18, 22),
                (18, 38),
                (22, 52),
                (42, 8),
                (40, 23),
                (40, 37),
                (42, 52),
                (70, 22),
                (70, 38),
            ]

        elif formation == "4-3-3":

            positions = [
                (8, 30),
                (22, 8),
                (18, 22),
                (18, 38),
                (22, 52),
                (42, 18),
                (40, 30),
                (42, 42),
                (68, 10),
                (74, 30),
                (68, 50),
            ]

        elif formation == "3-5-2":

            positions = [
                (8, 30),
                (20, 16),
                (18, 30),
                (20, 44),
                (38, 7),
                (36, 20),
                (38, 30),
                (36, 40),
                (38, 53),
                (70, 22),
                (70, 38),
            ]

        elif formation == "5-3-2":

            positions = [
                (8, 30),
                (18, 7),
                (15, 19),
                (16, 30),
                (15, 41),
                (18, 53),
                (38, 18),
                (38, 30),
                (38, 42),
                (70, 22),
                (70, 38),
            ]

        elif formation == "4-1-4-1":

            positions = [
                (8, 30),
                (22, 8),
                (18, 22),
                (18, 38),
                (22, 52),
                (33, 30),
                (48, 8),
                (44, 22),
                (44, 38),
                (48, 52),
                (72, 30),
            ]

        else:

            positions = [
                (8, 30),
                (22, 8),
                (18, 22),
                (18, 38),
                (22, 52),
                (35, 22),
                (35, 38),
                (52, 10),
                (52, 30),
                (52, 50),
                (72, 30),
            ]

        result = []

        for x, y in positions:

            if side == "away":
                x = PITCH_WIDTH - x

            result.append({
                "x": float(x),
                "y": float(y),
            })

        return result

    # ========================================================
    # PLACE PLAYERS
    # ========================================================

    def _place_players(self) -> None:

        for team in [
            self.home,
            self.away,
        ]:

            positions = self._formation_positions(
                team["formation"],
                team["side"],
            )

            roles = FORMATIONS.get(
                team["formation"],
                FORMATIONS["4-3-3"],
            )

            for index, player in enumerate(
                team["players"]
            ):

                pos = positions[
                    min(
                        index,
                        len(positions) - 1,
                    )
                ]

                role = roles[
                    min(
                        index,
                        len(roles) - 1,
                    )
                ]

                player["role"] = role
                player["position"] = role

                player["x"] = pos["x"]
                player["y"] = pos["y"]

                player["targetX"] = pos["x"]
                player["targetY"] = pos["y"]

        # Kickoff
        midfielder = self._find_best_player(
            self.home,
            ["CM", "CAM", "CDM"],
        )

        if midfielder:
            midfielder["x"] = 50
            midfielder["y"] = 30
            self._give_ball(
                midfielder,
                "home",
            )

    # ========================================================
    # PLAYER SEARCH
    # ========================================================

    def _all_players(
        self,
        side: str,
    ) -> List[Dict[str, Any]]:

        team = (
            self.home
            if side == "home"
            else self.away
        )

        return [
            p
            for p in team["players"]
            if p.get("active")
            and not p.get("redCard")
        ]

    # --------------------------------------------------------

    def _find_player(
        self,
        side: str,
        player_id: str,
    ) -> Optional[Dict[str, Any]]:

        for player in self._all_players(side):

            if str(player["id"]) == str(player_id):
                return player

        return None

    # --------------------------------------------------------

    def _find_best_player(
        self,
        team: Dict[str, Any],
        positions: List[str],
    ) -> Optional[Dict[str, Any]]:

        candidates = [
            p
            for p in team["players"]
            if p.get("active")
            and not p.get("redCard")
            and (
                p.get("position") in positions
                or p.get("role") in positions
            )
        ]

        if not candidates:

            candidates = [
                p
                for p in team["players"]
                if p.get("active")
            ]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda p:
                p["passing"]
                + p["vision"]
                + p["stamina"],
        )

    # ========================================================
    # BALL
    # ========================================================

    def _give_ball(
        self,
        player: Dict[str, Any],
        side: str,
    ) -> None:

        for team_side in [
            "home",
            "away",
        ]:

            for p in self._all_players(team_side):
                p["hasBall"] = False

        player["hasBall"] = True

        self.ball["owner"] = player["id"]
        self.ball["team"] = side

        self.ball["x"] = player["x"]
        self.ball["y"] = player["y"]

        self.ball["vx"] = 0
        self.ball["vy"] = 0

        self.ball["state"] = "controlled"

        self.possession_team = side

    # --------------------------------------------------------

    def _clear_ball(self) -> None:

        for side in [
            "home",
            "away",
        ]:

            for player in self._all_players(side):
                player["hasBall"] = False

        self.ball["owner"] = None
        self.ball["team"] = None
        self.ball["state"] = "free"

    # ========================================================
    # START
    # ========================================================

    def start(self) -> Dict[str, Any]:

        with self.lock:

            if self.finished:
                return self.snapshot()

            if self.status == "playing":
                return self.snapshot()

            self.status = "playing"
            self.running = True

            self.last_tick = time.monotonic()

            if (
                self._loop_thread is None
                or not self._loop_thread.is_alive()
            ):

                self._loop_thread = threading.Thread(
                    target=self._run_loop,
                    daemon=True,
                )

                self._loop_thread.start()

            self._event(
                "match_started",
                "Match started",
                None,
                None,
            )

            return self.snapshot()

    # ========================================================
    # PAUSE
    # ========================================================

    def pause(self) -> Dict[str, Any]:

        with self.lock:

            if not self.finished:

                self.running = False

                if self.status == "playing":
                    self.status = "paused"

                self.last_tick = time.monotonic()

                self._event(
                    "paused",
                    "Match paused",
                    None,
                    None,
                )

            return self.snapshot()

    # ========================================================
    # RESUME
    # ========================================================

    def resume(self) -> Dict[str, Any]:

        with self.lock:

            if self.finished:
                return self.snapshot()

            self.running = True
            self.status = "playing"

            self.last_tick = time.monotonic()

            if (
                self._loop_thread is None
                or not self._loop_thread.is_alive()
            ):

                self._loop_thread = threading.Thread(
                    target=self._run_loop,
                    daemon=True,
                )

                self._loop_thread.start()

            self._event(
                "resumed",
                "Match resumed",
                None,
                None,
            )

            return self.snapshot()

    # ========================================================
    # MAIN LOOP
    # ========================================================

    def _run_loop(self) -> None:

        while True:

            with self.lock:

                if self.finished:
                    break

                now = time.monotonic()

                real_delta = (
                    now - self.last_tick
                )

                self.last_tick = now

                real_delta = clamp(
                    real_delta,
                    0.01,
                    0.50,
                )

                # --------------------------------------------
                # HALFTIME
                # --------------------------------------------

                if self.status == "halftime":

                    self._process_halftime()

                # --------------------------------------------
                # PLAYING
                # --------------------------------------------

                elif (
                    self.running
                    and self.status == "playing"
                ):

                    self._advance(
                        real_delta
                    )

                else:

                    self.last_tick = now

            time.sleep(TICK_SECONDS)

    # ========================================================
    # HALFTIME PROCESS
    # ========================================================

    def _process_halftime(self) -> None:

        if self.halftime_started_at is None:
            return

        elapsed = (
            time.monotonic()
            - self.halftime_started_at
        )

        if elapsed < HALFTIME_BREAK_SECONDS:
            return

        if self.finished:
            return

        # ----------------------------------------------------
        # Start second half at EXACTLY 45:00
        # ----------------------------------------------------

        self.match_clock_seconds = 45 * 60

        self.minute = 45
        self.second = 0

        self.status = "playing"

        self.running = True

        self.second_half_started = True

        self.last_tick = time.monotonic()

        self._reset_positions_for_second_half()

        self._event(
            "second_half",
            "Second half started",
            None,
            None,
        )

        self.halftime_started_at = None

    # ========================================================
    # ADVANCE CLOCK
    # ========================================================

    def _advance(
        self,
        real_seconds: float,
    ) -> None:

        if self.status != "playing":
            return

        # ----------------------------------------------------
        # ADVANCE FOOTBALL CLOCK
        # ----------------------------------------------------

        self.match_clock_seconds += (
            real_seconds
            * GAME_SECONDS_PER_REAL_SECOND
        )

        # ----------------------------------------------------
        # FIRST HALF
        # ----------------------------------------------------

        if not self.halftime_done:

            first_half_end = (
                45 * 60
                + self.injury_time_first_half * 60
            )

            if (
                self.match_clock_seconds
                >= first_half_end
            ):

                self.match_clock_seconds = first_half_end

                self._set_clock()

                self._halftime()

                return

        # ----------------------------------------------------
        # SECOND HALF
        # ----------------------------------------------------

        second_half_end = (
            90 * 60
            + self.injury_time_second_half * 60
        )

        if (
            self.halftime_done
            and self.match_clock_seconds
            >= second_half_end
        ):

            self.match_clock_seconds = second_half_end

            self._set_clock()

            self._finish_match()

            return

        # ----------------------------------------------------
        # CLOCK DISPLAY
        # ----------------------------------------------------

        self._set_clock()

        # ----------------------------------------------------
        # GAME SYSTEMS
        # ----------------------------------------------------

        self._update_possession_time(
            real_seconds
        )

        self._update_stamina(
            real_seconds
        )

        self._update_players(
            real_seconds
        )

        self._update_ball(
            real_seconds
        )

        self._maybe_random_event()

        self._update_possession_stats()

        self._update_momentum()

    # ========================================================
    # CLOCK DISPLAY
    # ========================================================

    def _set_clock(self) -> None:

        total_seconds = int(
            max(
                0,
                self.match_clock_seconds,
            )
        )

        self.minute = total_seconds // 60

        self.second = total_seconds % 60

    # ========================================================
    # POSSESSION
    # ========================================================

    def _update_possession_time(
        self,
        real_seconds: float,
    ) -> None:

        owner = self._find_ball_owner()

        if owner:
            side = owner["side"]
        else:
            side = self.possession_team

        self.possession_time[side] += (
            real_seconds
        )

    # ========================================================
    # STAMINA
    # ========================================================

    def _update_stamina(
        self,
        real_seconds: float,
    ) -> None:

        for side in [
            "home",
            "away",
        ]:

            team = self._team(side)

            pressing = team["tactics"]["pressing"]

            multiplier = {
                "low": 0.65,
                "medium": 0.90,
                "high": 1.20,
            }.get(
                pressing,
                0.90,
            )

            for player in self._all_players(side):

                drain = (
                    0.018
                    * real_seconds
                    * multiplier
                )

                player["energy"] = clamp(
                    player["energy"] - drain,
                    20,
                    100,
                )

    # ========================================================
    # PLAYER MOVEMENT
    # ========================================================

    def _update_players(
        self,
        real_seconds: float,
    ) -> None:

        owner = self._find_ball_owner()

        for side in [
            "home",
            "away",
        ]:

            team = self._team(side)

            opponent_side = (
                "away"
                if side == "home"
                else "home"
            )

            for player in self._all_players(side):

                target = self._calculate_target(
                    player,
                    team,
                    owner,
                    opponent_side,
                )

                # Smooth target changes
                player["targetX"] = (
                    player["targetX"] * 0.70
                    + target["x"] * 0.30
                )

                player["targetY"] = (
                    player["targetY"] * 0.70
                    + target["y"] * 0.30
                )

                self._move_player(
                    player,
                    real_seconds,
                )

    # ========================================================
    # PLAYER TARGET LOGIC
    # ========================================================

    def _calculate_target(
        self,
        player: Dict[str, Any],
        team: Dict[str, Any],
        owner: Optional[Dict[str, Any]],
        opponent_side: str,
    ) -> Dict[str, float]:

        side = team["side"]

        attacking = (
            self.possession_team == side
        )

        role = player["role"]

        direction = (
            1
            if side == "home"
            else -1
        )

        base_x = player["x"]
        base_y = player["y"]

        # ====================================================
        # ATTACKING TEAM
        # ====================================================

        if attacking:

            progression = {
                "GK": 0,
                "CB": 4,
                "RB": 8,
                "LB": 8,
                "RWB": 11,
                "LWB": 11,
                "CDM": 12,
                "CM": 18,
                "CAM": 24,
                "RM": 20,
                "LM": 20,
                "RW": 27,
                "LW": 27,
                "ST": 32,
            }.get(
                role,
                12,
            )

            # Mentality
            mentality = team["tactics"]["mentality"]

            if mentality == "attacking":
                progression += 7

            elif mentality == "defensive":
                progression -= 6

            target_x = (
                50
                + direction * progression
            )

            # Ball owner gets freedom
            if (
                owner
                and owner["side"] == side
                and player["id"] == owner["id"]
            ):

                target_x = (
                    player["x"]
                    + direction * 8
                )

            # Striker run behind defence
            if role == "ST":

                target_x += (
                    direction
                    * random.uniform(
                        0.0,
                        1.5,
                    )
                )

                target_y = clamp(
                    30
                    + (
                        player["y"] - 30
                    ) * 0.25,
                    20,
                    40,
                )

            elif role in [
                "RW",
                "RM",
            ]:

                target_y = 9

            elif role in [
                "LW",
                "LM",
            ]:

                target_y = 51

            elif role == "CAM":

                target_y = 30

            else:

                target_y = base_y

            # Ball side attraction
            if owner and owner["side"] == side:

                target_y += (
                    clamp(
                        owner["y"] - 30,
                        -12,
                        12,
                    )
                    * 0.12
                )

            return {
                "x": clamp(
                    target_x,
                    5,
                    94,
                ),

                "y": clamp(
                    target_y,
                    4,
                    56,
                ),
            }

        # ====================================================
        # DEFENDING TEAM
        # ====================================================

        defensive_x = (
            30
            if side == "home"
            else 70
        )

        if role == "GK":

            defensive_x = (
                5
                if side == "home"
                else 95
            )

        elif role in [
            "CB",
            "RB",
            "LB",
            "RWB",
            "LWB",
        ]:

            defensive_x = (
                25
                if side == "home"
                else 75
            )

        elif role in [
            "CDM",
            "CM",
        ]:

            defensive_x = (
                34
                if side == "home"
                else 66
            )

        # Defensive line tactics
        defensive_line = team["tactics"]["defensiveLine"]

        if defensive_line == "high":

            defensive_x += (
                direction * 7
            )

        elif defensive_line == "low":

            defensive_x -= (
                direction * 5
            )

        target_y = base_y

        if owner:

            target_y = (
                target_y * 0.65
                + owner["y"] * 0.35
            )

        # Pressing
        pressing = team["tactics"]["pressing"]

        if (
            owner
            and owner["side"] != side
        ):

            d = distance(
                player,
                owner,
            )

            if pressing == "high" and d < 18:

                defensive_x = (
                    owner["x"]
                    - direction * 3
                )

            elif pressing == "medium" and d < 10:

                defensive_x = (
                    owner["x"]
                    - direction * 2
                )

        return {
            "x": clamp(
                defensive_x,
                4,
                96,
            ),

            "y": clamp(
                target_y,
                4,
                56,
            ),
        }

    # ========================================================
    # MOVE PLAYER
    # ========================================================

    def _move_player(
        self,
        player: Dict[str, Any],
        real_seconds: float,
    ) -> None:

        dx = (
            player["targetX"]
            - player["x"]
        )

        dy = (
            player["targetY"]
            - player["y"]
        )

        dist = math.hypot(
            dx,
            dy,
        )

        if dist < 0.05:
            return

        pace = player["pace"]

        energy = player["energy"]

        speed = (
            3.2
            + pace * 0.035
        )

        energy_factor = (
            0.65
            + energy / 100 * 0.35
        )

        speed *= energy_factor

        step = (
            speed
            * real_seconds
        )

        ratio = min(
            1.0,
            step / dist,
        )

        player["x"] += (
            dx * ratio
        )

        player["y"] += (
            dy * ratio
        )

        player["x"] = clamp(
            player["x"],
            2,
            98,
        )

        player["y"] = clamp(
            player["y"],
            2,
            58,
        )

    # ========================================================
    # BALL UPDATE
    # ========================================================

    def _update_ball(
        self,
        real_seconds: float,
    ) -> None:

        owner = self._find_ball_owner()

        if owner is None:

            if self.ball["state"] == "free":

                self.ball["x"] += (
                    self.ball["vx"]
                    * real_seconds
                )

                self.ball["y"] += (
                    self.ball["vy"]
                    * real_seconds
                )

                self.ball["vx"] *= 0.90
                self.ball["vy"] *= 0.90

                self.ball["x"] = clamp(
                    self.ball["x"],
                    1,
                    99,
                )

                self.ball["y"] = clamp(
                    self.ball["y"],
                    1,
                    59,
                )

                self._choose_ball_winner()

            return

        # Ball follows player
        self.ball["x"] = owner["x"]
        self.ball["y"] = owner["y"]

        owner["cooldown"] = max(
            0,
            owner["cooldown"]
            - real_seconds,
        )

        self.cooldowns["action"][
            owner["side"]
        ] = max(
            0,
            self.cooldowns["action"][
                owner["side"]
            ] - real_seconds,
        )

        if owner["cooldown"] <= 0:

            self._decide_action(
                owner
            )

    # ========================================================
    # FIND BALL OWNER
    # ========================================================

    def _find_ball_owner(
        self,
    ) -> Optional[Dict[str, Any]]:

        owner_id = self.ball.get(
            "owner"
        )

        if not owner_id:
            return None

        for side in [
            "home",
            "away",
        ]:

            player = self._find_player(
                side,
                owner_id,
            )

            if (
                player
                and player.get("hasBall")
            ):
                return player

        return None

    # ========================================================
    # PRESSURE
    # ========================================================

    def _pressure(
        self,
        player: Dict[str, Any],
        opponent_side: str,
    ) -> float:

        opponents = self._all_players(
            opponent_side
        )

        if not opponents:
            return 99

        return min(
            distance(
                player,
                opponent,
            )
            for opponent in opponents
        )

    # ========================================================
    # ACTION DECISION
    # ========================================================

    def _decide_action(
        self,
        player: Dict[str, Any],
    ) -> None:

        side = player["side"]

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        direction = (
            1
            if side == "home"
            else -1
        )

        goal_x = (
            HOME_GOAL_X
            if side == "home"
            else AWAY_GOAL_X
        )

        distance_to_goal = abs(
            goal_x
            - player["x"]
        )

        pressure = self._pressure(
            player,
            opponent_side,
        )

        role = player["role"]

        # ----------------------------------------------------
        # SHOT
        # ----------------------------------------------------

        if self._good_shooting_position(
            player,
            distance_to_goal,
            pressure,
        ):

            # Do not shoot constantly.
            shot_chance = (
                0.11
                + player["shooting"] / 1000
            )

            if (
                role in [
                    "ST",
                    "CAM",
                ]
            ):
                shot_chance += 0.05

            if random.random() < shot_chance:

                self._shoot(
                    player
                )

                return

        # ----------------------------------------------------
        # CROSS
        # ----------------------------------------------------

        if (
            role in [
                "RW",
                "LW",
                "RM",
                "LM",
                "RWB",
                "LWB",
            ]
            and distance_to_goal < 38
            and (
                player["y"] < 14
                or player["y"] > 46
            )
        ):

            if random.random() < 0.20:

                self._cross(
                    player
                )

                return

        # ----------------------------------------------------
        # DRIBBLE
        # ----------------------------------------------------

        if (
            pressure > 5
            and player["dribbling"] >= 58
            and random.random() < 0.22
        ):

            self._dribble(
                player
            )

            return

        # ----------------------------------------------------
        # THROUGH BALL
        # ----------------------------------------------------

        if (
            player["vision"] >= 65
            and random.random() < 0.14
        ):

            if self._through_ball(
                player
            ):

                return

        # ----------------------------------------------------
        # NORMAL PASS
        # ----------------------------------------------------

        self._pass(
            player
        )

    # ========================================================
    # SHOOTING POSITION
    # ========================================================

    def _good_shooting_position(
        self,
        player: Dict[str, Any],
        distance_to_goal: float,
        pressure: float,
    ) -> bool:

        role = player["role"]

        if role in [
            "ST",
            "CAM",
        ]:

            return (
                distance_to_goal <= 27
                and (
                    12
                    <= player["y"]
                    <= 48
                )
            )

        if role in [
            "RW",
            "LW",
        ]:

            return (
                distance_to_goal <= 24
                and pressure > 2.5
            )

        if role in [
            "CM",
            "RM",
            "LM",
        ]:

            return (
                distance_to_goal <= 21
                and pressure > 5
            )

        return False

    # ========================================================
    # PASS
    # ========================================================

    def _pass(
        self,
        player: Dict[str, Any],
    ) -> None:

        side = player["side"]

        direction = (
            1
            if side == "home"
            else -1
        )

        teammates = [
            p
            for p in self._all_players(side)
            if p["id"] != player["id"]
        ]

        if not teammates:
            return

        candidates = []

        for teammate in teammates:

            d = distance(
                player,
                teammate,
            )

            if d > 38:
                continue

            progress = (
                teammate["x"]
                - player["x"]
            ) * direction

            score = (
                progress * 1.3
                + teammate["vision"] * 0.10
                - d * 0.30
            )

            if teammate["role"] in [
                "ST",
                "CAM",
                "RW",
                "LW",
            ]:
                score += 9

            if teammate["role"] == "GK":
                score -= 40

            candidates.append(
                (
                    score,
                    teammate,
                )
            )

        if not candidates:

            teammate = min(
                teammates,
                key=lambda p:
                    distance(
                        player,
                        p,
                    ),
            )

        else:

            candidates.sort(
                key=lambda x: x[0],
                reverse=True,
            )

            # Sometimes choose second-best to avoid robotic football
            if (
                len(candidates) > 1
                and random.random() < 0.20
            ):
                teammate = candidates[1][1]
            else:
                teammate = candidates[0][1]

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        pressure = self._pressure(
            player,
            opponent_side,
        )

        success = (
            0.78
            + (
                player["passing"]
                - 70
            ) / 220
        )

        if pressure < 5:
            success -= 0.10

        if pressure < 3:
            success -= 0.12

        success = clamp(
            success,
            0.40,
            0.94,
        )

        player["stats"]["passes"] += 1

        self._team_stats(side)[
            "passes"
        ] += 1

        if random.random() > success:

            self._event(
                "bad_pass",
                f"{player['name']} lost the ball",
                side,
                player["id"],
            )

            self._lose_ball_to_opponent(
                player
            )

            player["cooldown"] = 0.8

            return

        player["stats"][
            "passesCompleted"
        ] += 1

        self._team_stats(side)[
            "passesCompleted"
        ] += 1

        self._give_ball(
            teammate,
            side,
        )

        teammate["action"] = "receive"

        # Encourage forward movement
        if teammate["role"] in [
            "ST",
            "CAM",
            "RW",
            "LW",
        ]:

            teammate["targetX"] = clamp(
                teammate["x"]
                + direction * 5,
                5,
                95,
            )

        self._event(
            "pass",
            f"{player['name']} passed to {teammate['name']}",
            side,
            player["id"],
            {
                "receiverId": teammate["id"],
                "receiver": teammate["name"],
            },
        )

        player["cooldown"] = (
            0.65
            + random.random() * 0.65
        )

    # ========================================================
    # THROUGH BALL
    # ========================================================

    def _through_ball(
        self,
        player: Dict[str, Any],
    ) -> bool:

        side = player["side"]

        direction = (
            1
            if side == "home"
            else -1
        )

        attackers = [
            p
            for p in self._all_players(side)
            if p["id"] != player["id"]
            and p["role"] in [
                "ST",
                "RW",
                "LW",
                "CAM",
            ]
            and (
                p["x"] - player["x"]
            ) * direction > 4
        ]

        if not attackers:
            return False

        target = max(
            attackers,
            key=lambda p:
                (
                    (
                        p["x"]
                        - player["x"]
                    )
                    * direction
                )
                + p["pace"] * 0.10,
        )

        chance = clamp(
            0.50
            + (
                player["vision"]
                - 65
            ) / 180,
            0.25,
            0.84,
        )

        player["stats"]["passes"] += 1

        self._team_stats(side)[
            "passes"
        ] += 1

        if random.random() > chance:

            self._event(
                "through_ball_failed",
                f"{player['name']} tried a through ball",
                side,
                player["id"],
            )

            self._lose_ball_to_opponent(
                player
            )

            player["cooldown"] = 1.0

            return True

        player["stats"][
            "passesCompleted"
        ] += 1

        self._team_stats(side)[
            "passesCompleted"
        ] += 1

        self._give_ball(
            target,
            side,
        )

        target["action"] = "run"

        target["targetX"] = clamp(
            target["x"]
            + direction * 10,
            5,
            95,
        )

        self._event(
            "through_ball",
            f"{player['name']} sent a through ball to {target['name']}",
            side,
            player["id"],
            {
                "receiverId": target["id"],
                "receiver": target["name"],
            },
        )

        player["cooldown"] = 1.0

        return True

    # ========================================================
    # DRIBBLE
    # ========================================================

    def _dribble(
        self,
        player: Dict[str, Any],
    ) -> None:

        side = player["side"]

        direction = (
            1
            if side == "home"
            else -1
        )

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        opponents = self._all_players(
            opponent_side
        )

        closest = None

        if opponents:

            closest = min(
                opponents,
                key=lambda p:
                    distance(
                        player,
                        p,
                    ),
            )

        success = (
            0.48
            + (
                player["dribbling"]
                - 65
            ) / 160
        )

        if closest:

            d = distance(
                player,
                closest,
            )

            if d < 6:
                success -= (
                    6 - d
                ) * 0.035

        success = clamp(
            success,
            0.20,
            0.82,
        )

        player["stats"][
            "dribbles"
        ] += 1

        if random.random() < success:

            player["x"] = clamp(
                player["x"]
                + direction * random.uniform(
                    2,
                    5,
                ),
                3,
                97,
            )

            player["y"] = clamp(
                player["y"]
                + random.uniform(
                    -2,
                    2,
                ),
                3,
                57,
            )

            player["action"] = "dribble"

            self._event(
                "dribble",
                f"{player['name']} beat a defender",
                side,
                player["id"],
            )

        else:

            if closest:

                closest["stats"][
                    "tackles"
                ] += 1

                self._team_stats(
                    opponent_side
                )["tackles"] += 1

                self._give_ball(
                    closest,
                    opponent_side,
                )

                self._event(
                    "tackle",
                    f"{closest['name']} won the ball",
                    opponent_side,
                    closest["id"],
                )

            else:

                self._lose_ball_to_opponent(
                    player
                )

        player["cooldown"] = 0.85

    # ========================================================
    # SHOOT
    # ========================================================

    def _shoot(
        self,
        player: Dict[str, Any],
    ) -> None:

        side = player["side"]

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        team = self._team(side)

        opponent = self._team(
            opponent_side
        )

        goal_x = (
            HOME_GOAL_X
            if side == "home"
            else AWAY_GOAL_X
        )

        distance_to_goal = abs(
            goal_x
            - player["x"]
        )

        # ----------------------------------------------------
        # ANGLE
        # ----------------------------------------------------

        angle_factor = clamp(
            1.0
            - abs(
                player["y"] - 30
            ) / 38,
            0.55,
            1.0,
        )

        # ----------------------------------------------------
        # DISTANCE
        # ----------------------------------------------------

        distance_factor = clamp(
            1.0
            - distance_to_goal / 40,
            0.35,
            1.0,
        )

        # ----------------------------------------------------
        # PRESSURE
        # ----------------------------------------------------

        pressure = self._pressure(
            player,
            opponent_side,
        )

        pressure_factor = clamp(
            0.70
            + pressure / 35,
            0.55,
            1.0,
        )

        # ----------------------------------------------------
        # PLAYER QUALITY
        # ----------------------------------------------------

        shooting_quality = (
            player["shooting"] * 0.50
            + player["composure"] * 0.25
            + player["strength"] * 0.10
        )

        # ----------------------------------------------------
        # GOALKEEPER
        # ----------------------------------------------------

        goalkeeper = next(
            (
                p
                for p in opponent["players"]
                if p["active"]
                and p["role"] == "GK"
            ),
            None,
        )

        if goalkeeper is None:
            return

        goalkeeper_quality = (
            goalkeeper["goalkeeping"]
        )

        # ----------------------------------------------------
        # SHOT QUALITY
        # ----------------------------------------------------

        shot_quality = (
            shooting_quality
            * angle_factor
            * distance_factor
            * pressure_factor
        )

        # ----------------------------------------------------
        # ON TARGET
        # ----------------------------------------------------

        on_target_probability = clamp(
            0.42
            + player["shooting"] / 300
            + player["composure"] / 500,
            0.40,
            0.78,
        )

        on_target = (
            random.random()
            < on_target_probability
        )

        # ----------------------------------------------------
        # GOAL PROBABILITY
        #
        # Designed to produce football-like scores:
        # 0-0, 1-0, 1-
