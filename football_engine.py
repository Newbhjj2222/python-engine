# football_engine.py

from __future__ import annotations

import math
import random
import threading
import time
import uuid
from copy import deepcopy
from typing import Any, Optional


# ============================================================
# MATCH ENGINE CONSTANTS
# ============================================================

PITCH_WIDTH = 100.0
PITCH_HEIGHT = 60.0

MATCH_MINUTES = 90
FIRST_HALF_SECONDS = 45 * 60
FULL_MATCH_SECONDS = 90 * 60

# Real-world seconds required to simulate 90 football minutes.
# 480 seconds = 8 minutes real time.
REAL_MATCH_SECONDS = 480.0

TIME_SCALE = FULL_MATCH_SECONDS / REAL_MATCH_SECONDS

TICK_SECONDS = 0.20

MAX_EVENTS = 400
MAX_PLAYERS_PER_TEAM = 11

HALF_TIME_BREAK_SECONDS = 5.0

MIN_PASS_INTERVAL = 0.45
MIN_DRIBBLE_INTERVAL = 1.10
MIN_SHOT_INTERVAL = 4.00
MIN_ACTION_INTERVAL = 0.35

BALL_SPEED = 28.0

FORMATION_POSITIONS = {
    "4-3-3": [
        ("GK", 7, 30),
        ("LB", 20, 9),
        ("LCB", 18, 23),
        ("RCB", 18, 37),
        ("RB", 20, 51),
        ("LCM", 38, 18),
        ("CM", 36, 30),
        ("RCM", 38, 42),
        ("LW", 57, 10),
        ("ST", 65, 30),
        ("RW", 57, 50),
    ],
    "4-4-2": [
        ("GK", 7, 30),
        ("LB", 20, 9),
        ("LCB", 18, 23),
        ("RCB", 18, 37),
        ("RB", 20, 51),
        ("LM", 42, 10),
        ("LCM", 40, 23),
        ("RCM", 40, 37),
        ("RM", 42, 50),
        ("ST", 65, 25),
        ("ST", 65, 35),
    ],
    "4-2-3-1": [
        ("GK", 7, 30),
        ("LB", 20, 9),
        ("LCB", 18, 23),
        ("RCB", 18, 37),
        ("RB", 20, 51),
        ("LDM", 34, 22),
        ("RDM", 34, 38),
        ("LAM", 49, 13),
        ("CAM", 51, 30),
        ("RAM", 49, 47),
        ("ST", 67, 30),
    ],
    "3-5-2": [
        ("GK", 7, 30),
        ("LCB", 17, 20),
        ("CB", 16, 30),
        ("RCB", 17, 40),
        ("LWB", 39, 8),
        ("LCM", 38, 22),
        ("CM", 37, 30),
        ("RCM", 38, 38),
        ("RWB", 39, 52),
        ("ST", 65, 25),
        ("ST", 65, 35),
    ],
    "5-3-2": [
        ("GK", 7, 30),
        ("LWB", 22, 7),
        ("LCB", 18, 20),
        ("CB", 17, 30),
        ("RCB", 18, 40),
        ("RWB", 22, 53),
        ("LCM", 39, 21),
        ("CM", 38, 30),
        ("RCM", 39, 39),
        ("ST", 65, 25),
        ("ST", 65, 35),
    ],
}


# ============================================================
# BASIC HELPERS
# ============================================================

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def distance(a: dict[str, float], b: dict[str, float]) -> float:
    dx = safe_float(a.get("x")) - safe_float(b.get("x"))
    dy = safe_float(a.get("y")) - safe_float(b.get("y"))
    return math.sqrt(dx * dx + dy * dy)


def lerp(a: float, b: float, amount: float) -> float:
    return a + (b - a) * amount


def normalize_name(value: Any, fallback: str) -> str:
    if value is None:
        return fallback

    text = str(value).strip()

    return text if text else fallback


# ============================================================
# PLAYER
# ============================================================

