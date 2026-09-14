from __future__ import annotations

import math
import random
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# CONFIG
# ============================================================

PITCH_WIDTH = 100.0
PITCH_HEIGHT = 60.0

MATCH_MINUTES = 90
REAL_MATCH_SECONDS = 480.0       # 8 min real = 90 football minutes
TICK_SECONDS = 0.20

MAX_EVENTS = 400
MAX_PLAYERS = 40

HOME_GOAL_X = 100.0
AWAY_GOAL_X = 0.0
GOAL_Y_MIN = 22.0
GOAL_Y_MAX = 38.0

PENALTY_BOX_DEPTH = 18.0
PENALTY_BOX_WIDTH_MIN = 14.0
PENALTY_BOX_WIDTH_MAX = 46.0

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
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def normalize_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def weighted_choice(items: List[Tuple[Any, float]]) -> Any:
    total = sum(w for _, w in items)
    if total <= 0:
        return random.choice(items)[0]
    r = random.random() * total
    upto = 0.0
    for item, w in items:
        upto += w
        if r <= upto:
            return item
    return items[-1][0]


def is_inside_box(x: float, y: float, defending_side: str) -> bool:
    """Kureba niba umupira uri mu kazu y'igare."""

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

        # Injury time (in football minutes) - added at end of each half
        self.injury_time_first_half = random.randint(1, 5)
        self.injury_time_second_half = random.randint(2, 6)

        self.score = {"home": 0, "away": 0}

        self.ball = {
            "x": 50.0,
            "y": 30.0,
            "vx": 0.0,
            "vy": 0.0,
            "owner": None,
            "team": None,
            "state": "dead",
        }

        self.events: List[Dict[str, Any]] = []

        self._loop_thread: Optional[threading.Thread] = None
        self._halftime_thread: Optional[threading.Thread] = None

        self.last_tick = time.time()

        self.halftime_done = False
        self.second_half_started = False

        self.possession_team = "home"
        self.attack_team = "home"

        self.cooldowns = {
            "shot": {"home": 0.0, "away": 0.0},
            "corner": {"home": 0.0, "away": 0.0},
            "foul": {"home": 0.0, "away": 0.0},
        }

        # Possession tracking (real seconds)
        self.possession_time = {"home": 0.0, "away": 0.0}

        self.home = self._create_team(
            config.get("home") or {}, "home", "Home",
        )
        self.away = self._create_team(
            config.get("away") or {}, "away", "Away",
        )

        self.stats = self._create_match_stats()
        self._place_players()

        self._event("match_created", "Match created", None, None)

    # ========================================================
    # TEAM CREATION
    # ========================================================

    def _create_team(
        self,
        source: Dict[str, Any],
        side: str,
        fallback_name: str,
    ) -> Dict[str, Any]:

        formation = normalize_text(source.get("formation"), "4-3-3")
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
            for index, player in enumerate(players_source[:11]):
                if isinstance(player, dict):
                    players.append(
                        self._create_player(player, index, side)
                    )

        bench: List[Dict[str, Any]] = []
        if isinstance(bench_source, list):
            for index, player in enumerate(bench_source[:12]):
                if isinstance(player, dict):
                    bench.append(
                        self._create_player(
                            player, index + 11, side, is_bench=True,
                        )
                    )

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
                source.get("id") or source.get("clubId"), side,
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

            "pace":        self._rating(source, ratings, "pace", 68),
            "passing":     self._rating(source, ratings, "passing", 68),
            "shooting":    self._rating(source, ratings, "shooting", 65),
            "dribbling":   self._rating(source, ratings, "dribbling", 67),
            "defending":   self._rating(source, ratings, "defending", 65),
            "stamina":     self._rating(source, ratings, "stamina", 75),
            "strength":    self._rating(source, ratings, "strength", 70),
            "vision":      self._rating(source, ratings, "vision", 68),
            "composure":   self._rating(source, ratings, "composure", 68),
            "goalkeeping": self._rating(source, ratings, "goalkeeping", 65),

            "morale": 70.0,
            "energy": 100.0,
            "injured": False,

            "x": 50.0,
            "y": 30.0,
            "targetX": 50.0,
            "targetY": 30.0,

            "hasBall": False,
            "action": "idle",
            "lastActionAt": 0.0,
            "cooldown": 0.0,

            "yellowCards": 0,
            "redCard": False,
            "suspended": False,

            "stats": self._empty_player_stats(),
        }

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
        return clamp(safe_float(value, default), 1, 100)

    # ========================================================
    # TACTICS
    # ========================================================

    def _create_tactics(self, source: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "mentality": normalize_text(
                source.get("mentality"), "balanced",
            ),
            "tempo": clamp(
                safe_float(source.get("tempo"), 60), 1, 100,
            ),
            "pressing": normalize_text(
                source.get("pressing"), "medium",
            ),
            "defensiveLine": normalize_text(
                source.get("defensiveLine"), "medium",
            ),
            "width": clamp(
                safe_float(source.get("width"), 55), 1, 100,
            ),
        }

    # ========================================================
    # STATS
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

    def _empty_team_stats(self) -> Dict[str, Any]:
        return {
            "possession": 50,
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

    def _create_match_stats(self) -> Dict[str, Dict[str, Any]]:
        return {
            "home": self._empty_team_stats(),
            "away": self._empty_team_stats(),
        }

    # ========================================================
    # PLAYER POSITIONS
    # ========================================================

    def _formation_positions(
        self, formation: str, side: str,
    ) -> List[Dict[str, float]]:

        attacking = side == "home"

        if formation == "4-4-2":
            positions = [
                (8, 30), (22, 8), (18, 22), (18, 38), (22, 52),
                (42, 8), (38, 23), (38, 37), (42, 52),
                (70, 22), (70, 38),
            ]
        elif formation == "4-3-3":
            positions = [
                (8, 30), (22, 8), (18, 22), (18, 38), (22, 52),
                (40, 18), (38, 30), (40, 42),
                (68, 10), (74, 30), (68, 50),
            ]
        elif formation == "3-5-2":
            positions = [
                (8, 30),
                (20, 16), (18, 30), (20, 44),
                (38, 7), (36, 20), (38, 30), (36, 40), (38, 53),
                (70, 22), (70, 38),
            ]
        elif formation == "5-3-2":
            positions = [
                (8, 30),
                (18, 7), (15, 19), (16, 30), (15, 41), (18, 53),
                (38, 18), (38, 30), (38, 42),
                (70, 22), (70, 38),
            ]
        elif formation == "4-1-4-1":
            positions = [
                (8, 30), (22, 8), (18, 22), (18, 38), (22, 52),
                (33, 30),
                (48, 8), (44, 22), (44, 38), (48, 52),
                (72, 30),
            ]
        else:  # 4-2-3-1
            positions = [
                (8, 30), (22, 8), (18, 22), (18, 38), (22, 52),
                (35, 22), (35, 38),
                (52, 10), (52, 30), (52, 50),
                (72, 30),
            ]

        result: List[Dict[str, float]] = []
        for x, y in positions:
            if not attacking:
                x = PITCH_WIDTH - x
            result.append({"x": float(x), "y": float(y)})

        return result

    def _place_players(self) -> None:
        for team in [self.home, self.away]:
            positions = self._formation_positions(
                team["formation"], team["side"],
            )
            roles = FORMATIONS.get(team["formation"], FORMATIONS["4-3-3"])

            for index, player in enumerate(team["players"]):
                position = positions[min(index, len(positions) - 1)]
                role = roles[min(index, len(roles) - 1)]

                player["role"] = role
                player["position"] = role
                player["x"] = position["x"]
                player["y"] = position["y"]
                player["targetX"] = position["x"]
                player["targetY"] = position["y"]

        # Kickoff with home central midfielder
        home_mid = self._find_best_player(
            self.home, ["CM", "CAM", "CDM"],
        )
        if home_mid:
            self._give_ball(home_mid, "home")

    # ========================================================
    # PLAYER SEARCH
    # ========================================================

    def _all_players(self, side: str) -> List[Dict[str, Any]]:
        team = self.home if side == "home" else self.away
        return [p for p in team["players"] if p.get("active")]

    def _find_player(
        self, side: str, player_id: str,
    ) -> Optional[Dict[str, Any]]:

        for player in self._all_players(side):
            if str(player["id"]) == str(player_id):
                return player
        return None

    def _find_best_player(
        self, team: Dict[str, Any], positions: List[str],
    ) -> Optional[Dict[str, Any]]:

        candidates = [
            p for p in team["players"]
            if p.get("active")
            and (p.get("position") in positions
                 or p.get("role") in positions)
        ]

        if not candidates:
            candidates = [p for p in team["players"] if p.get("active")]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda p: p["passing"] + p["vision"] + p["stamina"],
        )

    # ========================================================
    # BALL
    # ========================================================

    def _give_ball(self, player: Dict[str, Any], side: str) -> None:
        for team_side in ["home", "away"]:
            for p in self._all_players(team_side):
                p["hasBall"] = False

        player["hasBall"] = True
        self.ball["owner"] = player["id"]
        self.ball["team"] = side
        self.ball["x"] = player["x"]
        self.ball["y"] = player["y"]
        self.ball["vx"] = 0.0
        self.ball["vy"] = 0.0
        self.ball["state"] = "controlled"
        self.possession_team = side

    def _clear_ball(self) -> None:
        for side in ["home", "away"]:
            for player in self._all_players(side):
                player["hasBall"] = False

        self.ball["owner"] = None
        self.ball["state"] = "free"

    # ========================================================
    # MATCH START / STOP
    # ========================================================

    def start(self) -> Dict[str, Any]:
        with self.lock:
            if self.finished:
                return self.snapshot()

            if self.status == "playing":
                return self.snapshot()

            self.status = "playing"
            self.running = True
            self.last_tick = time.time()

            if (
                self._loop_thread is None
                or not self._loop_thread.is_alive()
            ):
                self._loop_thread = threading.Thread(
                    target=self._run_loop,
                    daemon=True,
                )
                self._loop_thread.start()

            self._event("match_started", "Match started", None, None)
            return self.snapshot()

    def pause(self) -> Dict[str, Any]:
        with self.lock:
            if not self.finished:
                self.running = False
                if self.status == "playing":
                    self.status = "paused"
                self._event("paused", "Match paused", None, None)
            return self.snapshot()

    def resume(self) -> Dict[str, Any]:
        with self.lock:
            if self.finished:
                return self.snapshot()

            self.running = True
            self.status = "playing"
            self.last_tick = time.time()

            if (
                self._loop_thread is None
                or not self._loop_thread.is_alive()
            ):
                self._loop_thread = threading.Thread(
                    target=self._run_loop,
                    daemon=True,
                )
                self._loop_thread.start()

            self._event("resumed", "Match resumed", None, None)
            return self.snapshot()

    def finish(self) -> Dict[str, Any]:
        with self.lock:
            self._finish_match()
            return self.snapshot()

    # ========================================================
    # MAIN LOOP
    # ========================================================

    def _run_loop(self) -> None:
        while True:
            with self.lock:
                if self.finished:
                    break

                if self.running:
                    now = time.time()
                    elapsed = now - self.last_tick
                    self.last_tick = now
                    elapsed = clamp(elapsed, 0.01, 1.0)
                    self._advance(elapsed)
                else:
                    # Reset so we don't jump when we resume
                    self.last_tick = time.time()

            time.sleep(TICK_SECONDS)

    # ========================================================
    # ADVANCE
    # ========================================================

    def _advance(self, real_seconds: float) -> None:
        if self.status != "playing":
            return

        self.elapsed_real += real_seconds

        football_minutes = (
            self.elapsed_real / REAL_MATCH_SECONDS
        ) * MATCH_MINUTES
        football_minutes = clamp(football_minutes, 0, 90)

        self.minute = int(football_minutes)
        self.second = int((football_minutes - self.minute) * 60)

        # ---- First half end ----
        if (
            self.minute >= 45
            and not self.halftime_done
        ):
            # Stop at 45 + injury time
            if (
                self.minute >= 45 + self.injury_time_first_half
            ):
                self.minute = 45 + self.injury_time_first_half
                self.second = 0
                self._halftime()
                return

        # ---- Second half end ----
        if (
            self.minute >= 90
            and not self.finished
        ):
            if (
                self.minute
                >= 90 + self.injury_time_second_half
            ):
                self.minute = 90 + self.injury_time_second_half
                self.second = 0
                self._finish_match()
                return

        # Play
        self._update_possession_time(real_seconds)
        self._update_stamina(real_seconds)
        self._update_players(real_seconds)
        self._update_ball(real_seconds)
        self._maybe_random_event()
        self._update_possession_stats()

    # ========================================================
    # POSSESSION TIME
    # ========================================================

    def _update_possession_time(self, real_seconds: float) -> None:
        owner = self._find_ball_owner()
        side = owner["side"] if owner else self.possession_team

        self.possession_time[side] += real_seconds

    # ========================================================
    # STAMINA / MORALE
    # ========================================================

    def _update_stamina(self, real_seconds: float) -> None:
        drain = real_seconds * 0.012

        for side in ["home", "away"]:
            team = self.home if side == "home" else self.away
            pressing = team["tactics"].get("pressing", "medium")
            multiplier = {"low": 0.7, "medium": 1.0, "high": 1.35}.get(
                pressing, 1.0,
            )

            for player in self._all_players(side):
                player["energy"] = clamp(
                    player["energy"] - drain * multiplier,
                    15,
                    100,
                )
                if player["energy"] < 30:
                    player["pace"] = max(
                        40.0, player["pace"] - 0.01,
                    )

    # ========================================================
    # PLAYER MOVEMENT
    # ========================================================

    def _update_players(self, real_seconds: float) -> None:
        owner = self._find_ball_owner()

        for side in ["home", "away"]:
            team = self.home if side == "home" else self.away
            opponent_side = "away" if side == "home" else "home"

            for player in self._all_players(side):
                target = self._calculate_target(
                    player, team, owner, opponent_side,
                )
                player["targetX"] = target["x"]
                player["targetY"] = target["y"]
                self._move_player(player, real_seconds)

    def _calculate_target(
        self,
        player: Dict[str, Any],
        team: Dict[str, Any],
        owner: Optional[Dict[str, Any]],
        opponent_side: str,
    ) -> Dict[str, float]:

        side = team["side"]
        attacking = self.possession_team == side
        role = player["role"]
        base_y = player["y"]

        direction = 1 if side == "home" else -1

        if attacking:
            progression = {
                "GK": 0, "CB": 5, "RB": 9, "LB": 9,
                "RWB": 12, "LWB": 12,
                "CDM": 14, "CM": 18, "CAM": 23,
                "RM": 20, "LM": 20,
                "RW": 25, "LW": 25, "ST": 30,
            }.get(role, 12)

            target_x = 50 + direction * progression

            if owner and owner["side"] == side:
                d_to_owner = distance(player, owner)
                if (
                    role in ["ST", "RW", "LW", "CAM"]
                    and d_to_owner < 25
                ):
                    target_x += direction * 8

            if role in ["RW", "RM"]:
                target_y = 8
            elif role in ["LW", "LM"]:
                target_y = 52
            elif role == "ST":
                target_y = 25 + random.uniform(-7, 7)
            else:
                target_y = base_y + random.uniform(-1.5, 1.5)

            return {
                "x": clamp(target_x, 8, 92),
                "y": clamp(target_y, 4, 56),
            }

        # Defensive
        defensive_x = 35 if side == "home" else 65

        if role == "GK":
            defensive_x = 5 if side == "home" else 95
        elif role in ["CB", "RB", "LB", "RWB", "LWB"]:
            defensive_x = 25 if side == "home" else 75
        elif role in ["CDM", "CM"]:
            defensive_x = 33 if side == "home" else 67

        if owner:
            defensive_y = owner["y"]
        else:
            defensive_y = base_y

        pressing = team["tactics"].get("pressing", "medium")
        if pressing == "high":
            defensive_x += direction * 5

        # Chase ball if very close
        if owner and owner["side"] != side:
            if distance(player, owner) < 8:
                defensive_x = owner["x"]
                defensive_y = owner["y"]

        return {
            "x": clamp(defensive_x, 4, 96),
            "y": clamp(defensive_y + random.uniform(-5, 5), 4, 56),
        }

    def _move_player(
        self, player: Dict[str, Any], real_seconds: float,
    ) -> None:

        dx = player["targetX"] - player["x"]
        dy = player["targetY"] - player["y"]
        dist = math.hypot(dx, dy)

        if dist < 0.1:
            return

        pace_factor = 0.018 * (0.75 + player["pace"] / 100)
        energy_factor = 0.6 + (player["energy"] / 100) * 0.4
        speed = pace_factor * real_seconds * 10 * energy_factor

        ratio = min(1.0, speed / dist)
        player["x"] += dx * ratio
        player["y"] += dy * ratio
        player["x"] = clamp(player["x"], 2, 98)
        player["y"] = clamp(player["y"], 2, 58)

    # ========================================================
    # BALL UPDATE
    # ========================================================

    def _update_ball(self, real_seconds: float) -> None:
        owner = self._find_ball_owner()

        if not owner:
            # Free ball: move it, see if someone picks it up
            if self.ball["state"] == "free":
                self.ball["x"] = clamp(
                    self.ball["x"] + self.ball["vx"] * real_seconds,
                    2, 98,
                )
                self.ball["y"] = clamp(
                    self.ball["y"] + self.ball["vy"] * real_seconds,
                    2, 58,
                )
                self.ball["vx"] *= 0.9
                self.ball["vy"] *= 0.9
                self._choose_ball_winner()
            return

        self.ball["x"] = owner["x"]
        self.ball["y"] = owner["y"]

        owner["cooldown"] = max(
            0.0, owner["cooldown"] - real_seconds,
        )
        if owner["cooldown"] > 0:
            return

        self._decide_action(owner)

    # ========================================================
    # DECISION SYSTEM
    # ========================================================

    def _decide_action(self, player: Dict[str, Any]) -> None:
        side = player["side"]
        opponent_side = "away" if side == "home" else "home"
        direction = 1 if side == "home" else -1

        goal_x = HOME_GOAL_X if side == "home" else AWAY_GOAL_X
        distance_to_goal = abs(goal_x - player["x"])
        pressure = self._pressure(player, opponent_side)
        role = player["role"]

        # ---------- SHOOT ----------
        shooting_range = (
            role in ["ST", "RW", "LW", "CAM"]
            and distance_to_goal <= 28
        ) or (
            role in ["CM", "RM", "LM"]
            and distance_to_goal <= 20
        )

        if shooting_range and random.random() < 0.35:
            self._shoot(player)
            return

        # ---------- CROSS ----------
        wide_area = player["y"] <= 12 or player["y"] >= 48
        if (
            wide_area
            and distance_to_goal <= 38
            and role in ["RW", "LW", "RM", "LM", "RWB", "LWB"]
        ):
            if random.random() < 0.32:
                self._cross(player)
                return

        # ---------- THROUGH BALL ----------
        if (
            player["vision"] >= 60
            and random.random() < 0.22
        ):
            if self._through_ball(player):
                return

        # ---------- DRIBBLE ----------
        if (
            pressure < 6
            and player["dribbling"] >= 55
            and random.random() < 0.35
        ):
            self._dribble(player)
            return

        # ---------- PASS ----------
        self._pass(player)

    def _pressure(
        self, player: Dict[str, Any], opponent_side: str,
    ) -> float:
        opponents = self._all_players(opponent_side)
        if not opponents:
            return 99.0
        return min(distance(player, o) for o in opponents)

    def _find_ball_owner(self) -> Optional[Dict[str, Any]]:
        owner_id = self.ball.get("owner")
        if not owner_id:
            return None

        for side in ["home", "away"]:
            player = self._find_player(side, owner_id)
            if player and player.get("hasBall"):
                return player
        return None

    # ========================================================
    # PASS
    # ========================================================

    def _pass(self, player: Dict[str, Any]) -> None:
        side = player["side"]
        direction = 1 if side == "home" else -1

        teammates = [
            p for p in self._all_players(side)
            if p["id"] != player["id"]
        ]
        if not teammates:
            return

        candidates: List[Tuple[float, Dict[str, Any]]] = []
        for teammate in teammates:
            d = distance(player, teammate)
            if d > 40:
                continue
            progress = (teammate["x"] - player["x"]) * direction
            score = (
                progress * 1.7
                + teammate["vision"] * 0.1
                - d * 0.45
            )
            if teammate["role"] in ["ST", "RW", "LW", "CAM"]:
                score += 7
            if teammate["role"] == "GK":
                score -= 30
            candidates.append((score, teammate))

        if not candidates:
            teammate = min(
                teammates, key=lambda p: distance(player, p),
            )
        else:
            candidates.sort(key=lambda item: item[0], reverse=True)
            teammate = candidates[0][1]

        opponent_side = "away" if side == "home" else "home"
        pressure = self._pressure(player, opponent_side)

        success_chance = (
            0.70 + (player["passing"] - 70) / 250
        )
        if pressure < 5:
            success_chance -= 0.10
        if pressure < 3:
            success_chance -= 0.10

        success_chance = clamp(success_chance, 0.35, 0.95)

        player["stats"]["passes"] += 1
        self._team_stats(side)["passes"] += 1

        if random.random() > success_chance:
            self._event(
                "bad_pass",
                f"{player['name']} lost the ball",
                side,
                player["id"],
            )
            self._lose_ball_to_opponent(player)
            player["cooldown"] = 0.7
            return

        player["stats"]["passesCompleted"] += 1
        self._team_stats(side)["passesCompleted"] += 1

        self._give_ball(teammate, side)
        teammate["action"] = "receive"

        if teammate["role"] in ["ST", "RW", "LW", "CAM"]:
            teammate["targetX"] = clamp(
                teammate["x"] + direction * 5, 5, 95,
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

        player["cooldown"] = 0.6 + random.random() * 0.8

    # ========================================================
    # THROUGH BALL
    # ========================================================

    def _through_ball(self, player: Dict[str, Any]) -> bool:
        side = player["side"]
        direction = 1 if side == "home" else -1

        teammates = [
            p for p in self._all_players(side)
            if p["id"] != player["id"]
            and p["role"] in ["ST", "RW", "LW", "CAM"]
        ]
        if not teammates:
            return False

        forward = [
            p for p in teammates
            if (p["x"] - player["x"]) * direction > 3
        ]
        if not forward:
            return False

        target = max(
            forward,
            key=lambda p: (
                (p["x"] - player["x"]) * direction
            ) + p["pace"] * 0.1,
        )

        # Offside check
        if self._is_offside(target, side):
            target["stats"]["offsides"] += 1
            self._team_stats(side)["offsides"] += 1
            self._event(
                "offside",
                f"{target['name']} was flagged offside",
                side,
                target["id"],
            )
            self._free_kick(
                "away" if side == "home" else "home",
                target["x"], target["y"],
            )
            return True

        chance = clamp(
            0.48 + (player["vision"] - 60) / 180,
            0.25, 0.85,
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
            self._lose_ball_to_opponent(player)
            player["cooldown"] = 1.0
            return True

        player["stats"]["passesCompleted"] += 1
        self._team_stats(side)["passesCompleted"] += 1

        self._give_ball(target, side)
        target["targetX"] = clamp(
            target["x"] + direction * 10, 5, 95,
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

    def _is_offside(
        self, attacker: Dict[str, Any], side: str,
    ) -> bool:
        """Simple offside: attacker must be behind at least 2 defenders
        or the ball at the moment of the pass. Simplified here."""

        # Get defenders excluding GK
        opponent_side = "away" if side == "home" else "home"
        defenders = [
            p for p in self._all_players(opponent_side)
            if p["role"] != "GK"
        ]
        if not defenders:
            return False

        direction = 1 if side == "home" else -1

        # Sort defender x positions in attack direction
        defender_xs = sorted(
            [p["x"] for p in defenders],
            reverse=(direction > 0),
        )

        # Second-last defender (or last if only one)
        line = defender_xs[-2] if len(defender_xs) >= 2 else defender_xs[-1]

        # Ball position at time of pass (approx: attacker is assumed
        # to receive it and we check current)
        ball_x = self.ball["x"]

        # If attacker is beyond both the ball and the second-last
        # defender in attack direction, he's offside
        if direction > 0:
            return attacker["x"] > ball_x and attacker["x"] > line
        else:
            return attacker["x"] < ball_x and attacker["x"] < line

    # ========================================================
    # DRIBBLE
    # ========================================================

    def _dribble(self, player: Dict[str, Any]) -> None:
        side = player["side"]
        direction = 1 if side == "home" else -1
        opponent_side = "away" if side == "home" else "home"

        opponents = self._all_players(opponent_side)
        closest = (
            min(opponents, key=lambda p: distance(player, p))
            if opponents else None
        )

        success = 0.50 + (player["dribbling"] - 65) / 150

        if closest:
            success -= max(
                0.0, (6 - distance(player, closest)) * 0.035,
            )

        success = clamp(success, 0.20, 0.85)
        player["stats"]["dribbles"] += 1

        if random.random() < success:
            player["x"] = clamp(
                player["x"] + direction * random.uniform(2, 6),
                3, 97,
            )
            player["y"] = clamp(
                player["y"] + random.uniform(-3, 3), 3, 57,
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
                closest["id"] if closest else None,
            )
            if closest:
                closest["stats"]["tackles"] += 1
                self._team_stats(opponent_side)["tackles"] += 1
                self._give_ball(closest, opponent_side)
            else:
                self._lose_ball_to_opponent(player)

        player["cooldown"] = 0.8

    # ========================================================
    # SHOOT
    # ========================================================

    def _shoot(self, player: Dict[str, Any]) -> None:
        side = player["side"]
        opponent_side = "away" if side == "home" else "home"
        team = self.home if side == "home" else self.away
        opponent = self.away if side == "home" else self.home

        goal_x = HOME_GOAL_X if side == "home" else AWAY_GOAL_X
        distance_to_goal = abs(goal_x - player["x"])

        angle_factor = clamp(
            1.0 - abs(player["y"] - 30) / 40, 0.55, 1.0,
        )
        distance_factor = clamp(
            1.0 - (distance_to_goal / 45), 0.35, 1.0,
        )

        pressure = self._pressure(player, opponent_side)
        pressure_factor = clamp(1.0 - pressure / 25, 0.55, 1.0)

        shot_quality = (
            player["shooting"] * 0.55
            + player["composure"] * 0.20
            + player["strength"] * 0.05
        ) * angle_factor * distance_factor * pressure_factor

        goalkeeper = next(
            (
                p for p in opponent["players"]
                if p["active"] and p["role"] == "GK"
            ),
            None,
        )
        if goalkeeper is None and opponent["players"]:
            goalkeeper = opponent["players"][0]

        if goalkeeper is None:
            return

        save_power = goalkeeper["goalkeeping"] * 0.60

        goal_probability = clamp(
            0.08 + (shot_quality - save_power) / 170,
            0.03, 0.68,
        )

        player["stats"]["shots"] += 1
        team["stats"]["shots"] += 1
        self._team_stats(side)["shots"] += 1

        on_target_probability = (
            0.48 + player["shooting"] / 300
        )
        on_target = random.random() < on_target_probability

        if on_target:
            player["stats"]["shotsOnTarget"] += 1
            team["stats"]["shotsOnTarget"] = (
                team["stats"].get("shotsOnTarget", 0) + 1
            )
            self._team_stats(side)["shotsOnTarget"] += 1

        self._event(
            "shot",
            f"{player['name']} took a shot",
            side,
            player["id"],
            extra={"onTarget": on_target},
        )

        if on_target and random.random() < goal_probability:
            self._goal(player)

        elif on_target:
            goalkeeper["stats"]["saves"] += 1
            self._team_stats(opponent_side)["saves"] += 1
            opponent["stats"]["saves"] = (
                opponent["stats"].get("saves", 0) + 1
            )

            self._event(
                "save",
                f"{goalkeeper['name']} made a save",
                opponent_side,
                goalkeeper["id"],
            )

            if random.random() < 0.22:
                self._corner(side, goalkeeper)
            else:
                self._lose_ball_to_opponent(
                    goalkeeper, new_side=opponent_side,
                )
        else:
            self._event(
                "shot_missed",
                f"{player['name']} missed the target",
                side,
                player["id"],
            )
            self._goal_kick(opponent_side)

        player["cooldown"] = 1.4

    # ========================================================
    # CROSS
    # ========================================================

    def _cross(self, player: Dict[str, Any]) -> None:
        side = player["side"]
        attackers = [
            p for p in self._all_players(side)
            if p["role"] in ["ST", "CAM", "RW", "LW"]
        ]
        if not attackers:
            return

        target = min(
            attackers,
            key=lambda p: distance(player, p),
        )

        success = 0.45 + (player["passing"] - 60) / 160

        if random.random() > success:
            self._event(
                "cross_failed",
                f"{player['name']} sent a poor cross",
                side,
                player["id"],
            )
            self._lose_ball_to_opponent(player)
            player["cooldown"] = 1.0
            return

        self._give_ball(target, side)
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

        if random.random() < 0.50:
            target["cooldown"] = 0.1
            self._shoot(target)

        player["cooldown"] = 1.0

    # ========================================================
    # GOAL
    # ========================================================

    def _goal(self, scorer: Dict[str, Any]) -> None:
        side = scorer["side"]
        self.score[side] += 1
        self._team_stats(side)["goals"] += 1
        scorer["stats"]["goals"] += 1
        scorer["action"] = "goal"

        team = self._team(side)
        # Momentum
        team["momentum"] = clamp(team["momentum"] + 15, -100, 100)
        other = self._team("away" if side == "home" else "home")
        other["momentum"] = clamp(other["momentum"] - 15, -100, 100)

        self._event(
            "goal",
            f"GOAL! {scorer['name']} scored for {team['name']}",
            side,
            scorer["id"],
            extra={
                "scorer": scorer["name"],
                "score": self.score.copy(),
            },
        )

        self.ball["state"] = "goal"
        self._reset_after_goal(
            opposite_side="away" if side == "home" else "home",
        )

    def _reset_after_goal(self, opposite_side: str) -> None:
        self._clear_ball()
        team = self._team(opposite_side)
        player = self._find_best_player(team, ["CM", "CAM", "CDM"])
        if not player and team["players"]:
            player = team["players"][0]

        if player:
            player["x"] = 50
            player["y"] = 30
            self._give_ball(player, opposite_side)
            self.attack_team = opposite_side

    # ========================================================
    # CORNER
    # ========================================================

    def _corner(
        self,
        side: str,
        goalkeeper: Optional[Dict[str, Any]] = None,
    ) -> None:
        if time.time() < self.cooldowns["corner"][side]:
            return
        self.cooldowns["corner"][side] = time.time() + 2

        self._team_stats(side)["corners"] += 1
        team = self._team(side)

        taker = self._find_best_player(
            team, ["RW", "LW", "RM", "LM", "CAM"],
        )
        if not taker and team["players"]:
            taker = team["players"][0]

        if not taker:
            return

        taker["stats"]["corners"] += 1
        self._event(
            "corner",
            f"Corner kick for {team['name']}",
            side,
            taker["id"],
        )

        attackers = [
            p for p in self._all_players(side)
            if p["role"] in ["ST", "CB", "CAM"]
        ]

        if attackers and random.random() < 0.65:
            target = random.choice(attackers)
            self._give_ball(target, side)
            if random.random() < 0.35:
                self._shoot(target)

    # ========================================================
    # GOAL KICK
    # ========================================================

    def _goal_kick(self, side: str) -> None:
        team = self._team(side)
        goalkeeper = next(
            (
                p for p in team["players"]
                if p["active"] and p["role"] == "GK"
            ),
            None,
        )
        if not goalkeeper and team["players"]:
            goalkeeper = team["players"][0]
        if not goalkeeper:
            return

        self._give_ball(goalkeeper, side)
        self._event(
            "goal_kick",
            f"Goal kick for {team['name']}",
            side,
            goalkeeper["id"],
        )

    # ========================================================
    # FREE KICK / PENALTY
    # ========================================================

    def _free_kick(self, side: str, x: float, y: float) -> None:
        team = self._team(side)
        taker = self._find_best_player(
            team, ["CAM", "CM", "RW", "LW", "ST"],
        )
        if not taker and team["players"]:
            taker = team["players"][0]
        if not taker:
            return

        taker["x"] = clamp(x, 4, 96)
        taker["y"] = clamp(y, 4, 56)

        self._team_stats(side)["freeKicks"] += 1
        self._give_ball(taker, side)

        self._event(
            "free_kick",
            f"Free kick for {team['name']}",
            side,
            taker["id"],
        )

        # Direct free kick chance if in shooting range
        opponent_side = "away" if side == "home" else "home"
        goal_x = HOME_GOAL_X if side == "home" else AWAY_GOAL_X
        d = abs(goal_x - taker["x"])

        if d < 30 and random.random() < 0.55:
            self._shoot(taker)
            return

        taker["cooldown"] = 1.0

    def _penalty(self, side: str) -> None:
        team = self._team(side)
        taker = self._find_best_player(team, ["ST", "CAM", "CM"])
        if not taker and team["players"]:
            taker = team["players"][0]
        if not taker:
            return

        opponent_side = "away" if side == "home" else "home"
        opponent = self._team(opponent_side)
        goalkeeper = next(
            (
                p for p in opponent["players"]
                if p["active"] and p["role"] == "GK"
            ),
            None,
        )
        if not goalkeeper and opponent["players"]:
            goalkeeper = opponent["players"][0]

        self._team_stats(side)["penalties"] += 1
        self._event(
            "penalty",
            f"PENALTY for {team['name']}!",
            side,
            taker["id"],
        )

        if not goalkeeper:
            self._goal(taker)
            return

        conversion = clamp(
            0.75
            + (taker["composure"] - 65) / 200
            - (goalkeeper["goalkeeping"] - 70) / 300,
            0.55, 0.92,
        )

        if random.random() < conversion:
            self._goal(taker)
        else:
            goalkeeper["stats"]["saves"] += 1
            self._team_stats(opponent_side)["saves"] += 1
            self._event(
                "penalty_saved",
                f"{goalkeeper['name']} SAVED the penalty!",
                opponent_side,
                goalkeeper["id"],
            )
            self._goal_kick(opponent_side)

    # ========================================================
    # CARDS
    # ========================================================

    def _yellow_card(
        self, player: Dict[str, Any], reason: str = "",
    ) -> None:
        player["yellowCards"] += 1
        player["stats"]["yellowCards"] += 1
        self._team_stats(player["side"])["yellowCards"] += 1

        self._event(
            "yellow_card",
            f"Yellow card for {player['name']}"
            + (f" ({reason})" if reason else ""),
            player["side"],
            player["id"],
        )

        if player["yellowCards"] >= 2:
            self._red_card(player, "second yellow")

    def _red_card(
        self, player: Dict[str, Any], reason: str = "",
    ) -> None:
        player["redCard"] = True
        player["suspended"] = True
        player["active"] = False
        player["stats"]["redCards"] += 1
        self._team_stats(player["side"])["redCards"] += 1

        self._event(
            "red_card",
            f"RED CARD! {player['name']} is sent off"
            + (f" ({reason})" if reason else ""),
            player["side"],
            player["id"],
        )

        # If he had the ball, give it to nearest opponent
        if self.ball["owner"] == player["id"]:
            self._lose_ball_to_opponent(player)

    # ========================================================
    # BALL LOSS
    # ========================================================

    def _lose_ball_to_opponent(
        self,
        player: Dict[str, Any],
        new_side: Optional[str] = None,
    ) -> None:
        side = new_side
        if side is None:
            side = "away" if player["side"] == "home" else "home"

        opponents = self._all_players(side)
        if not opponents:
            self._clear_ball()
            return

        closest = min(
            opponents, key=lambda p: distance(player, p),
        )
        self._give_ball(closest, side)
        self.possession_team = side

    def _choose_ball_winner(self) -> None:
        candidates: List[Tuple[float, Dict[str, Any]]] = []

        for side in ["home", "away"]:
            for player in self._all_players(side):
                candidates.append(
                    (distance(player, self.ball), player),
                )

        if not candidates:
            return

        candidates.sort(key=lambda x: x[0])
        player = candidates[0][1]

        # Only pick up if close enough
        if candidates[0][0] < 3.0:
            self._give_ball(player, player["side"])

    # ========================================================
    # RANDOM EVENTS
    # ========================================================

    def _maybe_random_event(self) -> None:
        if random.random() < 0.025:
            self._maybe_tackle()
        if random.random() < 0.010:
            self._maybe_foul()

    def _maybe_tackle(self) -> None:
        owner = self._find_ball_owner()
        if not owner:
            return

        opponent_side = "away" if owner["side"] == "home" else "home"
        defenders = self._all_players(opponent_side)
        if not defenders:
            return

        defender = min(
            defenders, key=lambda p: distance(p, owner),
        )
        d = distance(defender, owner)
        if d > 4:
            return

        tackle_probability = 0.35 + defender["defending"] / 300

        if random.random() < tackle_probability:
            defender["stats"]["tackles"] += 1
            self._team_stats(opponent_side)["tackles"] += 1
            self._give_ball(defender, opponent_side)
            self._event(
                "tackle",
                f"{defender['name']} won the ball",
                opponent_side,
                defender["id"],
            )
        else:
            owner["stats"]["fouled"] += 1

    def _maybe_foul(self) -> None:
        owner = self._find_ball_owner()
        if not owner:
            return

        opponent_side = "away" if owner["side"] == "home" else "home"
        defenders = self._all_players(opponent_side)
        if not defenders:
            return

        defender = min(
            defenders, key=lambda p: distance(p, owner),
        )
        if distance(defender, owner) > 5:
            return

        if random.random() < 0.40:
            defender["stats"]["fouls"] += 1
            self._team_stats(opponent_side)["fouls"] += 1

            in_box = is_inside_box(
                owner["x"], owner["y"], defending_side=opponent_side,
            )

            self._event(
                "foul",
                f"Foul by {defender['name']} on {owner['name']}",
                opponent_side,
                defender["id"],
            )

            # Card logic
            if in_box or random.random() < 0.15:
                self._yellow_card(defender, "tactical foul")

            if in_box and random.random() < 0.55:
                self._penalty(owner["side"])
            else:
                self._free_kick(
                    owner["side"], owner["x"], owner["y"],
                )

    # ========================================================
    # POSSESSION STATS
    # ========================================================

    def _update_possession_stats(self) -> None:
        total = (
            self.possession_time["home"]
            + self.possession_time["away"]
        )
        if total <= 0:
            return

        home_pct = (self.possession_time["home"] / total) * 100
        away_pct = 100 - home_pct

        self.stats["home"]["possession"] = round(home_pct, 1)
        self.stats["away"]["possession"] = round(away_pct, 1)
        self.stats["home"]["possessionTime"] = round(
            self.possession_time["home"], 2,
        )
        self.stats["away"]["possessionTime"] = round(
            self.possession_time["away"], 2,
        )

    # ========================================================
    # HALFTIME
    # ========================================================

    def _halftime(self) -> None:
        self.halftime_done = True
        self.status = "halftime"
        self.running = False

        self._event(
            "halftime",
            f"Half time ({self.score['home']}-{self.score['away']})",
            None,
            None,
            extra={"score": self.score.copy()},
        )

        # Reset player positions for second half
        self._reset_positions_for_second_half()

        if (
            self._halftime_thread is None
            or not self._halftime_thread.is_alive()
        ):
            self._halftime_thread = threading.Thread(
                target=self._auto_resume_after_halftime,
                daemon=True,
            )
            self._halftime_thread.start()

    def _reset_positions_for_second_half(self) -> None:
        # Swap sides: mirror everyone's position horizontally
        for side in ["home", "away"]:
            for player in self._all_players(side):
                player["x"] = PITCH_WIDTH - player["x"]
                player["y"] = PITCH_HEIGHT - player["y"]
                player["targetX"] = player["x"]
                player["targetY"] = player["y"]

        # Away kicks off second half
        away_mid = self._find_best_player(
            self.away, ["CM", "CAM", "CDM"],
        )
        if away_mid:
            self._give_ball(away_mid, "away")

    def _auto_resume_after_halftime(self) -> None:
        time.sleep(2)

        with self.lock:
            if not self.finished and self.status == "halftime":
                self.status = "playing"
                self.running = True
                self.second_half_started = True
                self.last_tick = time.time()

                self._event(
                    "second_half",
                    "Second half started",
                    None,
                    None,
                )

                # Make sure main loop thread is running
                if (
                    self._loop_thread is None
                    or not self._loop_thread.is_alive()
                ):
                    self._loop_thread = threading.Thread(
                        target=self._run_loop,
                        daemon=True,
                    )
                    self._loop_thread.start()

    # ========================================================
    # FINISH
    # ========================================================

    def _finish_match(self) -> None:
        if self.finished:
            return

        self.finished = True
        self.running = False
        self.status = "finished"

        self._clear_ball()

        self._event(
            "full_time",
            f"Full time ({self.score['home']}-{self.score['away']})",
            None,
            None,
            extra={"score": self.score.copy()},
        )

    # ========================================================
    # TACTICS / FORMATION / SUBS
    # ========================================================

    def set_tactics(
        self, side: str, tactics: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self.lock:
            team = self._team(side)
            if not isinstance(tactics, dict):
                return self.snapshot()

            team["tactics"].update(self._create_tactics(tactics))
            self._event(
                "tactics",
                f"{team['name']} changed tactics",
                side,
                None,
            )
            return self.snapshot()

    def set_formation(
        self, side: str, formation: str,
    ) -> Dict[str, Any]:
        with self.lock:
            if formation not in FORMATIONS:
                raise ValueError(f"Unsupported formation: {formation}")

            team = self._team(side)
            team["formation"] = formation

            positions = self._formation_positions(formation, side)
            roles = FORMATIONS[formation]

            for index, player in enumerate(self._all_players(side)):
                if index >= len(positions):
                    break
                player["role"] = roles[index]
                player["position"] = roles[index]
                player["targetX"] = positions[index]["x"]
                player["targetY"] = positions[index]["y"]

            self._event(
                "formation",
                f"{team['name']} changed formation to {formation}",
                side,
                None,
            )
            return self.snapshot()

    def substitute(
        self, side: str, outgoing_id: str, incoming_id: str,
    ) -> Dict[str, Any]:
        with self.lock:
            team = self._team(side)
            if team["substitutionsUsed"] >= 5:
                raise ValueError("Maximum substitutions reached")

            outgoing = self._find_player(side, outgoing_id)
            incoming = next(
                (
                    p for p in team["bench"]
                    if str(p["id"]) == str(incoming_id)
                ),
                None,
            )

            if not outgoing:
                raise ValueError("Outgoing player not found")
            if not incoming:
                raise ValueError("Incoming player not found")

            incoming["active"] = True
            incoming["isBench"] = False
            incoming["x"] = outgoing["x"]
            incoming["y"] = outgoing["y"]

            outgoing["active"] = False
            outgoing["hasBall"] = False

            team["players"] = [
                p for p in team["players"]
                if p["id"] != outgoing["id"]
            ]
            team["players"].append(incoming)

            team["bench"] = [
                p for p in team["bench"]
                if p["id"] != incoming["id"]
            ]
            team["bench"].append(outgoing)
            outgoing["isBench"] = True

            team["substitutionsUsed"] += 1

            if self.ball["owner"] == outgoing["id"]:
                self._give_ball(incoming, side)

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
    ) -> None:

        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "minute": self.minute,
            "second": self.second,
            "message": message,
            "side": side,
            "playerId": player_id,
            "timestamp": int(time.time() * 1000),
        }

        if extra:
            event.update(extra)

        self.events.append(event)
        if len(self.events) > MAX_EVENTS:
            self.events = self.events[-MAX_EVENTS:]

    # ========================================================
    # HELPERS
    # ========================================================

    def _team(self, side: str) -> Dict[str, Any]:
        return self.home if side == "home" else self.away

    def _team_stats(self, side: str) -> Dict[str, Any]:
        return self.stats["home" if side == "home" else "away"]

    # ========================================================
    # SNAPSHOT
    # ========================================================

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "ok": True,
                "matchId": self.match_id,
                "status": self.status,
                "running": self.running,
                "finished": self.finished,
                "minute": self.minute,
                "second": self.second,
                "injuryTime": {
                    "firstHalf": self.injury_time_first_half,
                    "secondHalf": self.injury_time_second_half,
                },
                "score": {
                    "home": self.score["home"],
                    "away": self.score["away"],
                },
                "ball": {
                    "x": round(self.ball["x"], 2),
                    "y": round(self.ball["y"], 2),
                    "owner": self.ball["owner"],
                    "team": self.ball["team"],
                    "state": self.ball["state"],
                },
                "home": self._serialize_team(self.home),
                "away": self._serialize_team(self.away),
                "stats": self.stats,
                "events": self.events[-MAX_EVENTS:],
                "lastEvent": (
                    self.events[-1] if self.events else None
                ),
            }

    def _serialize_team(
        self, team: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "id": team["id"],
            "name": team["name"],
            "logo": team["logo"],
            "side": team["side"],
            "formation": team["formation"],
            "tactics": team["tactics"],
            "substitutionsUsed": team["substitutionsUsed"],
            "morale": round(team["morale"], 1),
            "momentum": round(team["momentum"], 1),
            "players": [
                self._serialize_player(p) for p in team["players"]
            ],
            "bench": [
                self._serialize_player(p) for p in team["bench"]
            ],
            "stats": team["stats"],
        }

    def _serialize_player(
        self, player: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "id": player["id"],
            "name": player["name"],
            "number": player["number"],
            "position": player["position"],
            "role": player["role"],
            "side": player["side"],
            "active": player["active"],

            "pace": round(player["pace"], 1),
            "passing": round(player["passing"], 1),
            "shooting": round(player["shooting"], 1),
            "dribbling": round(player["dribbling"], 1),
            "defending": round(player["defending"], 1),
            "stamina": round(player["stamina"], 1),
            "strength": round(player["strength"], 1),
            "vision": round(player["vision"], 1),
            "composure": round(player["composure"], 1),
            "goalkeeping": round(player["goalkeeping"], 1),

            "energy": round(player["energy"], 1),
            "morale": round(player["morale"], 1),

            "x": round(player["x"], 2),
            "y": round(player["y"], 2),
            "targetX": round(player["targetX"], 2),
            "targetY": round(player["targetY"], 2),

            "hasBall": player["hasBall"],
            "action": player["action"],

            "yellowCards": player["yellowCards"],
            "redCard": player["redCard"],

            "stats": player["stats"],
        }


