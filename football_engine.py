from __future__ import annotations

import math
import random
import threading
import time
import uuid
from typing import Any, Dict, List, Optional


# ============================================================
# CONFIG
# ============================================================

PITCH_WIDTH = 100.0
PITCH_HEIGHT = 60.0

MATCH_MINUTES = 90
REAL_MATCH_SECONDS = 480.0   # 8 minutes = 90 football minutes
TICK_SECONDS = 0.25

MAX_EVENTS = 300
MAX_PLAYERS = 30

FORMATIONS = {
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
}


# ============================================================
# HELPERS
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


def distance(a: Dict[str, float], b: Dict[str, float]) -> float:
    return math.sqrt(
        (a["x"] - b["x"]) ** 2 +
        (a["y"] - b["y"]) ** 2
    )


def normalize_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback

    text = str(value).strip()

    return text if text else fallback


# ============================================================
# ENGINE
# ============================================================

class FootballMatch:

    def __init__(self, config: Dict[str, Any]):
        self.lock = threading.RLock()

        self.match_id = normalize_text(
            config.get("matchId") or config.get("id"),
            str(uuid.uuid4()),
        )

        self.created_at = time.time()

        self.status = "created"

        self.running = False
        self.finished = False

        self.minute = 0
        self.second = 0

        self.elapsed_real = 0.0

        self.score = {
            "home": 0,
            "away": 0,
        }

        self.ball = {
            "x": 50.0,
            "y": 30.0,
            "owner": None,
            "team": None,
            "state": "dead",
        }

        self.events: List[Dict[str, Any]] = []

        self.thread: Optional[threading.Thread] = None

        self.last_tick = time.time()

        self.halftime_done = False

        self.possession_team = "home"

        self.attack_team = "home"

        self.last_event_time = 0.0

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
        }

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

        self.stats = self._create_match_stats()

        self._place_players()

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

        players = []

        if isinstance(players_source, list):
            for index, player in enumerate(players_source[:11]):
                if isinstance(player, dict):
                    players.append(
                        self._create_player(
                            player,
                            index,
                            side,
                        )
                    )

        bench = []

        if isinstance(bench_source, list):
            for index, player in enumerate(bench_source[:12]):
                if isinstance(player, dict):
                    bench.append(
                        self._create_player(
                            player,
                            index + 11,
                            side,
                            is_bench=True,
                        )
                    )

        # IMPORTANT:
        # We do not want generic players if Firebase actually
        # supplied players. But if fewer than 11 were supplied,
        # the match still needs a complete XI.
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
                source.get("id") or source.get("clubId"),
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

        player = {
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

            "goalkeeping": self._rating(
                source,
                ratings,
                "goalkeeping",
                65,
            ),

            "morale": 70.0,

            "energy": 100.0,

            "x": 50.0,
            "y": 30.0,

            "targetX": 50.0,
            "targetY": 30.0,

            "hasBall": False,

            "action": "idle",

            "lastActionAt": 0.0,

            "cooldown": 0.0,

            "stats": self._empty_player_stats(),
        }

        return player

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

        return {
            "mentality": normalize_text(
                source.get("mentality"),
                "balanced",
            ),

            "tempo": clamp(
                safe_float(
                    source.get("tempo"),
                    60,
                ),
                1,
                100,
            ),

            "pressing": normalize_text(
                source.get("pressing"),
                "medium",
            ),

            "defensiveLine": normalize_text(
                source.get("defensiveLine"),
                "medium",
            ),

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
    # STATS
    # ========================================================

    def _empty_player_stats(self):
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
        }

    def _empty_team_stats(self):
        return {
            "possession": 50,
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
        }

    def _create_match_stats(self):
        return {
            "home": self._empty_team_stats(),
            "away": self._empty_team_stats(),
        }

    # ========================================================
    # PLAYER POSITIONS
    # ========================================================

    def _formation_positions(
        self,
        formation: str,
        side: str,
    ) -> List[Dict[str, float]]:

        attacking = side == "home"

        if formation == "4-4-2":
            positions = [
                (8, 30),
                (22, 8),
                (18, 22),
                (18, 38),
                (22, 52),
                (42, 8),
                (38, 23),
                (38, 37),
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
                (40, 18),
                (38, 30),
                (40, 42),
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
            if not attacking:
                x = PITCH_WIDTH - x

            result.append({
                "x": float(x),
                "y": float(y),
            })

        return result

    def _place_players(self):

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

                position = positions[
                    min(index, len(positions) - 1)
                ]

                role = roles[
                    min(index, len(roles) - 1)
                ]

                player["role"] = role

                player["position"] = role

                player["x"] = position["x"]
                player["y"] = position["y"]

                player["targetX"] = position["x"]
                player["targetY"] = position["y"]

        # Ball starts with central midfielder
        home_mid = self._find_best_player(
            self.home,
            ["CM", "CAM", "CDM"],
        )

        if home_mid:
            self._give_ball(
                home_mid,
                "home",
            )

    # ========================================================
    # PLAYER SEARCH
    # ========================================================

    def _all_players(self, side: str):
        team = self.home if side == "home" else self.away

        return [
            p
            for p in team["players"]
            if p.get("active")
        ]

    def _find_player(
        self,
        side: str,
        player_id: str,
    ):

        for player in self._all_players(side):

            if str(player["id"]) == str(player_id):
                return player

        return None

    def _find_best_player(
        self,
        team: Dict[str, Any],
        positions: List[str],
    ):

        candidates = [
            p
            for p in team["players"]
            if p.get("active")
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
            key=lambda p: (
                p["passing"]
                + p["vision"]
                + p["stamina"]
            ),
        )

    # ========================================================
    # BALL
    # ========================================================

    def _give_ball(
        self,
        player: Dict[str, Any],
        side: str,
    ):

        for team_side in ["home", "away"]:

            for p in self._all_players(team_side):
                p["hasBall"] = False

        player["hasBall"] = True

        self.ball["owner"] = player["id"]
        self.ball["team"] = side
        self.ball["x"] = player["x"]
        self.ball["y"] = player["y"]
        self.ball["state"] = "controlled"

        self.possession_team = side

    def _clear_ball(self):

        for side in ["home", "away"]:
            for player in self._all_players(side):
                player["hasBall"] = False

        self.ball["owner"] = None
        self.ball["state"] = "free"

    # ========================================================
    # MATCH START
    # ========================================================

    def start(self):

        with self.lock:

            if self.finished:
                return self.snapshot()

            if self.status == "playing":
                return self.snapshot()

            self.status = "playing"
            self.running = True

            self.last_tick = time.time()

            if (
                self.thread is None
                or not self.thread.is_alive()
            ):

                self.thread = threading.Thread(
                    target=self._run_loop,
                    daemon=True,
                )

                self.thread.start()

            self._event(
                "match_started",
                "Match started",
                None,
                None,
            )

            return self.snapshot()

    # ========================================================
    # LOOP
    # ========================================================

    def _run_loop(self):

        while True:

            with self.lock:

                if self.finished:
                    break

                if not self.running:
                    pass
                else:
                    now = time.time()

                    elapsed = now - self.last_tick

                    self.last_tick = now

                    elapsed = clamp(
                        elapsed,
                        0.01,
                        1.0,
                    )

                    self._advance(
                        elapsed
                    )

            time.sleep(TICK_SECONDS)

    # ========================================================
    # ADVANCE
    # ========================================================

    def _advance(
        self,
        real_seconds: float,
    ):

        if self.status != "playing":
            return

        self.elapsed_real += real_seconds

        football_minutes = (
            self.elapsed_real
            / REAL_MATCH_SECONDS
        ) * MATCH_MINUTES

        football_minutes = clamp(
            football_minutes,
            0,
            90,
        )

        self.minute = int(
            football_minutes
        )

        self.second = int(
            (football_minutes - self.minute)
            * 60
        )

        if (
            self.minute >= 45
            and not self.halftime_done
        ):
            self._halftime()
            return

        if self.minute >= 90:

            self.minute = 90
            self.second = 0

            self._finish_match()

            return

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

    # ========================================================
    # STAMINA
    # ========================================================

    def _update_stamina(
        self,
        real_seconds: float,
    ):

        drain = (
            real_seconds
            * 0.012
        )

        for side in ["home", "away"]:

            team = (
                self.home
                if side == "home"
                else self.away
            )

            pressing = team["tactics"].get(
                "pressing",
                "medium",
            )

            multiplier = {
                "low": 0.7,
                "medium": 1.0,
                "high": 1.35,
            }.get(
                pressing,
                1.0,
            )

            for player in self._all_players(side):

                player["energy"] = clamp(
                    player["energy"]
                    - (
                        drain
                        * multiplier
                    ),
                    20,
                    100,
                )

    # ========================================================
    # PLAYER MOVEMENT
    # ========================================================

    def _update_players(
        self,
        real_seconds: float,
    ):

        owner = self._find_ball_owner()

        for side in ["home", "away"]:

            team = (
                self.home
                if side == "home"
                else self.away
            )

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

                player["targetX"] = target["x"]
                player["targetY"] = target["y"]

                self._move_player(
                    player,
                    real_seconds,
                )

    def _calculate_target(
        self,
        player: Dict[str, Any],
        team: Dict[str, Any],
        owner: Optional[Dict[str, Any]],
        opponent_side: str,
    ):

        side = team["side"]

        attacking = (
            self.possession_team == side
        )

        role = player["role"]

        base_x = player["x"]
        base_y = player["y"]

        # ----------------------------------------------------
        # ATTACKING MOVEMENT
        # ----------------------------------------------------

        if attacking:

            direction = (
                1
                if side == "home"
                else -1
            )

            progression = {
                "GK": 0,
                "CB": 5,
                "RB": 9,
                "LB": 9,
                "RWB": 12,
                "LWB": 12,
                "CDM": 14,
                "CM": 18,
                "CAM": 23,
                "RM": 20,
                "LM": 20,
                "RW": 25,
                "LW": 25,
                "ST": 30,
            }.get(
                role,
                12,
            )

            target_x = (
                50
                + (
                    direction
                    * progression
                )
            )

            if owner and owner["side"] == side:

                distance_to_owner = math.sqrt(
                    (
                        player["x"]
                        - owner["x"]
                    ) ** 2
                    +
                    (
                        player["y"]
                        - owner["y"]
                    ) ** 2
                )

                if (
                    role in [
                        "ST",
                        "RW",
                        "LW",
                        "CAM",
                    ]
                    and distance_to_owner < 25
                ):
                    target_x += (
                        direction
                        * 8
                    )

            # Wingers stay wide
            if role in [
                "RW",
                "RM",
            ]:
                target_y = 8

            elif role in [
                "LW",
                "LM",
            ]:
                target_y = 52

            elif role == "ST":
                target_y = (
                    25
                    + random.uniform(
                        -7,
                        7,
                    )
                )

            else:
                target_y = (
                    base_y
                    + random.uniform(
                        -1.5,
                        1.5,
                    )
                )

            target_x = clamp(
                target_x,
                8,
                92,
            )

            return {
                "x": target_x,
                "y": clamp(
                    target_y,
                    4,
                    56,
                ),
            }

        # ----------------------------------------------------
        # DEFENSIVE MOVEMENT
        # ----------------------------------------------------

        direction = (
            1
            if side == "home"
            else -1
        )

        defensive_x = (
            35
            if side == "home"
            else 65
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
                33
                if side == "home"
                else 67
            )

        if owner:
            if side == "home":
                defensive_y = owner["y"]
            else:
                defensive_y = owner["y"]
        else:
            defensive_y = base_y

        # Press close to ball
        pressing = team["tactics"].get(
            "pressing",
            "medium",
        )

        if pressing == "high":
            defensive_x += (
                direction
                * 5
            )

        return {
            "x": clamp(
                defensive_x,
                4,
                96,
            ),
            "y": clamp(
                defensive_y
                + random.uniform(
                    -5,
                    5,
                ),
                4,
                56,
            ),
        }

    def _move_player(
        self,
        player: Dict[str, Any],
        real_seconds: float,
    ):

        dx = (
            player["targetX"]
            - player["x"]
        )

        dy = (
            player["targetY"]
            - player["y"]
        )

        dist = math.sqrt(
            dx * dx
            + dy * dy
        )

        if dist < 0.1:
            return

        pace_factor = (
            0.018
            * (
                0.75
                + player["pace"]
                / 100
            )
        )

        speed = (
            pace_factor
            * real_seconds
            * 10
        )

        ratio = min(
            1,
            speed / dist,
        )

        player["x"] += dx * ratio
        player["y"] += dy * ratio

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
    ):

        owner = self._find_ball_owner()

        if not owner:
            self._choose_ball_winner()

            return

        self.ball["x"] = owner["x"]
        self.ball["y"] = owner["y"]

        owner["cooldown"] = max(
            0,
            owner["cooldown"]
            - real_seconds,
        )

        if owner["cooldown"] > 0:
            return

        self._decide_action(
            owner
        )

    # ========================================================
    # DECISION SYSTEM
    # ========================================================

    def _decide_action(
        self,
        player: Dict[str, Any],
    ):

        side = player["side"]

        team = (
            self.home
            if side == "home"
            else self.away
        )

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        goal_x = (
            100
            if side == "home"
            else 0
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
        # SHOOT
        # ----------------------------------------------------

        shooting_distance = (
            role in [
                "ST",
                "RW",
                "LW",
                "CAM",
            ]
            and distance_to_goal <= 25
        )

        if shooting_distance:

            shot_probability = (
                0.30
                + (
                    player["shooting"]
                    / 500
                )
            )

            if pressure > 3:
                shot_probability *= 0.72

            if random.random() < shot_probability:
                self._shoot(
                    player
                )

                return

        # ----------------------------------------------------
        # CROSS
        # ----------------------------------------------------

        wide_area = (
            player["y"] <= 10
            or player["y"] >= 50
        )

        if (
            wide_area
            and distance_to_goal <= 38
            and role in [
                "RW",
                "LW",
                "RM",
                "LM",
                "RWB",
                "LWB",
            ]
        ):

            if random.random() < 0.30:
                self._cross(
                    player
                )

                return

        # ----------------------------------------------------
        # DRIBBLE
        # ----------------------------------------------------

        if (
            pressure < 5
            and player["dribbling"] >= 55
            and random.random()
            < 0.42
        ):

            self._dribble(
                player
            )

            return

        # ----------------------------------------------------
        # THROUGH BALL
        # ----------------------------------------------------

        if (
            player["vision"] >= 60
            and random.random() < 0.22
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
    # FIND BALL OWNER
    # ========================================================

    def _find_ball_owner(self):

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

            if player and player.get(
                "hasBall"
            ):
                return player

        return None

    # ========================================================
    # PASS
    # ========================================================

    def _pass(
        self,
        player: Dict[str, Any],
    ):

        side = player["side"]

        teammates = [
            p
            for p in self._all_players(side)
            if p["id"] != player["id"]
        ]

        if not teammates:
            return

        direction = (
            1
            if side == "home"
            else -1
        )

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
                progress * 1.7
                + teammate["vision"]
                * 0.1
                - d * 0.45
            )

            # Prefer forward players
            if teammate["role"] in [
                "ST",
                "RW",
                "LW",
                "CAM",
            ]:
                score += 7

            candidates.append(
                (
                    score,
                    teammate,
                )
            )

        if not candidates:
            teammate = min(
                teammates,
                key=lambda p: distance(
                    player,
                    p,
                ),
            )
        else:
            candidates.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            teammate = candidates[0][1]

        success_chance = (
            0.70
            + (
                player["passing"]
                - 70
            ) / 250
        )

        success_chance -= (
            self._pressure(
                player,
                "away"
                if side == "home"
                else "home",
            )
            < 5
        ) * 0.10

        success_chance = clamp(
            success_chance,
            0.35,
            0.95,
        )

        player["stats"]["passes"] += 1

        self._team_stats(side)[
            "passes"
        ] += 1

        if random.random() > success_chance:

            self._event(
                "bad_pass",
                f"{player['name']} lost the ball",
                side,
                player["id"],
            )

            self._lose_ball_to_opponent(
                player
            )

            player["cooldown"] = 0.7

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

        # Forward pass gets a little attacking push
        direction = (
            1
            if side == "home"
            else -1
        )

        if (
            teammate["role"]
            in [
                "ST",
                "RW",
                "LW",
                "CAM",
            ]
        ):

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
            extra={
                "receiverId": teammate["id"],
                "receiver": teammate["name"],
            },
        )

        player["cooldown"] = (
            0.6
            + random.random()
            * 0.8
        )

    # ========================================================
    # THROUGH BALL
    # ========================================================

    def _through_ball(
        self,
        player: Dict[str, Any],
    ) -> bool:

        side = player["side"]

        teammates = [
            p
            for p in self._all_players(side)
            if p["id"] != player["id"]
            and p["role"] in [
                "ST",
                "RW",
                "LW",
                "CAM",
            ]
        ]

        if not teammates:
            return False

        direction = (
            1
            if side == "home"
            else -1
        )

        forward = [
            p
            for p in teammates
            if (
                p["x"] - player["x"]
            ) * direction > 3
        ]

        if not forward:
            return False

        target = max(
            forward,
            key=lambda p: (
                (
                    p["x"]
                    - player["x"]
                )
                * direction
            )
            + p["pace"] * 0.1,
        )

        chance = (
            0.48
            + (
                player["vision"]
                - 60
            ) / 180
        )

        chance = clamp(
            chance,
            0.25,
            0.85,
        )

        player["stats"]["passes"] += 1
        self._team_stats(side)["passes"] += 1

        if random.random() > chance:

            self._event(
                "through_ball_failed",
                f"{player['name']} tried a through ball but it was intercepted",
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

        target["targetX"] = clamp(
            target["x"]
            + direction * 10,
            5,
            95,
        )

        target["action"] = "run"

        self._event(
            "through_ball",
            f"{player['name']} sent a through ball to {target['name']}",
            side,
            player["id"],
            extra={
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
    ):

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

        closest = None

        opponents = self._all_players(
            opponent_side
        )

        if opponents:

            closest = min(
                opponents,
                key=lambda p: distance(
                    player,
                    p,
                ),
            )

        success = (
            0.50
            + (
                player["dribbling"]
                - 65
            ) / 150
        )

        if closest:

            success -= max(
                0,
                (
                    6
                    - distance(
                        player,
                        closest,
                    )
                )
                * 0.035,
            )

        success = clamp(
            success,
            0.20,
            0.85,
        )

        player["stats"]["dribbles"] += 1

        if random.random() < success:

            player["x"] = clamp(
                player["x"]
                + direction
                * random.uniform(
                    2,
                    6,
                ),
                3,
                97,
            )

            player["y"] = clamp(
                player["y"]
                + random.uniform(
                    -3,
                    3,
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

            self._event(
                "tackle",
                f"{player['name']} lost the ball under pressure",
                opponent_side,
                closest["id"]
                if closest
                else None,
            )

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

            else:
                self._lose_ball_to_opponent(
                    player
                )

        player["cooldown"] = 0.8

    # ========================================================
    # SHOOT
    # ========================================================

    def _shoot(
        self,
        player: Dict[str, Any],
    ):

        side = player["side"]

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        team = (
            self.home
            if side == "home"
            else self.away
        )

        opponent = (
            self.away
            if side == "home"
            else self.home
        )

        direction = (
            1
            if side == "home"
            else -1
        )

        goal_x = (
            100
            if side == "home"
            else 0
        )

        distance_to_goal = abs(
            goal_x
            - player["x"]
        )

        angle_factor = clamp(
            1
            - abs(
                player["y"]
                - 30
            ) / 40,
            0.55,
            1.0,
        )

        distance_factor = clamp(
            1
            - (
                distance_to_goal
                / 45
            ),
            0.35,
            1.0,
        )

        shot_quality = (
            player["shooting"]
            * 0.55
            + player["composure"]
            if "composure" in player
            else player["shooting"] * 0.65
        )

        shot_quality *= angle_factor
        shot_quality *= distance_factor

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
            goalkeeper = opponent["players"][0]

        save_power = (
            goalkeeper["goalkeeping"]
            * 0.60
        )

        goal_probability = (
            0.08
            + (
                shot_quality
                - save_power
            ) / 170
        )

        goal_probability = clamp(
            goal_probability,
            0.03,
            0.65,
        )

        player["stats"]["shots"] += 1

        team["stats"]["shots"] += 1

        self._team_stats(side)[
            "shots"
        ] += 1

        on_target_probability = (
            0.48
            + player["shooting"]
            / 300
        )

        on_target = (
            random.random()
            < on_target_probability
        )

        if on_target:

            player["stats"][
                "shotsOnTarget"
            ] += 1

            team["stats"][
                "shotsOnTarget"
            ] = team["stats"].get(
                "shotsOnTarget",
                0,
            ) + 1

            self._team_stats(side)[
                "shotsOnTarget"
            ] += 1

        self._event(
            "shot",
            f"{player['name']} took a shot",
            side,
            player["id"],
            extra={
                "onTarget": on_target,
            },
        )

        if on_target and random.random() < goal_probability:

            self._goal(
                player
            )

        elif on_target:

            goalkeeper["stats"][
                "saves"
            ] += 1

            self._team_stats(
                opponent_side
            )["saves"] += 1

            opponent["stats"][
                "saves"
            ] = opponent["stats"].get(
                "saves",
                0,
            ) + 1

            self._event(
                "save",
                f"{goalkeeper['name']} made a save",
                opponent_side,
                goalkeeper["id"],
            )

            # Sometimes save goes for corner
            if random.random() < 0.22:

                self._corner(
                    side,
                    goalkeeper,
                )

            else:

                self._lose_ball_to_opponent(
                    goalkeeper,
                    new_side=opponent_side,
                )

        else:

            # Miss can lead to goal kick
            self._event(
                "shot_missed",
                f"{player['name']} missed the target",
                side,
                player["id"],
            )

            self._goal_kick(
                opponent_side
            )

        player["cooldown"] = 1.4

    # ========================================================
    # CROSS
    # ========================================================

    def _cross(
        self,
        player: Dict[str, Any],
    ):

        side = player["side"]

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        attackers = [
            p
            for p in self._all_players(side)
            if p["role"] in [
                "ST",
                "CAM",
                "RW",
                "LW",
            ]
        ]

        if not attackers:
            return

        target = min(
            attackers,
            key=lambda p: distance(
                player,
                p,
            ),
        )

        success = (
            0.45
            + (
                player["passing"]
                - 60
            ) / 160
        )

        if random.random() > success:

            self._event(
                "cross_failed",
                f"{player['name']} sent a poor cross",
                side,
                player["id"],
            )

            self._lose_ball_to_opponent(
                player
            )

            player["cooldown"] = 1.0

            return

        self._give_ball(
            target,
            side,
        )

        self._event(
            "cross",
            f"{player['name']} crossed for {target['name']}",
            side,
            player["id"],
            extra={
                "receiverId": target["id"],
                "receiver": target["name"],
            },
        )

        # Header / quick shot after cross
        if random.random() < 0.50:

            target["cooldown"] = 0.1

            self._shoot(
                target
            )

        player["cooldown"] = 1.0

    # ========================================================
    # GOAL
    # ========================================================

    def _goal(
        self,
        scorer: Dict[str, Any],
    ):

        side = scorer["side"]

        self.score[side] += 1

        self._team_stats(
            side
        )["goals"] += 1

        scorer["stats"][
            "goals"
        ] += 1

        scorer["action"] = "goal"

        self._event(
            "goal",
            f"GOAL! {scorer['name']} scored for {self._team(side)['name']}",
            side,
            scorer["id"],
            extra={
                "scorer": scorer["name"],
                "score": self.score.copy(),
            },
        )

        self.ball["state"] = "goal"

        self._reset_after_goal(
            opposite_side=(
                "away"
                if side == "home"
                else "home"
            )
        )

    def _reset_after_goal(
        self,
        opposite_side: str,
    ):

        self._clear_ball()

        team = self._team(
            opposite_side
        )

        player = self._find_best_player(
            team,
            [
                "CM",
                "CAM",
                "CDM",
            ],
        )

        if not player:
            player = team["players"][0]

        player["x"] = (
            50
            if opposite_side == "home"
            else 50
        )

        player["y"] = 30

        self._give_ball(
            player,
            opposite_side,
        )

        self.attack_team = opposite_side

    # ========================================================
    # CORNER
    # ========================================================

    def _corner(
        self,
        side: str,
        goalkeeper: Optional[Dict[str, Any]] = None,
    ):

        if time.time() < self.cooldowns[
            "corner"
        ][side]:
            return

        self.cooldowns[
            "corner"
        ][side] = (
            time.time()
            + 2
        )

        self._team_stats(
            side
        )["corners"] += 1

        team = self._team(side)

        taker = self._find_best_player(
            team,
            [
                "RW",
                "LW",
                "RM",
                "LM",
                "CAM",
            ],
        )

        if not taker:
            taker = team["players"][0]

        taker["stats"][
            "corners"
        ] += 1

        self._event(
            "corner",
            f"Corner kick for {team['name']}",
            side,
            taker["id"],
        )

        attackers = [
            p
            for p in self._all_players(side)
            if p["role"] in [
                "ST",
                "CB",
                "CAM",
            ]
        ]

        if attackers and random.random() < 0.65:

            target = random.choice(
                attackers
            )

            self._give_ball(
                target,
                side,
            )

            if random.random() < 0.35:
                self._shoot(
                    target
                )

    # ========================================================
    # GOAL KICK
    # ========================================================

    def _goal_kick(
        self,
        side: str,
    ):

        team = self._team(side)

        goalkeeper = next(
            (
                p
                for p in team["players"]
                if p["active"]
                and p["role"] == "GK"
            ),
            None,
        )

        if not goalkeeper:
            goalkeeper = team["players"][0]

        self._give_ball(
            goalkeeper,
            side,
        )

        self._event(
            "goal_kick",
            f"Goal kick for {team['name']}",
            side,
            goalkeeper["id"],
        )

    # ========================================================
    # BALL LOSS
    # ========================================================

    def _lose_ball_to_opponent(
        self,
        player: Dict[str, Any],
        new_side: Optional[str] = None,
    ):

        side = new_side

        if side is None:
            side = (
                "away"
                if player["side"] == "home"
                else "home"
            )

        opponents = self._all_players(
            side
        )

        if not opponents:
            self._clear_ball()
            return

        closest = min(
            opponents,
            key=lambda p: distance(
                player,
                p,
            ),
        )

        self._give_ball(
            closest,
            side,
        )

        self.possession_team = side

    def _choose_ball_winner(self):

        candidates = []

        for side in [
            "home",
            "away",
        ]:

            for player in self._all_players(
                side
            ):

                candidates.append(
                    (
                        distance(
                            player,
                            self.ball,
                        ),
                        player,
                    )
                )

        if not candidates:
            return

        candidates.sort(
            key=lambda x: x[0]
        )

        player = candidates[0][1]

        self._give_ball(
            player,
            player["side"],
        )

    # ========================================================
    # RANDOM EVENTS
    # ========================================================

    def _maybe_random_event(self):

        # Tackle/interception
        if random.random() < 0.025:

            self._maybe_tackle()

        # Foul
        if random.random() < 0.008:

            self._maybe_foul()

        # Possession update
        self._update_possession_stats()

    def _maybe_tackle(self):

        owner = self._find_ball_owner()

        if not owner:
            return

        opponent_side = (
            "away"
            if owner["side"] == "home"
            else "home"
        )

        defenders = self._all_players(
            opponent_side
        )

        if not defenders:
            return

        defender = min(
            defenders,
            key=lambda p: distance(
                p,
                owner,
            ),
        )

        d = distance(
            defender,
            owner,
        )

        if d > 4:
            return

        tackle_probability = (
            0.35
            + defender["defending"]
            / 300
        )

        if random.random() < tackle_probability:

            defender["stats"][
                "tackles"
            ] += 1

            self._team_stats(
                opponent_side
            )["tackles"] += 1

            self._give_ball(
                defender,
                opponent_side,
            )

            self._event(
                "tackle",
                f"{defender['name']} won the ball",
                opponent_side,
                defender["id"],
            )

        else:

            owner["stats"][
                "fouled"
            ] += 1

    def _maybe_foul(self):

        owner = self._find_ball_owner()

        if not owner:
            return

        opponent_side = (
            "away"
            if owner["side"] == "home"
            else "home"
        )

        defenders = self._all_players(
            opponent_side
        )

        if not defenders:
            return

        defender = min(
            defenders,
            key=lambda p: distance(
                p,
                owner,
            ),
        )

        if distance(
            defender,
            owner,
        ) > 5:
            return

        if random.random() < 0.35:

            defender["stats"][
                "fouls"
            ] += 1

            self._team_stats(
                opponent_side
            )["fouls"] += 1

            self._event(
                "foul",
                f"Foul by {defender['name']}",
                opponent_side,
                defender["id"],
            )

            self._give_ball(
                owner,
                owner["side"],
            )

    # ========================================================
    # POSSESSION
    # ========================================================

    def _update_possession_stats(self):

        home_count = 0
        away_count = 0

        owner = self._find_ball_owner()

        if owner:

            if owner["side"] == "home":
                home_count = 1
            else:
                away_count = 1

        current = self._team_stats(
            self.possession_team
        )

        other_side = (
            "away"
            if self.possession_team == "home"
            else "home"
        )

        current["possession"] = clamp(
            current.get(
                "possession",
                50,
            ) + 0.05,
            0,
            100,
        )

        other = self._team_stats(
            other_side
        )

        other["possession"] = clamp(
            100
            - current["possession"],
            0,
            100,
        )

    # ========================================================
    # HALFTIME
    # ========================================================

    def _halftime(self):

        self.halftime_done = True

        self.status = "halftime"
        self.running = False

        self._event(
            "halftime",
            "Half time",
            None,
            None,
            extra={
                "score": self.score.copy(),
            },
        )

        self.thread = threading.Thread(
            target=self._auto_resume_after_halftime,
            daemon=True,
        )

        self.thread.start()

    def _auto_resume_after_halftime(self):

        time.sleep(2)

        with self.lock:

            if (
                not self.finished
                and self.status == "halftime"
            ):

                self.status = "playing"
                self.running = True
                self.last_tick = time.time()

                self._event(
                    "second_half",
                    "Second half started",
                    None,
                    None,
                )

    # ========================================================
    # FINISH
    # ========================================================

    def _finish_match(self):

        if self.finished:
            return

        self.finished = True
        self.running = False
        self.status = "finished"

        self._clear_ball()

        self._event(
            "full_time",
            "Full time",
            None,
            None,
            extra={
                "score": self.score.copy(),
            },
        )

    def finish(self):

        with self.lock:

            self._finish_match()

            return self.snapshot()

    # ========================================================
    # PAUSE
    # ========================================================

    def pause(self):

        with self.lock:

            if not self.finished:
                self.running = False

                if self.status == "playing":
                    self.status = "paused"

                self._event(
                    "paused",
                    "Match paused",
                    None,
                    None,
                )

            return self.snapshot()

    # ========================================================
    # TACTICS
    # ========================================================

    def set_tactics(
        self,
        side: str,
        tactics: Dict[str, Any],
    ):

        with self.lock:

            team = self._team(
                side
            )

            if not isinstance(
                tactics,
                dict,
            ):
                return self.snapshot()

            team["tactics"].update(
                self._create_tactics(
                    tactics
                )
            )

            self._event(
                "tactics",
                f"{team['name']} changed tactics",
                side,
                None,
            )

            return self.snapshot()

    # ========================================================
    # FORMATION
    # ========================================================

    def set_formation(
        self,
        side: str,
        formation: str,
    ):

        with self.lock:

            if formation not in FORMATIONS:
                raise ValueError(
                    f"Unsupported formation: {formation}"
                )

            team = self._team(
                side
            )

            team["formation"] = formation

            positions = self._formation_positions(
                formation,
                side,
            )

            roles = FORMATIONS[
                formation
            ]

            for index, player in enumerate(
                self._all_players(side)
            ):

                if index >= len(positions):
                    break

                player["role"] = roles[index]
                player["position"] = roles[index]

                player["targetX"] = positions[
                    index
                ]["x"]

                player["targetY"] = positions[
                    index
                ]["y"]

            self._event(
                "formation",
                f"{team['name']} changed formation to {formation}",
                side,
                None,
            )

            return self.snapshot()

    # ========================================================
    # SUBSTITUTION
    # ========================================================

    def substitute(
        self,
        side: str,
        outgoing_id: str,
        incoming_id: str,
    ):

        with self.lock:

            team = self._team(
                side
            )

            if team["substitutionsUsed"] >= 5:

                raise ValueError(
                    "Maximum substitutions reached"
                )

            outgoing = self._find_player(
                side,
                outgoing_id,
            )

            incoming = next(
                (
                    p
                    for p in team["bench"]
                    if str(p["id"])
                    == str(incoming_id)
                ),
                None,
            )

            if not outgoing:
                raise ValueError(
                    "Outgoing player not found"
                )

            if not incoming:
                raise ValueError(
                    "Incoming player not found"
                )

            incoming["active"] = True
            incoming["isBench"] = False

            incoming["x"] = outgoing["x"]
            incoming["y"] = outgoing["y"]

            outgoing["active"] = False
            outgoing["hasBall"] = False

            team["players"] = [
                p
                for p in team["players"]
                if p["id"] != outgoing["id"]
            ]

            team["players"].append(
                incoming
            )

            team["bench"] = [
                p
                for p in team["bench"]
                if p["id"] != incoming["id"]
            ]

            team["bench"].append(
                outgoing
            )

            outgoing["isBench"] = True

            team["substitutionsUsed"] += 1

            if self.ball["owner"] == outgoing["id"]:

                replacement = incoming

                self._give_ball(
                    replacement,
                    side,
                )

            self._event(
                "substitution",
                f"{team['name']} substituted {outgoing['name']} for {incoming['name']}",
                side,
                incoming["id"],
                extra={
                    "outgoingId": outgoing["id"],
                    "incomingId": incoming["id"],
                    "outgoing": outgoing["name"],
                    "incoming": incoming["name"],
                },
            )

            return self.snapshot()

    # ========================================================
    # EVENT
    # ========================================================

    def _event(
        self,
        event_type: str,
        message: str,
        side: Optional[str],
        player_id: Optional[str],
        extra: Optional[Dict[str, Any]] = None,
    ):

        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "minute": self.minute,
            "second": self.second,
            "message": message,
            "side": side,
            "playerId": player_id,
            "timestamp": int(
                time.time() * 1000
            ),
        }

        if extra:
            event.update(
                extra
            )

        self.events.append(
            event
        )

        if len(self.events) > MAX_EVENTS:
            self.events = self.events[
                -MAX_EVENTS:
            ]

    # ========================================================
    # TEAM HELPERS
    # ========================================================

    def _team(
        self,
        side: str,
    ):

        return (
            self.home
            if side == "home"
            else self.away
        )

    def _team_stats(
        self,
        side: str,
    ):

        return self.stats[
            "home"
            if side == "home"
            else "away"
        ]

    # ========================================================
    # SNAPSHOT
    # ========================================================

    def snapshot(self):

        with self.lock:

            return {
                "ok": True,

                "matchId": self.match_id,

                "status": self.status,

                "running": self.running,

                "finished": self.finished,

                "minute": self.minute,

                "second": self.second,

                "score": {
                    "home": self.score["home"],
                    "away": self.score["away"],
                },

                "ball": {
                    "x": round(
                        self.ball["x"],
                        2,
                    ),
                    "y": round(
                        self.ball["y"],
                        2,
                    ),
                    "owner": self.ball[
                        "owner"
                    ],
                    "team": self.ball[
                        "team"
                    ],
                    "state": self.ball[
                        "state"
                    ],
                },

                "home": self._serialize_team(
                    self.home
                ),

                "away": self._serialize_team(
                    self.away
                ),

                "stats": self.stats,

                "events": self.events[
                    -MAX_EVENTS:
                ],

                "lastEvent": (
                    self.events[-1]
                    if self.events
                    else None
                ),
            }

    # ========================================================
    # SERIALIZE TEAM
    # ========================================================

    def _serialize_team(
        self,
        team: Dict[str, Any],
    ):

        return {
            "id": team["id"],
            "name": team["name"],
            "logo": team["logo"],
            "side": team["side"],
            "formation": team["formation"],
            "tactics": team["tactics"],
            "substitutionsUsed": team[
                "substitutionsUsed"
            ],

            "players": [
                self._serialize_player(
                    p
                )
                for p in team["players"]
            ],

            "bench": [
                self._serialize_player(
                    p
                )
                for p in team["bench"]
            ],

            "stats": team["stats"],
        }

    def _serialize_player(
        self,
        player: Dict[str, Any],
    ):

        return {
            "id": player["id"],
            "name": player["name"],
            "number": player["number"],
            "position": player["position"],
            "role": player["role"],
            "side": player["side"],
            "active": player["active"],

            "pace": round(
                player["pace"],
                1,
            ),

            "passing": round(
                player["passing"],
                1,
            ),

            "shooting": round(
                player["shooting"],
                1,
            ),

            "dribbling": round(
                player["dribbling"],
                1,
            ),

            "defending": round(
                player["defending"],
                1,
            ),

            "stamina": round(
                player["stamina"],
                1,
            ),

            "strength": round(
                player["strength"],
                1,
            ),

            "vision": round(
                player["vision"],
                1,
            ),

            "goalkeeping": round(
                player["goalkeeping"],
                1,
            ),

            "energy": round(
                player["energy"],
                1,
            ),

            "x": round(
                player["x"],
                2,
            ),

            "y": round(
                player["y"],
                2,
            ),

            "targetX": round(
                player["targetX"],
                2,
            ),

            "targetY": round(
                player["targetY"],
                2,
            ),

            "hasBall": player[
                "hasBall"
            ],

            "action": player[
                "action"
            ],

            "stats": player[
                "stats"
            ],
        }


# ============================================================
# COMPATIBILITY ALIAS
# ============================================================

# Some older frontend files may import FootballEngine
# instead of FootballMatch. This prevents unnecessary
# import errors.
FootballEngine = FootballMatch