class Player:
    def __init__(
        self,
        raw: Optional[dict[str, Any]],
        index: int,
        side: str,
    ):
        raw = raw or {}

        ratings = (
            raw.get("ratings")
            or raw.get("stats")
            or raw.get("attributes")
            or {}
        )

        self.id = str(
            raw.get("id")
            or raw.get("playerId")
            or raw.get("uid")
            or raw.get("_id")
            or f"{side}-player-{index + 1}"
        )

        self.name = normalize_name(
            raw.get("name")
            or raw.get("displayName")
            or raw.get("fullName")
            or raw.get("playerName"),
            f"Player {index + 1}",
        )

        self.number = safe_int(
            raw.get("number")
            or raw.get("shirtNumber")
            or raw.get("jerseyNumber"),
            index + 1,
        )

        self.position = str(
            raw.get("position")
            or raw.get("preferredPosition")
            or raw.get("role")
            or "CM"
        )

        self.role = str(
            raw.get("role")
            or raw.get("position")
            or "CM"
        )

        self.pace = safe_float(
            raw.get("pace")
            or ratings.get("pace")
            or ratings.get("speed"),
            68,
        )

        self.passing = safe_float(
            raw.get("passing")
            or ratings.get("passing")
            or ratings.get("pass"),
            68,
        )

        self.shooting = safe_float(
            raw.get("shooting")
            or ratings.get("shooting")
            or ratings.get("shoot"),
            65,
        )

        self.dribbling = safe_float(
            raw.get("dribbling")
            or ratings.get("dribbling")
            or ratings.get("dribble"),
            67,
        )

        self.defending = safe_float(
            raw.get("defending")
            or ratings.get("defending")
            or ratings.get("defence")
            or ratings.get("defense"),
            65,
        )

        self.stamina = safe_float(
            raw.get("stamina")
            or ratings.get("stamina"),
            75,
        )

        self.strength = safe_float(
            raw.get("strength")
            or ratings.get("strength")
            or ratings.get("physical"),
            70,
        )

        self.vision = safe_float(
            raw.get("vision")
            or ratings.get("vision"),
            68,
        )

        self.goalkeeping = safe_float(
            raw.get("goalkeeping")
            or ratings.get("goalkeeping")
            or ratings.get("gk"),
            65,
        )

        self.composure = safe_float(
            raw.get("composure")
            or ratings.get("composure"),
            65,
        )

        self.positioning = safe_float(
            raw.get("positioning")
            or ratings.get("positioning"),
            65,
        )

        self.acceleration = safe_float(
            raw.get("acceleration")
            or ratings.get("acceleration"),
            68,
        )

        self.aggression = safe_float(
            raw.get("aggression")
            or ratings.get("aggression"),
            60,
        )

        self.balance = safe_float(
            raw.get("balance")
            or ratings.get("balance"),
            65,
        )

        self.side = side

        self.x = 30.0
        self.y = 30.0

        self.base_x = 30.0
        self.base_y = 30.0

        self.target_x = 30.0
        self.target_y = 30.0

        self.speed = 0.0

        self.stamina_current = clamp(self.stamina, 20, 100)

        self.yellow = False
        self.red = False

        self.goals = 0
        self.assists = 0
        self.shots = 0
        self.shots_on_target = 0
        self.passes = 0
        self.passes_completed = 0
        self.tackles = 0
        self.interceptions = 0
        self.fouls = 0
        self.saves = 0

        self.last_action_at = 0.0
        self.last_pass_at = 0.0
        self.last_dribble_at = 0.0
        self.last_shot_at = 0.0
        self.last_target_update = 0.0

        self.decision_at = 0.0

        self.is_on_pitch = True

    def rating(self) -> float:
        values = [
            self.pace,
            self.passing,
            self.shooting,
            self.dribbling,
            self.defending,
            self.stamina,
            self.strength,
            self.vision,
            self.composure,
            self.positioning,
        ]

        return sum(values) / len(values)

    def effective_speed(self) -> float:
        stamina_factor = 0.70 + (self.stamina_current / 100.0) * 0.30

        return (
            2.3
            + self.pace / 100.0 * 1.5
            + self.acceleration / 100.0 * 0.8
        ) * stamina_factor

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "number": self.number,
            "position": self.position,
            "role": self.role,
            "side": self.side,

            "x": round(self.x, 2),
            "y": round(self.y, 2),

            "baseX": round(self.base_x, 2),
            "baseY": round(self.base_y, 2),

            "targetX": round(self.target_x, 2),
            "targetY": round(self.target_y, 2),

            "speed": round(self.speed, 2),

            "pace": round(self.pace, 1),
            "passing": round(self.passing, 1),
            "shooting": round(self.shooting, 1),
            "dribbling": round(self.dribbling, 1),
            "defending": round(self.defending, 1),
            "stamina": round(self.stamina_current, 1),
            "strength": round(self.strength, 1),
            "vision": round(self.vision, 1),
            "goalkeeping": round(self.goalkeeping, 1),
            "composure": round(self.composure, 1),
            "positioning": round(self.positioning, 1),
            "acceleration": round(self.acceleration, 1),
            "aggression": round(self.aggression, 1),

            "yellow": self.yellow,
            "red": self.red,

            "goals": self.goals,
            "assists": self.assists,
            "shots": self.shots,
            "shotsOnTarget": self.shots_on_target,
            "passes": self.passes,
            "passesCompleted": self.passes_completed,
            "tackles": self.tackles,
            "interceptions": self.interceptions,
            "fouls": self.fouls,
            "saves": self.saves,

            "isOnPitch": self.is_on_pitch,
        }


# ============================================================
# TEAM
# ============================================================

class Team:
    def __init__(
        self,
        raw: Optional[dict[str, Any]],
        side: str,
        fallback_name: str,
    ):
        raw = raw or {}

        self.side = side

        self.id = str(
            raw.get("id")
            or raw.get("clubId")
            or raw.get("teamId")
            or side
        )

        self.name = normalize_name(
            raw.get("name")
            or raw.get("clubName")
            or raw.get("teamName"),
            fallback_name,
        )

        self.logo = (
            raw.get("logo")
            or raw.get("logoUrl")
            or raw.get("imageUrl")
            or raw.get("image")
            or ""
        )

        self.formation = str(
            raw.get("formation")
            or "4-3-3"
        )

        if self.formation not in FORMATION_POSITIONS:
            self.formation = "4-3-3"

        raw_tactics = raw.get("tactics") or {}

        self.tactics = {
            "mentality": str(
                raw_tactics.get("mentality")
                or "balanced"
            ),
            "tempo": clamp(
                safe_float(raw_tactics.get("tempo"), 60),
                0,
                100,
            ),
            "pressing": str(
                raw_tactics.get("pressing")
                or "medium"
            ),
            "defensiveLine": str(
                raw_tactics.get("defensiveLine")
                or "medium"
            ),
            "width": clamp(
                safe_float(raw_tactics.get("width"), 55),
                0,
                100,
            ),
        }

        raw_players = raw.get("players")

        if not isinstance(raw_players, list):
            raw_players = (
                raw.get("lineup")
                if isinstance(raw.get("lineup"), list)
                else raw.get("squad")
                if isinstance(raw.get("squad"), list)
                else []
            )

        raw_bench = raw.get("bench")

        if not isinstance(raw_bench, list):
            raw_bench = (
                raw.get("substitutes")
                if isinstance(raw.get("substitutes"), list)
                else []
            )

        self.players: list[Player] = []

        for index, raw_player in enumerate(raw_players[:11]):
            self.players.append(
                Player(
                    raw_player,
                    index,
                    side,
                )
            )

        # Fallback players prevent a malformed database record
        # from crashing the entire match.
        while len(self.players) < 11:
            index = len(self.players)

            self.players.append(
                Player(
                    {
                        "id": f"{side}-fallback-{index + 1}",
                        "name": f"{fallback_name} Player {index + 1}",
                        "number": index + 1,
                        "position": "GK" if index == 0 else "CM",
                    },
                    index,
                    side,
                )
            )

        self.bench: list[Player] = []

        for index, raw_player in enumerate(raw_bench):
            self.bench.append(
                Player(
                    raw_player,
                    index + 11,
                    side,
                )
            )

        self.substitutions_used = safe_int(
            raw.get("substitutionsUsed"),
            0,
        )

        raw_stats = raw.get("stats")

        self.stats = {
            "shots": safe_int(
                (raw_stats or {}).get("shots"),
                0,
            ),
            "shotsOnTarget": safe_int(
                (raw_stats or {}).get("shotsOnTarget"),
                0,
            ),
            "passes": safe_int(
                (raw_stats or {}).get("passes"),
                0,
            ),
            "passesCompleted": safe_int(
                (raw_stats or {}).get("passesCompleted"),
                0,
            ),
            "tackles": safe_int(
                (raw_stats or {}).get("tackles"),
                0,
            ),
            "corners": safe_int(
                (raw_stats or {}).get("corners"),
                0,
            ),
            "fouls": safe_int(
                (raw_stats or {}).get("fouls"),
                0,
            ),
            "yellowCards": safe_int(
                (raw_stats or {}).get("yellowCards"),
                0,
            ),
            "redCards": safe_int(
                (raw_stats or {}).get("redCards"),
                0,
            ),
            "offsides": safe_int(
                (raw_stats or {}).get("offsides"),
                0,
            ),
        }

    def on_pitch(self) -> list[Player]:
        return [
            player
            for player in self.players
            if player.is_on_pitch and not player.red
        ]

    def goalkeeper(self) -> Player:
        for player in self.on_pitch():
            if player.position.upper() in {
                "GK",
                "G",
                "GOALKEEPER",
            }:
                return player

        return self.on_pitch()[0]

    def strength(self) -> float:
        players = self.on_pitch()

        if not players:
            return 50.0

        return sum(player.rating() for player in players) / len(players)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "logo": self.logo,
            "formation": self.formation,
            "tactics": deepcopy(self.tactics),

            "players": [
                player.to_dict()
                for player in self.players
                if player.is_on_pitch
            ],

            "bench": [
                player.to_dict()
                for player in self.bench
                if not player.is_on_pitch
            ],

            "substitutionsUsed": self.substitutions_used,

            "stats": deepcopy(self.stats),
        }


# ============================================================
# BALL
# ============================================================

class Ball:
    def __init__(self):
        self.x = 50.0
        self.y = 30.0

        self.target_x = 50.0
        self.target_y = 30.0

        self.vx = 0.0
        self.vy = 0.0

        self.owner_id: Optional[str] = None
        self.owner_side: Optional[str] = None

        self.state = "owned"

        self.last_touch_side: Optional[str] = None
        self.last_touch_player: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": round(self.x, 2),
            "y": round(self.y, 2),

            "targetX": round(self.target_x, 2),
            "targetY": round(self.target_y, 2),

            "vx": round(self.vx, 2),
            "vy": round(self.vy, 2),

            "ownerId": self.owner_id,
            "ownerSide": self.owner_side,

            "state": self.state,

            "lastTouchSide": self.last_touch_side,
            "lastTouchPlayer": self.last_touch_player,
        }


# ============================================================
# FOOTBALL MATCH
# ============================================================

class FootballMatch:

    def __init__(self, config: dict[str, Any]):
        self.lock = threading.RLock()

        self.config = config or {}

        self.match_id = str(
            self.config.get("matchId")
            or self.config.get("id")
            or uuid.uuid4()
        )

        self.status = "created"

        self.running = False
        self.finished = False
        self.destroyed = False

        self.half = 1

        self.football_seconds = 0.0

        self.first_half_injury = random.randint(1, 3)
        self.second_half_injury = random.randint(2, 4)

        self.halftime_until: Optional[float] = None

        self.score = {
            "home": 0,
            "away": 0,
        }

        self.home = Team(
            self.config.get("home")
            or self.config.get("homeTeam")
            or {},
            "home",
            "Home Team",
        )

        self.away = Team(
            self.config.get("away")
            or self.config.get("awayTeam")
            or {},
            "away",
            "Away Team",
        )

        self.ball = Ball()

        self.possession_side = random.choice(
            ["home", "away"]
        )

        self.events: list[dict[str, Any]] = []

        self.last_event: Optional[dict[str, Any]] = None

        self.created_at = time.time()

        self.last_tick = time.monotonic()

        self.last_decision = time.monotonic()

        self.next_action_at = time.monotonic() + 0.5

        self.thread: Optional[threading.Thread] = None

        self.stop_event = threading.Event()

        self.result: Optional[dict[str, Any]] = None

        self.stats = {
            "possession": {
                "home": 50.0,
                "away": 50.0,
            },

            "shots": {
                "home": 0,
                "away": 0,
            },

            "shotsOnTarget": {
                "home": 0,
                "away": 0,
            },

            "passes": {
                "home": 0,
                "away": 0,
            },

            "passesCompleted": {
                "home": 0,
                "away": 0,
            },

            "tackles": {
                "home": 0,
                "away": 0,
            },

            "corners": {
                "home": 0,
                "away": 0,
            },

            "fouls": {
                "home": 0,
                "away": 0,
            },

            "yellowCards": {
                "home": 0,
                "away": 0,
            },

            "redCards": {
                "home": 0,
                "away": 0,
            },

            "offsides": {
                "home": 0,
                "away": 0,
            },
        }

        self._setup_positions()

        self._assign_initial_ball()

    # ========================================================
    # EVENT SYSTEM
    # ========================================================

    def _event(
        self,
        event_type: str,
        team: Optional[str] = None,
        player: Optional[str] = None,
        minute: Optional[int] = None,
        second: Optional[int] = None,
        **extra: Any,
    ) -> dict[str, Any]:

        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "team": team,
            "player": player,
            "minute": (
                minute
                if minute is not None
                else self.minute()
            ),
            "second": (
                second
                if second is not None
                else self.second()
            ),
            "timestamp": time.time(),
        }

        event.update(extra)

        self.events.append(event)

        if len(self.events) > MAX_EVENTS:
            self.events = self.events[-MAX_EVENTS:]

        self.last_event = event

        return event

    # Compatibility method in case another part of the engine
    # calls event() directly.
    def event(
        self,
        event_type: str,
        team: Optional[str] = None,
        player: Optional[str] = None,
        **extra: Any,
    ):
        return self._event(
            event_type,
            team=team,
            player=player,
            **extra,
        )

    # ========================================================
    # TEAM HELPERS
    # ========================================================

    def _team(self, side: str) -> Team:
        return self.home if side == "home" else self.away

    def _other_side(self, side: str) -> str:
        return "away" if side == "home" else "home"

    def _all_players(self) -> list[Player]:
        return self.home.on_pitch() + self.away.on_pitch()

    def _find_player(
        self,
        player_id: Optional[str],
    ) -> Optional[Player]:

        if not player_id:
            return None

        for player in self.home.players + self.home.bench:
            if player.id == str(player_id):
                return player

        for player in self.away.players + self.away.bench:
            if player.id == str(player_id):
                return player

        return None

    # ========================================================
    # FORMATIONS
    # ========================================================

    def _setup_positions(self):
        self._apply_positions(self.home, attacking_to_right=True)
        self._apply_positions(self.away, attacking_to_right=False)

    def _apply_positions(
        self,
        team: Team,
        attacking_to_right: bool,
    ):
        positions = FORMATION_POSITIONS.get(
            team.formation,
            FORMATION_POSITIONS["4-3-3"],
        )

        width_factor = (
            0.80
            + team.tactics["width"] / 100.0 * 0.40
        )

        for index, player in enumerate(team.on_pitch()):

            if index >= len(positions):
                break

            role, raw_x, raw_y = positions[index]

            player.position = role
            player.role = role

            x = float(raw_x)
            y = 30.0 + (
                float(raw_y) - 30.0
            ) * width_factor

            if not attacking_to_right:
                x = 100.0 - x

            player.base_x = clamp(x, 4, 96)
            player.base_y = clamp(y, 3, 57)

            player.x = player.base_x
            player.y = player.base_y

            player.target_x = player.x
            player.target_y = player.y

    # ========================================================
    # BALL
    # ========================================================

    def _assign_initial_ball(self):
        team = self._team(self.possession_side)

        players = team.on_pitch()

        if not players:
            return

        midfielders = [
            player
            for player in players
            if player.position.upper()
            not in {"GK", "G"}
        ]

        player = (
            random.choice(midfielders)
            if midfielders
            else players[0]
        )

        self._give_ball_to(player)

    def _give_ball_to(self, player: Player):
        self.ball.owner_id = player.id
        self.ball.owner_side = player.side

        self.ball.state = "owned"

        self.ball.x = player.x
        self.ball.y = player.y

        self.ball.vx = 0.0
        self.ball.vy = 0.0

        self.ball.last_touch_side = player.side
        self.ball.last_touch_player = player.id

        self.possession_side = player.side

    # ========================================================
    # CLOCK
    # ========================================================

    def minute(self) -> int:
        return int(self.football_seconds // 60)

    def second(self) -> int:
        return int(self.football_seconds % 60)

    def clock_string(self) -> str:
        minute = self.minute()
        second = self.second()

        return f"{minute:02d}:{second:02d}"

    def _current_limit(self) -> float:
        if self.half == 1:
            return FIRST_HALF_SECONDS + (
                self.first_half_injury * 60
            )

        return FULL_MATCH_SECONDS + (
            self.second_half_injury * 60
        )

    # ========================================================
    # START / PAUSE / FINISH
    # ========================================================

    def start(self):
        with self.lock:

            if self.finished:
                return self.snapshot()

            if self.status == "halftime":
                self.half = 2

                self.football_seconds = FIRST_HALF_SECONDS

                self.status = "playing"

                self.running = True

                self.halftime_until = None

                self.last_tick = time.monotonic()

                self._event(
                    "second_half_start",
                )

            elif self.status != "playing":
                self.status = "playing"

                self.running = True

                self.last_tick = time.monotonic()

                if self.football_seconds <= 0:
                    self._event(
                        "match_start",
                    )

            self._ensure_thread()

            return self.snapshot()

    def pause(self):
        with self.lock:

            if not self.finished:
                self.running = False

                if self.status == "playing":
                    self.status = "paused"

            return self.snapshot()

    def finish(self):
        with self.lock:

            if self.finished:
                return self.snapshot()

            self.football_seconds = FULL_MATCH_SECONDS

            self.running = False
            self.finished = True
            self.status = "finished"

            self._event(
                "full_time",
            )

            self.result = {
                "home": self.score["home"],
                "away": self.score["away"],
                "winner": (
                    "home"
                    if self.score["home"] > self.score["away"]
                    else "away"
                    if self.score["away"] > self.score["home"]
                    else "draw"
                ),
            }

            return self.snapshot()

    # ========================================================
    # THREAD
    # ========================================================

    def _ensure_thread(self):

        if (
            self.thread
            and self.thread.is_alive()
        ):
            return

        self.stop_event.clear()

        self.thread = threading.Thread(
            target=self._simulation_loop,
            daemon=True,
        )

        self.thread.start()

    def _simulation_loop(self):

        while not self.stop_event.is_set():

            try:
                with self.lock:

                    if self.destroyed:
                        break

                    now = time.monotonic()

                    dt = now - self.last_tick

                    self.last_tick = now

                    dt = clamp(
                        dt,
                        0.01,
                        0.50,
                    )

                    if self.running and not self.finished:
                        self._tick(dt)

                time.sleep(TICK_SECONDS)

            except Exception as exc:
                # Never let one simulation error kill the thread.
                # Log it into the match event stream instead.
                try:
                    with self.lock:
                        self._event(
                            "engine_error",
                            message=str(exc),
                        )
                except Exception:
                    pass

                time.sleep(0.5)

    # ========================================================
    # MAIN TICK
    # ========================================================

    def _tick(self, dt: float):

        if self.status != "playing":
            return

        # Advance football clock.
        self.football_seconds += (
            dt * TIME_SCALE
        )

        self._update_stamina(dt)

        self._update_player_targets()

        self._move_players(dt)

        self._update_ball(dt)

        self._update_possession()

        self._make_decisions()

        self._check_half_time_or_full_time()

    # ========================================================
    # HALFTIME / FULLTIME
    # ========================================================

    def _check_half_time_or_full_time(self):

        if (
            self.half == 1
            and self.football_seconds
            >= self._current_limit()
        ):
            self.football_seconds = self._current_limit()

            self.running = False

            self.status = "halftime"

            self.halftime_until = (
                time.monotonic()
                + HALF_TIME_BREAK_SECONDS
            )

            self._event(
                "half_time",
            )

            self._schedule_second_half()

            return

        if (
            self.half == 2
            and self.football_seconds
            >= self._current_limit()
        ):
            self.football_seconds = self._current_limit()

            self.running = False

            self.finished = True

            self.status = "finished"

            self._event(
                "full_time",
            )

            self.result = {
                "home": self.score["home"],
                "away": self.score["away"],
                "winner": (
                    "home"
                    if self.score["home"] > self.score["away"]
                    else "away"
                    if self.score["away"] > self.score["home"]
                    else "draw"
                ),
            }

    def _schedule_second_half(self):

        def resume():

            time.sleep(HALF_TIME_BREAK_SECONDS)

            with self.lock:

                if (
                    self.destroyed
                    or self.finished
                ):
                    return

                if self.status != "halftime":
                    return

                self.half = 2

                self.football_seconds = (
                    FIRST_HALF_SECONDS
                )

                self.status = "playing"

                self.running = True

                self.halftime_until = None

                self.last_tick = time.monotonic()

                self._event(
                    "second_half_start",
                )

        threading.Thread(
            target=resume,
            daemon=True,
        ).start()

    # ========================================================
    # STAMINA
    # ========================================================

    def _update_stamina(self, dt: float):

        for player in self._all_players():

            exertion = (
                0.004
                + player.speed * 0.0008
            )

            if player.side == self.possession_side:
                exertion += 0.0005

            player.stamina_current = clamp(
                player.stamina_current
                - exertion * dt * TIME_SCALE,
                20,
                100,
            )

    # ========================================================
    # PLAYER TARGETS
    # ========================================================

    def _update_player_targets(self):

        now = time.monotonic()

        ball_x = self.ball.x
        ball_y = self.ball.y

        for player in self._all_players():

            if (
                now - player.last_target_update
                < 0.8
            ):
                continue

            player.last_target_update = now

            side_sign = (
                1
                if player.side == "home"
                else -1
            )

            tactical_x = player.base_x

            tactical_y = player.base_y

            # Move team shape toward the ball.
            ball_pull = 0.08

            tactical_x = lerp(
                tactical_x,
                ball_x,
                ball_pull,
            )

            tactical_y = lerp(
                tactical_y,
                ball_y,
                ball_pull,
            )

            role = player.position.upper()

            # Goalkeepers stay close to their box.
            if role in {"GK", "G"}:

                tactical_x = (
                    6.0
                    if player.side == "home"
                    else 94.0
                )

                tactical_y = clamp(
                    30
                    + (ball_y - 30) * 0.30,
                    14,
                    46,
                )

            # Defenders react more conservatively.
            elif (
                "CB" in role
                or role in {
                    "LB",
                    "RB",
                    "LWB",
                    "RWB",
                }
            ):

                tactical_x += side_sign * (
                    5.0
                    if ball_x > 50
                    else -2.0
                )

            # Strikers make forward runs.
            elif role in {"ST", "CF"}:

                tactical_x += side_sign * 5.0

                if (
                    random.random()
                    < 0.20
                ):
                    tactical_y += random.uniform(
                        -5,
                        5,
                    )

            # Wide players stretch the pitch.
            elif role in {
                "LW",
                "RW",
                "LM",
                "RM",
                "LWB",
                "RWB",
            }:

                tactical_y += (
                    -side_sign
                    if player.y > 30
                    else side_sign
                ) * random.uniform(
                    0,
                    2.5,
                )

            # Pressing teams push toward the ball.
            pressing = (
                self._team(player.side)
                .tactics
                .get("pressing", "medium")
            )

            if pressing == "high":
                tactical_x = lerp(
                    tactical_x,
                    ball_x,
                    0.12,
                )

            elif pressing == "low":
                own_goal_x = (
                    10
                    if player.side == "home"
                    else 90
                )

                tactical_x = lerp(
                    tactical_x,
                    own_goal_x,
                    0.08,
                )

            # Small natural variation.
            tactical_y += random.uniform(
                -1.5,
                1.5,
            )

            player.target_x = clamp(
                tactical_x,
                3,
                97,
            )

            player.target_y = clamp(
                tactical_y,
                2,
                58,
            )

    # ========================================================
    # MOVEMENT
    # ========================================================

    def _move_players(self, dt: float):

        ball_owner = self._find_player(
            self.ball.owner_id
        )

        for player in self._all_players():

            dx = player.target_x - player.x
            dy = player.target_y - player.y

            dist = math.sqrt(
                dx * dx + dy * dy
            )

            if dist < 0.05:
                player.speed = 0.0
                continue

            speed = player.effective_speed()

            # Ball carrier moves more slowly while controlling.
            if (
                ball_owner
                and ball_owner.id == player.id
            ):
                speed *= 0.70

            max_move = (
                speed * dt
            )

            ratio = min(
                1.0,
                max_move / max(dist, 0.001),
            )

            old_x = player.x
            old_y = player.y

            player.x += dx * ratio
            player.y += dy * ratio

            player.x = clamp(
                player.x,
                2,
                98,
            )

            player.y = clamp(
                player.y,
                2,
                58,
            )

            moved = math.sqrt(
                (player.x - old_x) ** 2
                + (player.y - old_y) ** 2
            )

            player.speed = (
                moved / max(dt, 0.001)
            )

            # If player owns the ball, keep it attached.
            if (
                self.ball.owner_id
                == player.id
                and self.ball.state == "owned"
            ):
                self.ball.x = player.x
                self.ball.y = player.y

    # ========================================================
    # BALL PHYSICS
    # ========================================================

    def _update_ball(self, dt: float):

        if self.ball.state == "owned":

            owner = self._find_player(
                self.ball.owner_id
            )

            if owner:
                self.ball.x = owner.x
                self.ball.y = owner.y

            return

        self.ball.x += (
            self.ball.vx * dt
        )

        self.ball.y += (
            self.ball.vy * dt
        )

        # Natural ball friction.
        self.ball.vx *= 0.985
        self.ball.vy *= 0.985

        if abs(self.ball.vx) < 0.20:
            self.ball.vx = 0

        if abs(self.ball.vy) < 0.20:
            self.ball.vy = 0

        # Goal line.
        if (
            self.ball.x <= 0
            or self.ball.x >= 100
        ):
            self._handle_goal_line()

            return

        # Touchline.
        if (
            self.ball.y <= 0
            or self.ball.y >= 60
        ):
            self._handle_touchline()

            return

        # Loose ball can be collected.
        if self.ball.state == "loose":

            nearest = self._nearest_player(
                self.ball.x,
                self.ball.y,
                max_distance=4.5,
            )

            if nearest:

                self._give_ball_to(
                    nearest
                )

    def _handle_goal_line(self):

        x = self.ball.x

        attacking_side = (
            self.ball.last_touch_side
        )

        if attacking_side is None:
            self._reset_ball()

            return

        defending_side = self._other_side(
            attacking_side
        )

        goal = (
            x >= 100
            if attacking_side == "home"
            else x <= 0
        )

        if goal:
            self._goal(
                attacking_side
            )

            return

        # Ball crossed the wrong side.
        self._reset_ball()

    def _handle_touchline(self):

        last_side = self.ball.last_touch_side

        if last_side is None:
            self._reset_ball()

            return

        throw_side = self._other_side(
            last_side
        )

        self.ball.y = (
            1
            if self.ball.y <= 0
            else 59
        )

        self._event(
            "throw_in",
            team=throw_side,
        )

        player = self._nearest_player(
            self.ball.x,
            self.ball.y,
            side=throw_side,
            max_distance=15,
        )

        if player:
            self._give_ball_to(player)
        else:
            self._reset_ball()

    def _reset_ball(self):

        self.ball.state = "owned"

        self.ball.vx = 0
        self.ball.vy = 0

        team = self._team(
            self.possession_side
        )

        players = team.on_pitch()

        if players:
            player = min(
                players,
                key=lambda p: distance(
                    {
                        "x": p.x,
                        "y": p.y,
                    },
                    {
                        "x": self.ball.x,
                        "y": self.ball.y,
                    },
                ),
            )

            self._give_ball_to(player)

    # ========================================================
    # POSSESSION
    # ========================================================

    def _update_possession(self):

        home_strength = (
            self.home.strength()
        )

        away_strength = (
            self.away.strength()
        )

        total = max(
            1,
            home_strength + away_strength,
        )

        home_base = (
            home_strength / total
        )

        # Small tactical adjustment.
        home_tempo = (
            self.home.tactics["tempo"]
        )

        away_tempo = (
            self.away.tactics["tempo"]
        )

        home_bias = (
            home_tempo - away_tempo
        ) * 0.0005

        home_target = clamp(
            home_base + home_bias,
            0.30,
            0.70,
        )

        current = self.stats[
            "possession"
        ]["home"]

        current = lerp(
            current,
            home_target * 100,
            0.003,
        )

        self.stats[
            "possession"
        ]["home"] = round(
            current,
            2,
        )

        self.stats[
            "possession"
        ]["away"] = round(
            100 - current,
            2,
        )

    # ========================================================
    # DECISIONS
    # ========================================================

    def _make_decisions(self):

        now = time.monotonic()

        if now < self.next_action_at:
            return

        self.next_action_at = (
            now
            + random.uniform(
                0.25,
                0.75,
            )
        )

        owner = self._find_player(
            self.ball.owner_id
        )

        if not owner:
            return

        if owner.red:
            return

        self._decide_for_ball_carrier(
            owner
        )

    def _decide_for_ball_carrier(
        self,
        player: Player,
    ):

        now = time.monotonic()

        if (
            now - player.last_action_at
            < MIN_ACTION_INTERVAL
        ):
            return

        player.last_action_at = now

        goal_distance = (
            self._distance_to_opponent_goal(
                player
            )
        )

        nearby_defender = self._nearest_opponent(
            player,
            max_distance=8,
        )

        # Shooting is only considered in dangerous areas.
        if goal_distance < 30:

            shot_chance = (
                0.10
                + player.shooting / 1000
                + player.composure / 1500
            )

            if nearby_defender:
                shot_chance *= 0.72

            if random.random() < shot_chance:

                if (
                    now - player.last_shot_at
                    >= MIN_SHOT_INTERVAL
                ):
                    self._shoot(player)

                    return

        # Pass.
        if (
            now - player.last_pass_at
            >= MIN_PASS_INTERVAL
        ):

            pass_probability = (
                0.58
                + player.vision / 400
                + player.passing / 500
            )

            if nearby_defender:
                pass_probability += 0.08

            if random.random() < clamp(
                pass_probability,
                0.45,
                0.88,
            ):

                if self._attempt_pass(player):
                    return

        # Dribble.
        if (
            now - player.last_dribble_at
            >= MIN_DRIBBLE_INTERVAL
        ):

            if random.random() < 0.32:
                self._attempt_dribble(
                    player
                )

    # ========================================================
    # PASSING
    # ========================================================

    def _attempt_pass(
        self,
        player: Player,
    ) -> bool:

        teammates = [
            teammate
            for teammate in self._team(
                player.side
            ).on_pitch()
            if teammate.id != player.id
        ]

        if not teammates:
            return False

        candidates = []

        for teammate in teammates:

            d = distance(
                {
                    "x": player.x,
                    "y": player.y,
                },
                {
                    "x": teammate.x,
                    "y": teammate.y,
                },
            )

            if 4 <= d <= 30:
                candidates.append(
                    (
                        teammate,
                        d,
                    )
                )

        if not candidates:
            return False

        candidates.sort(
            key=lambda item: (
                self._pass_score(
                    player,
                    item[0],
                )
                - item[1] * 0.05
            ),
            reverse=True,
        )

        receiver = candidates[0][0]

        pass_quality = (
            0.62
            + player.passing / 220
            + player.vision / 350
        )

        defender = self._nearest_opponent(
            player,
            max_distance=10,
        )

        if defender:
            pass_quality -= (
                defender.defending / 400
            )

        pass_quality = clamp(
            pass_quality,
            0.45,
            0.96,
        )

        self.stats[
            "passes"
        ][player.side] += 1

        self._team(
            player.side
        ).stats["passes"] += 1

        player.passes += 1

        player.last_pass_at = (
            time.monotonic()
        )

        if random.random() <= pass_quality:

            self.stats[
                "passesCompleted"
            ][player.side] += 1

            self._team(
                player.side
            ).stats[
                "passesCompleted"
            ] += 1

            player.passes_completed += 1

            self.ball.owner_id = receiver.id
            self.ball.owner_side = receiver.side

            self.ball.last_touch_side = receiver.side
            self.ball.last_touch_player = receiver.id

            self.ball.state = "owned"

            self.ball.x = receiver.x
            self.ball.y = receiver.y

            self.possession_side = receiver.side

            self._event(
                "pass",
                team=player.side,
                player=player.id,
                receiver=receiver.id,
                completed=True,
            )

            return True

        # Failed pass.
        self.ball.owner_id = None
        self.ball.owner_side = None

        self.ball.state = "loose"

        self.ball.x = player.x
        self.ball.y = player.y

        direction = (
            1
            if receiver.x > player.x
            else -1
        )

        angle = math.atan2(
            receiver.y - player.y,
            receiver.x - player.x,
        )

        self.ball.vx = (
            math.cos(angle)
            * BALL_SPEED
            * 0.55
            * direction
            if direction < 0
            else math.cos(angle)
            * BALL_SPEED
            * 0.55
        )

        self.ball.vy = (
            math.sin(angle)
            * BALL_SPEED
            * 0.55
        )

        self.ball.last_touch_side = (
            player.side
        )

        self.ball.last_touch_player = (
            player.id
        )

        self._event(
            "pass",
            team=player.side,
            player=player.id,
            receiver=receiver.id,
            completed=False,
        )

        return True

    def _pass_score(
        self,
        passer: Player,
        receiver: Player,
    ) -> float:

        forward = (
            receiver.x - passer.x
        )

        if passer.side == "away":
            forward *= -1

        centrality = (
            1
            - abs(receiver.y - 30)
            / 30
        )

        return (
            forward * 0.08
            + centrality * 3
            + receiver.vision * 0.01
        )

    # ========================================================
    # DRIBBLING
    # ========================================================

    def _attempt_dribble(
        self,
        player: Player,
    ):

        player.last_dribble_at = (
            time.monotonic()
        )

        defender = self._nearest_opponent(
            player,
            max_distance=7,
        )

        if not defender:

            direction = (
                1
                if player.side == "home"
                else -1
            )

            player.target_x = clamp(
                player.x
                + direction * random.uniform(
                    3,
                    7,
                ),
                3,
                97,
            )

            self._event(
                "dribble",
                team=player.side,
                player=player.id,
                successful=True,
            )

            return

        attacker_power = (
            player.dribbling
            + player.balance * 0.30
            + player.acceleration * 0.25
        )

        defender_power = (
            defender.defending
            + defender.strength * 0.20
            + defender.aggression * 0.15
        )

        chance = clamp(
            0.50
            + (
                attacker_power
                - defender_power
            ) / 180,
            0.22,
            0.82,
        )

        if random.random() < chance:

            direction = (
                1
                if player.side == "home"
                else -1
            )

            player.target_x = clamp(
                player.x
                + direction * random.uniform(
                    3,
                    6,
                ),
                3,
                97,
            )

            self._event(
                "dribble",
                team=player.side,
                player=player.id,
                opponent=defender.id,
                successful=True,
            )

        else:

            defender.tackles += 1

            self.stats[
                "tackles"
            ][defender.side] += 1

            self._team(
                defender.side
            ).stats["tackles"] += 1

            self._event(
                "tackle",
                team=defender.side,
                player=defender.id,
                opponent=player.id,
            )

            self._give_ball_to(
                defender
            )

    # ========================================================
    # SHOOTING
    # ========================================================

    def _shoot(
        self,
        player: Player,
    ):

        player.last_shot_at = (
            time.monotonic()
        )

        player.shots += 1

        self.stats[
            "shots"
        ][player.side] += 1

        self._team(
            player.side
        ).stats["shots"] += 1

        goal_distance = (
            self._distance_to_opponent_goal(
                player
            )
        )

        angle_quality = (
            1
            - abs(player.y - 30)
