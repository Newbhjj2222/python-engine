# football_engine.py
"""
Advanced football match simulation engine.

Ibirimo:
- Abakinnyi bahagarara mu mwanya wabo hakurikijwe formation
- Ball carrier arunning n'umupira (agenda yihuta ari kw'umupira)
- Abakinnyi batari kw'umupira bakora runs bashaka space yo kwakira pass
- Defending: pressing, marking, tracking back
- Injuries (bikorwa n'igihe, cyangwa ku tackle ikaze)
- Substitutions nziza (harimo no gusimbuza abakomeretse)
- Formation & tactics change mid-match
- Ball physics, stamina, shooting, passing, dribbling birealistic
"""

from __future__ import annotations

import math
import random
import threading
import time
import uuid
from copy import deepcopy
from typing import Any, Optional


# ============================================================
# CONSTANTS
# ============================================================

PITCH_WIDTH = 100.0
PITCH_HEIGHT = 60.0

MATCH_MINUTES = 90
FIRST_HALF_SECONDS = 45 * 60
FULL_MATCH_SECONDS = 90 * 60

REAL_MATCH_SECONDS = 480.0
TIME_SCALE = FULL_MATCH_SECONDS / REAL_MATCH_SECONDS

TICK_SECONDS = 0.20
MAX_EVENTS = 500
MAX_PLAYERS_PER_TEAM = 11
HALF_TIME_BREAK_SECONDS = 5.0

MIN_PASS_INTERVAL = 0.40
MIN_DRIBBLE_INTERVAL = 1.00
MIN_SHOT_INTERVAL = 3.50
MIN_ACTION_INTERVAL = 0.32

BALL_SPEED = 26.0
BALL_FRICTION = 0.978

# Pitch dimensions used internally.
# x: 0 (home goal) → 100 (away goal)
# y: 0 → 60
FORMATION_POSITIONS = {
    "4-3-3": [
        ("GK", 6, 30),
        ("LB", 20, 8),
        ("LCB", 17, 22),
        ("RCB", 17, 38),
        ("RB", 20, 52),
        ("LCM", 40, 16),
        ("CM", 38, 30),
        ("RCM", 40, 44),
        ("LW", 62, 10),
        ("ST", 72, 30),
        ("RW", 62, 50),
    ],
    "4-4-2": [
        ("GK", 6, 30),
        ("LB", 20, 8),
        ("LCB", 17, 22),
        ("RCB", 17, 38),
        ("RB", 20, 52),
        ("LM", 44, 10),
        ("LCM", 41, 23),
        ("RCM", 41, 37),
        ("RM", 44, 50),
        ("ST", 70, 24),
        ("ST", 70, 36),
    ],
    "4-2-3-1": [
        ("GK", 6, 30),
        ("LB", 20, 8),
        ("LCB", 17, 22),
        ("RCB", 17, 38),
        ("RB", 20, 52),
        ("LDM", 36, 22),
        ("RDM", 36, 38),
        ("LAM", 54, 12),
        ("CAM", 58, 30),
        ("RAM", 54, 48),
        ("ST", 74, 30),
    ],
    "3-5-2": [
        ("GK", 6, 30),
        ("LCB", 16, 20),
        ("CB", 15, 30),
        ("RCB", 16, 40),
        ("LWB", 40, 6),
        ("LCM", 39, 22),
        ("CM", 38, 30),
        ("RCM", 39, 38),
        ("RWB", 40, 54),
        ("ST", 70, 25),
        ("ST", 70, 35),
    ],
    "5-3-2": [
        ("GK", 6, 30),
        ("LWB", 22, 6),
        ("LCB", 17, 19),
        ("CB", 15, 30),
        ("RCB", 17, 41),
        ("RWB", 22, 54),
        ("LCM", 40, 21),
        ("CM", 39, 30),
        ("RCM", 40, 39),
        ("ST", 70, 25),
        ("ST", 70, 35),
    ],
}


# ============================================================
# HELPERS
# ============================================================

def clamp(value, low, high):
    return max(low, min(high, value))


def safe_float(value, default=0.0):
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def distance(a, b):
    dx = safe_float(a.get("x")) - safe_float(b.get("x"))
    dy = safe_float(a.get("y")) - safe_float(b.get("y"))
    return math.sqrt(dx * dx + dy * dy)


def lerp(a, b, amount):
    return a + (b - a) * amount


def normalize_name(value, fallback):
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def point_to_segment_distance(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx = x1 + t * dx
    cy = y1 + t * dy
    return math.sqrt((px - cx) ** 2 + (py - cy) ** 2)


# ============================================================
# PLAYER
# ============================================================

class Player:
    def __init__(self, raw, index, side):
        raw = raw or {}
        ratings = raw.get("ratings") or raw.get("stats") or raw.get("attributes") or {}

        self.id = str(
            raw.get("id") or raw.get("playerId") or raw.get("uid") or raw.get("_id")
            or f"{side}-player-{index + 1}"
        )
        self.name = normalize_name(
            raw.get("name") or raw.get("displayName") or raw.get("fullName") or raw.get("playerName"),
            f"Player {index + 1}",
        )
        self.number = safe_int(
            raw.get("number") or raw.get("shirtNumber") or raw.get("jerseyNumber"),
            index + 1,
        )
        self.position = str(
            raw.get("position") or raw.get("preferredPosition") or raw.get("role") or "CM"
        ).upper()
        self.role = str(raw.get("role") or raw.get("position") or "CM").upper()

        self.pace = safe_float(raw.get("pace") or ratings.get("pace") or ratings.get("speed"), 68)
        self.passing = safe_float(raw.get("passing") or ratings.get("passing") or ratings.get("pass"), 68)
        self.shooting = safe_float(raw.get("shooting") or ratings.get("shooting") or ratings.get("shoot"), 65)
        self.dribbling = safe_float(raw.get("dribbling") or ratings.get("dribbling") or ratings.get("dribble"), 67)
        self.defending = safe_float(
            raw.get("defending") or ratings.get("defending") or ratings.get("defence") or ratings.get("defense"),
            65,
        )
        self.stamina = safe_float(raw.get("stamina") or ratings.get("stamina"), 75)
        self.strength = safe_float(raw.get("strength") or ratings.get("strength") or ratings.get("physical"), 70)
        self.vision = safe_float(raw.get("vision") or ratings.get("vision"), 68)
        self.goalkeeping = safe_float(
            raw.get("goalkeeping") or ratings.get("goalkeeping") or ratings.get("gk"),
            65,
        )
        self.composure = safe_float(raw.get("composure") or ratings.get("composure"), 65)
        self.positioning = safe_float(raw.get("positioning") or ratings.get("positioning"), 65)
        self.acceleration = safe_float(raw.get("acceleration") or ratings.get("acceleration"), 68)
        self.aggression = safe_float(raw.get("aggression") or ratings.get("aggression"), 60)
        self.balance = safe_float(raw.get("balance") or ratings.get("balance"), 65)

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
        self.injured = False
        self.injury_minute = None
        self.injury_severity = 0

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

        self.is_on_pitch = True

    def rating(self):
        values = [
            self.pace, self.passing, self.shooting, self.dribbling, self.defending,
            self.stamina, self.strength, self.vision, self.composure, self.positioning,
        ]
        return sum(values) / len(values)

    def effective_speed(self):
        stamina_factor = 0.72 + (self.stamina_current / 100.0) * 0.28
        base = 3.0
        pace_bonus = self.pace / 100.0 * 3.2
        acc_bonus = self.acceleration / 100.0 * 1.4
        if self.injured:
            stamina_factor *= 0.45
        return (base + pace_bonus + acc_bonus) * stamina_factor

    def to_dict(self):
        # Engine uses y in [0, 60]. Frontend expects y in [0, 100].
        y_scale = 100.0 / 60.0
        return {
            "id": self.id,
            "name": self.name,
            "number": self.number,
            "position": self.position,
            "role": self.role,
            "side": self.side,

            "x": round(self.x, 2),
            "y": round(self.y * y_scale, 2),

            "baseX": round(self.base_x, 2),
            "baseY": round(self.base_y * y_scale, 2),

            "targetX": round(self.target_x, 2),
            "targetY": round(self.target_y * y_scale, 2),

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
            "injured": self.injured,
            "injurySeverity": self.injury_severity,

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
    def __init__(self, raw, side, fallback_name):
        raw = raw or {}
        self.side = side
        self.id = str(raw.get("id") or raw.get("clubId") or raw.get("teamId") or side)
        self.name = normalize_name(
            raw.get("name") or raw.get("clubName") or raw.get("teamName"),
            fallback_name,
        )
        self.logo = (
            raw.get("logo") or raw.get("logoUrl") or raw.get("imageUrl") or raw.get("image") or ""
        )

        self.formation = str(raw.get("formation") or "4-3-3")
        if self.formation not in FORMATION_POSITIONS:
            self.formation = "4-3-3"

        raw_tactics = raw.get("tactics") or {}
        self.tactics = {
            "mentality": str(raw_tactics.get("mentality") or "balanced"),
            "tempo": clamp(safe_float(raw_tactics.get("tempo"), 60), 0, 100),
            "pressing": str(raw_tactics.get("pressing") or "medium"),
            "defensiveLine": str(raw_tactics.get("defensiveLine") or "medium"),
            "width": clamp(safe_float(raw_tactics.get("width"), 55), 0, 100),
        }

        raw_players = raw.get("players")
        if not isinstance(raw_players, list):
            raw_players = (
                raw.get("lineup") if isinstance(raw.get("lineup"), list)
                else raw.get("squad") if isinstance(raw.get("squad"), list)
                else []
            )

        raw_bench = raw.get("bench")
        if not isinstance(raw_bench, list):
            raw_bench = raw.get("substitutes") if isinstance(raw.get("substitutes"), list) else []

        self.players = []
        for index, raw_player in enumerate(raw_players[:11]):
            self.players.append(Player(raw_player, index, side))

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

        self.bench = []
        for index, raw_player in enumerate(raw_bench):
            self.bench.append(Player(raw_player, index + 11, side))

        self.substitutions_used = safe_int(raw.get("substitutionsUsed"), 0)

        raw_stats = raw.get("stats") or {}
        self.stats = {
            "shots": safe_int(raw_stats.get("shots"), 0),
            "shotsOnTarget": safe_int(raw_stats.get("shotsOnTarget"), 0),
            "passes": safe_int(raw_stats.get("passes"), 0),
            "passesCompleted": safe_int(raw_stats.get("passesCompleted"), 0),
            "tackles": safe_int(raw_stats.get("tackles"), 0),
            "corners": safe_int(raw_stats.get("corners"), 0),
            "fouls": safe_int(raw_stats.get("fouls"), 0),
            "yellowCards": safe_int(raw_stats.get("yellowCards"), 0),
            "redCards": safe_int(raw_stats.get("redCards"), 0),
            "offsides": safe_int(raw_stats.get("offsides"), 0),
        }

    def on_pitch(self):
        return [
            player for player in self.players
            if player.is_on_pitch and not player.red
        ]

    def active(self):
        """Players who can actually influence play (not injured)."""
        return [
            player for player in self.players
            if player.is_on_pitch and not player.red and not player.injured
        ]

    def goalkeeper(self):
        for player in self.active():
            if player.position in {"GK", "G", "GOALKEEPER"}:
                return player
        active = self.active()
        return active[0] if active else self.on_pitch()[0]

    def strength(self):
        players = self.active()
        if not players:
            return 50.0
        return sum(player.rating() for player in players) / len(players)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "logo": self.logo,
            "formation": self.formation,
            "tactics": deepcopy(self.tactics),
            "players": [p.to_dict() for p in self.players if p.is_on_pitch],
            "bench": [p.to_dict() for p in self.bench if not p.is_on_pitch],
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
        self.owner_id = None
        self.owner_side = None
        self.state = "owned"
        self.last_touch_side = None
        self.last_touch_player = None

    def to_dict(self):
        y_scale = 100.0 / 60.0
        return {
            "x": round(self.x, 2),
            "y": round(self.y * y_scale, 2),
            "targetX": round(self.target_x, 2),
            "targetY": round(self.target_y * y_scale, 2),
            "vx": round(self.vx, 2),
            "vy": round(self.vy, 2),
            "ownerId": self.owner_id,
            "ownerSide": self.owner_side,
            "state": self.state,
            "lastTouchSide": self.last_touch_side,
            "lastTouchPlayer": self.last_touch_player,
        }


# ============================================================
# MATCH
# ============================================================

class FootballMatch:

    def __init__(self, config):
        self.lock = threading.RLock()
        self.config = config or {}

        self.match_id = str(
            self.config.get("matchId") or self.config.get("id") or uuid.uuid4()
        )
        self.status = "created"
        self.running = False
        self.finished = False
        self.destroyed = False
        self.half = 1
        self.football_seconds = 0.0

        self.first_half_injury = random.randint(1, 3)
        self.second_half_injury = random.randint(2, 5)

        self.halftime_until = None

        self.score = {"home": 0, "away": 0}

        self.home = Team(
            self.config.get("home") or self.config.get("homeTeam") or {},
            "home",
            "Home Team",
        )
        self.away = Team(
            self.config.get("away") or self.config.get("awayTeam") or {},
            "away",
            "Away Team",
        )

        self.ball = Ball()
        self.possession_side = random.choice(["home", "away"])

        self.events = []
        self.last_event = None

        self.created_at = time.time()
        self.last_tick = time.monotonic()
        self.last_decision = time.monotonic()
        self.next_action_at = time.monotonic() + 0.5

        self.thread = None
        self.stop_event = threading.Event()
        self.result = None

        self.stats = {
            "possession": {"home": 50.0, "away": 50.0},
            "shots": {"home": 0, "away": 0},
            "shotsOnTarget": {"home": 0, "away": 0},
            "passes": {"home": 0, "away": 0},
            "passesCompleted": {"home": 0, "away": 0},
            "tackles": {"home": 0, "away": 0},
            "corners": {"home": 0, "away": 0},
            "fouls": {"home": 0, "away": 0},
            "yellowCards": {"home": 0, "away": 0},
            "redCards": {"home": 0, "away": 0},
            "offsides": {"home": 0, "away": 0},
        }

        self._setup_positions()
        self._assign_initial_ball()

    # ========================================================
    # EVENT
    # ========================================================

    def _event(self, event_type, team=None, player=None, minute=None, second=None, **extra):
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "team": team,
            "player": player,
            "minute": minute if minute is not None else self.minute(),
            "second": second if second is not None else self.second(),
            "timestamp": time.time(),
        }
        event.update(extra)
        self.events.append(event)
        if len(self.events) > MAX_EVENTS:
            self.events = self.events[-MAX_EVENTS:]
        self.last_event = event
        return event

    def event(self, event_type, team=None, player=None, **extra):
        return self._event(event_type, team=team, player=player, **extra)

    # ========================================================
    # HELPERS
    # ========================================================

    def _team(self, side):
        return self.home if side == "home" else self.away

    def _other_side(self, side):
        return "away" if side == "home" else "home"

    def _all_players(self):
        return self.home.on_pitch() + self.away.on_pitch()

    def _active_players(self):
        return self.home.active() + self.away.active()

    def _find_player(self, player_id):
        if not player_id:
            return None
        pid = str(player_id)
        for player in self.home.players + self.home.bench:
            if player.id == pid:
                return player
        for player in self.away.players + self.away.bench:
            if player.id == pid:
                return player
        return None

    # ========================================================
    # FORMATION SETUP
    # ========================================================

    def _setup_positions(self):
        self._apply_positions(self.home, attacking_to_right=True)
        self._apply_positions(self.away, attacking_to_right=False)

    def _apply_positions(self, team, attacking_to_right):
        positions = FORMATION_POSITIONS.get(team.formation, FORMATION_POSITIONS["4-3-3"])
        width_factor = 0.80 + team.tactics["width"] / 100.0 * 0.40

        on_pitch = [p for p in team.players if p.is_on_pitch and not p.red]

        for index, player in enumerate(on_pitch):
            if index >= len(positions):
                break

            role, raw_x, raw_y = positions[index]
            player.position = role
            player.role = role

            x = float(raw_x)
            y = 30.0 + (float(raw_y) - 30.0) * width_factor

            if not attacking_to_right:
                x = 100.0 - x

            player.base_x = clamp(x, 4, 96)
            player.base_y = clamp(y, 3, 57)
            player.x = player.base_x
            player.y = player.base_y
            player.target_x = player.x
            player.target_y = player.y

    # ========================================================
    # BALL SETUP
    # ========================================================

    def _assign_initial_ball(self):
        team = self._team(self.possession_side)
        players = team.active()
        if not players:
            return
        midfielders = [p for p in players if p.position not in {"GK", "G"}]
        player = random.choice(midfielders) if midfielders else players[0]
        self._give_ball_to(player)

    def _give_ball_to(self, player):
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

    def minute(self):
        return int(self.football_seconds // 60)

    def second(self):
        return int(self.football_seconds % 60)

    def clock_string(self):
        return f"{self.minute():02d}:{self.second():02d}"

    def _current_limit(self):
        if self.half == 1:
            return FIRST_HALF_SECONDS + self.first_half_injury * 60
        return FULL_MATCH_SECONDS + self.second_half_injury * 60

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
                self._event("second_half_start")
            elif self.status != "playing":
                self.status = "playing"
                self.running = True
                self.last_tick = time.monotonic()
                if self.football_seconds <= 0:
                    self._event("match_start")

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
            self._event("full_time")

            self.result = {
                "home": self.score["home"],
                "away": self.score["away"],
                "winner": (
                    "home" if self.score["home"] > self.score["away"]
                    else "away" if self.score["away"] > self.score["home"]
                    else "draw"
                ),
            }
            return self.snapshot()

    # ========================================================
    # THREAD
    # ========================================================

    def _ensure_thread(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._simulation_loop, daemon=True)
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
                    dt = clamp(dt, 0.01, 0.50)
                    if self.running and not self.finished:
                        self._tick(dt)
                time.sleep(TICK_SECONDS)
            except Exception as exc:
                try:
                    with self.lock:
                        self._event("engine_error", message=str(exc))
                except Exception:
                    pass
                time.sleep(0.5)

    # ========================================================
    # MAIN TICK
    # ========================================================

    def _tick(self, dt):
        if self.status != "playing":
            return

        self.football_seconds += dt * TIME_SCALE

        self._update_stamina(dt)
        self._check_injuries(dt)
        self._update_player_targets()
        self._move_players(dt)
        self._update_ball(dt)
        self._update_possession()
        self._make_decisions()
        self._check_half_time_or_full_time()

    # ========================================================
    # HALF / FULL TIME
    # ========================================================

    def _check_half_time_or_full_time(self):
        if self.half == 1 and self.football_seconds >= self._current_limit():
            self.football_seconds = self._current_limit()
            self.running = False
            self.status = "halftime"
            self.halftime_until = time.monotonic() + HALF_TIME_BREAK_SECONDS
            self._event("half_time")
            self._schedule_second_half()
            return

        if self.half == 2 and self.football_seconds >= self._current_limit():
            self.football_seconds = self._current_limit()
            self.running = False
            self.finished = True
            self.status = "finished"
            self._event("full_time")
            self.result = {
                "home": self.score["home"],
                "away": self.score["away"],
                "winner": (
                    "home" if self.score["home"] > self.score["away"]
                    else "away" if self.score["away"] > self.score["home"]
                    else "draw"
                ),
            }

    def _schedule_second_half(self):
        def resume():
            time.sleep(HALF_TIME_BREAK_SECONDS)
            with self.lock:
                if self.destroyed or self.finished:
                    return
                if self.status != "halftime":
                    return
                self.half = 2
                self.football_seconds = FIRST_HALF_SECONDS
                self.status = "playing"
                self.running = True
                self.halftime_until = None
                self.last_tick = time.monotonic()
                self._event("second_half_start")
        threading.Thread(target=resume, daemon=True).start()

    # ========================================================
    # STAMINA
    # ========================================================

    def _update_stamina(self, dt):
        for player in self._all_players():
            if player.injured:
                continue
            exertion = 0.004 + player.speed * 0.0010
            if player.side == self.possession_side:
                exertion += 0.0005
            player.stamina_current = clamp(
                player.stamina_current - exertion * dt * TIME_SCALE,
                20,
                100,
            )

    # ========================================================
    # INJURIES
    # ========================================================

    def _check_injuries(self, dt):
        football_dt = dt * TIME_SCALE
        for player in self._all_players():
            if player.injured or player.red:
                continue
            base_chance = 0.0000022 * football_dt
            stamina_factor = 1 + (100 - player.stamina_current) / 55
            chance = base_chance * stamina_factor
            if random.random() < chance:
                severity = random.choices([1, 2], weights=[3, 1])[0]
                self._injure_player(player, severity)

    def _injure_player(self, player, severity=1):
        if player.injured:
            return
        player.injured = True
        player.injury_severity = severity
        player.injury_minute = self.minute()
        player.speed = 0.0

        self._event(
            "injury",
            team=player.side,
            player=player.id,
            severity="minor" if severity == 1 else "major",
            message=f"{player.name} is injured",
        )

        # If ball was with the injured player, release it.
        if self.ball.owner_id == player.id:
            self.ball.owner_id = None
            self.ball.owner_side = None
            self.ball.state = "loose"
            self.ball.vx = random.uniform(-3, 3)
            self.ball.vy = random.uniform(-3, 3)

    # ========================================================
    # TARGETS  (NEW AI)
    # ========================================================

    def _update_player_targets(self):
        now = time.monotonic()
        ball_x = self.ball.x
        ball_y = self.ball.y
        ball_owner = self._find_player(self.ball.owner_id)
        ball_owner_side = self.ball.owner_side

        for player in self._all_players():
            if player.red:
                continue

            # Injured: stay put
            if player.injured:
                player.target_x = player.x
                player.target_y = player.y
                continue

            # Throttle target updates (but not too much)
            if now - player.last_target_update < 0.35:
                continue
            player.last_target_update = now

            if ball_owner and ball_owner.injured:
                ball_owner = None

            if ball_owner and player.side == ball_owner_side:
                if player.id == ball_owner.id:
                    self._target_for_ball_carrier(player)
                else:
                    self._target_for_attacker_support(player, ball_owner)
            elif ball_owner and player.side != ball_owner_side:
                self._target_for_defender(player, ball_owner)
            else:
                self._target_for_loose_ball(player, ball_x, ball_y)

    # ---------------------------------------------------------
    # BALL CARRIER AI
    # ---------------------------------------------------------
    def _target_for_ball_carrier(self, player):
        direction = 1 if player.side == "home" else -1
        goal_x = 100 if player.side == "home" else 0

        nearest = self._nearest_opponent(player, max_distance=9)

        target_x = player.x + direction * 3.5
        target_y = player.y

        if nearest:
            dy = player.y - nearest.y
            if abs(dy) < 3.5:
                # Move sideways to avoid the defender.
                target_y = player.y + (5.0 if player.y < 30 else -5.0)
                target_x = player.x + direction * 1.5
            else:
                target_y = player.y + dy * 0.35
                target_x = player.x + direction * 3.0

        # Drift toward goal.
        target_x = lerp(target_x, goal_x, 0.06)
        # Drift toward center channel.
        target_y = lerp(target_y, 30, 0.03)

        # Occasional diagonal runs.
        if random.random() < 0.15:
            target_y += random.uniform(-4, 4)

        player.target_x = clamp(target_x, 3, 97)
        player.target_y = clamp(target_y, 2, 58)

    # ---------------------------------------------------------
    # ATTACKER OFF-BALL AI
    # ---------------------------------------------------------
    def _target_for_attacker_support(self, player, ball_owner):
        role = player.position
        direction = 1 if player.side == "home" else -1

        base_x = player.base_x
        base_y = player.base_y

        d_to_ball = math.sqrt((player.x - ball_owner.x) ** 2 + (player.y - ball_owner.y) ** 2)
        d_ball_to_goal = abs(ball_owner.x - (100 if player.side == "home" else 0))

        # Push up based on possession.
        push = 6.0 if d_ball_to_goal < 50 else 3.0
        target_x = base_x + direction * push
        target_y = base_y

        # Closest teammate supports closely.
        if d_to_ball < 22:
            target_x = lerp(base_x, ball_owner.x + direction * 7, 0.45)
            # Support at an angle.
            side_offset = 12 if player.y > ball_owner.y else -12
            target_y = lerp(base_y, ball_owner.y + side_offset, 0.40)

        # Strikers: make runs into channels / behind defence
        if role in {"ST", "CF", "SS"}:
            target_x = max(target_x, base_x + direction * 6)
            if random.random() < 0.18:
                target_y = 30 + random.uniform(-13, 13)
            # Stay onside (vaguely).
            target_x = clamp(target_x, 3, 92 if direction > 0 else 8)

        # Wingers: hold width, cut inside when ball is far
        elif role in {"LW", "RW", "LM", "RM"}:
            if player.y > 30:
                target_y = max(target_y, 42)
            else:
                target_y = min(target_y, 18)
            # If ball is on opposite flank, tuck in
            if abs(ball_owner.y - player.y) > 20 and d_ball_to_goal < 45:
                target_y = lerp(target_y, 30, 0.35)

        # Full-backs: overlap when team is attacking high
        elif role in {"LB", "RB", "LWB", "RWB"}:
            if d_ball_to_goal < 40 and random.random() < 0.25:
                target_x += direction * 8
                target_y = lerp(target_y, ball_owner.y, 0.35)

        # Midfielders: find pockets of space
        elif role in {"CM", "LCM", "RCM", "DM", "LDM", "RDM", "AM", "CAM", "LAM", "RAM", "CDM", "CAM"}:
            space = self._space_around(player, max_distance=8)
            if space < 0.4:
                # Move away from nearest opponent.
                nearest = self._nearest_opponent(player, max_distance=10)
                if nearest:
                    if player.y > nearest.y:
                        target_y = player.y + 4
                    else:
                        target_y = player.y - 4

        # Small random wander for natural movement.
        target_x += random.uniform(-1.5, 1.5)
        target_y += random.uniform(-2.0, 2.0)

        player.target_x = clamp(target_x, 3, 97)
        player.target_y = clamp(target_y, 2, 58)

    # ---------------------------------------------------------
    # DEFENDER AI
    # ---------------------------------------------------------
    def _target_for_defender(self, player, ball_owner):
        role = player.position
        direction = 1 if player.side == "home" else -1
        own_goal_x = 0 if player.side == "home" else 100

        d_to_ball = math.sqrt((player.x - ball_owner.x) ** 2 + (player.y - ball_owner.y) ** 2)

        # Is this defender the designated presser?
        is_presser = self._is_nearest_teammate_to_ball(player, ball_owner)

        pressing = self._team(player.side).tactics.get("pressing", "medium")
        press_range = {"low": 16, "medium": 22, "high": 28, "very_high": 34}.get(pressing, 22)

        # Goalkeeper positioning.
        if role in {"GK", "G"}:
            gx = 5 if player.side == "home" else 95
            gy = clamp(30 + (ball_owner.y - 30) * 0.45, 18, 42)
            # Rush out for very close ball
            if d_to_ball < 8:
                target_x = lerp(gx, ball_owner.x, 0.35)
                target_y = lerp(gy, ball_owner.y, 0.30)
            else:
                target_x, target_y = gx, gy
            player.target_x = clamp(target_x, 3, 97)
            player.target_y = clamp(target_y, 2, 58)
            return

        if is_presser and d_to_ball < press_range:
            # PRESS the ball carrier.
            press_x = ball_owner.x - direction * 1.2
            press_y = ball_owner.y
            target_x = lerp(player.x, press_x, 0.18)
            target_y = lerp(player.y, press_y, 0.18)
        else:
            # HOLD team shape / mark.
            base_x = player.base_x
            base_y = player.base_y

            # Compact the team: shift toward the ball.
            target_x = lerp(base_x, ball_owner.x, 0.10)
            target_y = lerp(base_y, ball_owner.y, 0.08)

            # CBs keep their line.
            if "CB" in role:
                target_y = lerp(base_y, ball_owner.y, 0.06)

            # Full-backs track wingers.
            elif role in {"LB", "RB", "LWB", "RWB"}:
                target_y = lerp(base_y, ball_owner.y, 0.18)

            # Defensive midfielders drop in front of defence.
            elif role in {"DM", "LDM", "RDM", "CDM"}:
                target_x = base_x - direction * 3
                target_y = lerp(base_y, ball_owner.y, 0.10)

            # Attackers drop to help press (light).
            elif role in {"ST", "CF", "LW", "RW", "LM", "RM"}:
                # Drift toward ball only if ball is in defensive third.
                ball_x = ball_owner.x
                in_defensive_third = (
                    ball_x < 40 if player.side == "home" else ball_x > 60
                )
                if in_defensive_third:
                    target_x = lerp(base_x, ball_owner.x, 0.20)
                    target_y = lerp(base_y, ball_owner.y, 0.15)

            # Mark nearest attacker for defenders.
            if role in {"LB", "RB", "LWB", "RWB", "CB", "LCB", "RCB"}:
                marker = self._nearest_opponent_to_point(
                    player, ball_owner.x, ball_owner.y, max_distance=14
                )
                if marker and marker.id != ball_owner.id:
                    target_x = lerp(target_x, marker.x, 0.12)
                    target_y = lerp(target_y, marker.y, 0.15)

        player.target_x = clamp(target_x, 3, 97)
        player.target_y = clamp(target_y, 2, 58)

    # ---------------------------------------------------------
    # LOOSE BALL AI
    # ---------------------------------------------------------
    def _target_for_loose_ball(self, player, ball_x, ball_y):
        d = math.sqrt((player.x - ball_x) ** 2 + (player.y - ball_y) ** 2)

        teammates = self._team(player.side).active()
        if not teammates:
            return

        closest_d = min(
            math.sqrt((p.x - ball_x) ** 2 + (p.y - ball_y) ** 2)
            for p in teammates
        )

        if abs(d - closest_d) < 0.5 or d < 12:
            target_x = lerp(player.x, ball_x, 0.20)
            target_y = lerp(player.y, ball_y, 0.20)
        else:
            target_x = lerp(player.base_x, ball_x, 0.05)
            target_y = lerp(player.base_y, ball_y, 0.05)

        player.target_x = clamp(target_x, 3, 97)
        player.target_y = clamp(target_y, 2, 58)

    # ---------------------------------------------------------
    # AI HELPERS
    # ---------------------------------------------------------
    def _is_nearest_teammate_to_ball(self, player, ball_owner):
        teammates = self._team(player.side).active()
        pd = math.sqrt((player.x - ball_owner.x) ** 2 + (player.y - ball_owner.y) ** 2)
        for tm in teammates:
            if tm.id == player.id:
                continue
            td = math.sqrt((tm.x - ball_owner.x) ** 2 + (tm.y - ball_owner.y) ** 2)
            if td < pd - 0.5:
                return False
        return True

    def _space_around(self, player, max_distance=6):
        opp_side = self._other_side(player.side)
        opponents = self._team(opp_side).active()
        if not opponents:
            return 1.0
        nearest_d = min(
            (math.sqrt((o.x - player.x) ** 2 + (o.y - player.y) ** 2) for o in opponents),
            default=max_distance,
        )
        return clamp(nearest_d / max_distance, 0, 1)

    def _nearest_opponent_to_point(self, player, x, y, max_distance=100):
        opp_side = self._other_side(player.side)
        opponents = self._team(opp_side).active()
        nearest = None
        nearest_d = max_distance
        for opp in opponents:
            d = math.sqrt((opp.x - x) ** 2 + (opp.y - y) ** 2)
            if d < nearest_d:
                nearest = opp
                nearest_d = d
        return nearest

    # ========================================================
    # MOVEMENT
    # ========================================================

    def _move_players(self, dt):
        ball_owner = self._find_player(self.ball.owner_id)

        for player in self._all_players():
            if player.red:
                continue

            if player.injured:
                player.speed = 0.0
                continue

            dx = player.target_x - player.x
            dy = player.target_y - player.y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < 0.05:
                player.speed = 0.0
                continue

            speed = player.effective_speed()

            # Ball carrier runs slightly slower (control) but not too slow.
            if ball_owner and ball_owner.id == player.id:
                speed *= 0.82

            # Sprint when very far from target.
            if dist > 12:
                speed *= 1.15

            max_move = speed * dt
            ratio = min(1.0, max_move / max(dist, 0.001))

            old_x, old_y = player.x, player.y

            player.x += dx * ratio
            player.y += dy * ratio

            player.x = clamp(player.x, 2, 98)
            player.y = clamp(player.y, 2, 58)

            moved = math.sqrt((player.x - old_x) ** 2 + (player.y - old_y) ** 2)
            player.speed = moved / max(dt, 0.001)

            # Keep ball glued.
            if self.ball.owner_id == player.id and self.ball.state == "owned":
                self.ball.x = player.x
                self.ball.y = player.y

    # ========================================================
    # BALL PHYSICS
    # ========================================================

    def _update_ball(self, dt):
        if self.ball.state == "owned":
            owner = self._find_player(self.ball.owner_id)
            if owner and not owner.injured:
                self.ball.x = owner.x
                self.ball.y = owner.y
            else:
                # Owner disappeared.
                self.ball.owner_id = None
                self.ball.owner_side = None
                self.ball.state = "loose"
            return

        self.ball.x += self.ball.vx * dt
        self.ball.y += self.ball.vy * dt

        self.ball.vx *= BALL_FRICTION
        self.ball.vy *= BALL_FRICTION

        if abs(self.ball.vx) < 0.20:
            self.ball.vx = 0
        if abs(self.ball.vy) < 0.20:
            self.ball.vy = 0

        if self.ball.x <= 0 or self.ball.x >= 100:
            self._handle_goal_line()
            return

        if self.ball.y <= 0 or self.ball.y >= 60:
            self._handle_touchline()
            return

        if self.ball.state == "loose":
            nearest = self._nearest_player(
                self.ball.x, self.ball.y, max_distance=4.5
            )
            if nearest and not nearest.injured:
                self._give_ball_to(nearest)

    def _handle_goal_line(self):
        x = self.ball.x
        attacking_side = self.ball.last_touch_side
        if attacking_side is None:
            self._reset_ball()
            return

        defending_side = self._other_side(attacking_side)
        goal = (x >= 100 if attacking_side == "home" else x <= 0)

        if goal:
            self._goal(attacking_side)
            return

        # Ball went out the wrong side → goal kick
        self._event("goal_kick", team=defending_side)
        keeper = self._team(defending_side).goalkeeper()
        if keeper and not keeper.injured:
            keeper.x = clamp(6 if defending_side == "home" else 94, 3, 97)
            keeper.y = 30.0
            self._give_ball_to(keeper)
        else:
            self._reset_ball()

    def _handle_touchline(self):
        last_side = self.ball.last_touch_side
        if last_side is None:
            self._reset_ball()
            return

        throw_side = self._other_side(last_side)

        self.ball.y = 1 if self.ball.y <= 0 else 59
        self.ball.vx = 0
        self.ball.vy = 0
        self.ball.state = "loose"

        self._event("throw_in", team=throw_side)

        player = self._nearest_player(
            self.ball.x, self.ball.y, side=throw_side, max_distance=20
        )
        if player and not player.injured:
            self._give_ball_to(player)
        else:
            self._reset_ball()

    def _reset_ball(self):
        self.ball.state = "owned"
        self.ball.vx = 0
        self.ball.vy = 0

        team = self._team(self.possession_side)
        players = team.active()
        if players:
            player = min(
                players,
                key=lambda p: distance(
                    {"x": p.x, "y": p.y},
                    {"x": self.ball.x, "y": self.ball.y},
                ),
            )
            self._give_ball_to(player)

    # ========================================================
    # POSSESSION
    # ========================================================

    def _update_possession(self):
        home_strength = self.home.strength()
        away_strength = self.away.strength()
        total = max(1.0, home_strength + away_strength)
        home_base = home_strength / total

        home_tempo = self.home.tactics["tempo"]
        away_tempo = self.away.tactics["tempo"]
        home_bias = (home_tempo - away_tempo) * 0.0005

        home_target = clamp(home_base + home_bias, 0.30, 0.70)
        current = self.stats["possession"]["home"]
        current = lerp(current, home_target * 100, 0.003)

        self.stats["possession"]["home"] = round(current, 2)
        self.stats["possession"]["away"] = round(100 - current, 2)

    # ========================================================
    # DECISIONS
    # ========================================================

    def _make_decisions(self):
        now = time.monotonic()
        if now < self.next_action_at:
            return
        self.next_action_at = now + random.uniform(0.22, 0.65)

        owner = self._find_player(self.ball.owner_id)
        if not owner or owner.red or owner.injured:
            return

        self._decide_for_ball_carrier(owner)

    def _decide_for_ball_carrier(self, player):
        now = time.monotonic()
        if now - player.last_action_at < MIN_ACTION_INTERVAL:
            return
        player.last_action_at = now

        goal_distance = self._distance_to_opponent_goal(player)
        nearby_defender = self._nearest_opponent(player, max_distance=6)
        in_space = nearby_defender is None

        # ---------- SHOOT ----------
        if goal_distance < 28:
            shot_chance = 0.09 + player.shooting / 1200 + player.composure / 1800
            if in_space:
                shot_chance *= 1.5
            if nearby_defender:
                shot_chance *= 0.55
            if goal_distance > 20:
                shot_chance *= 0.45

            if random.random() < shot_chance:
                if now - player.last_shot_at >= MIN_SHOT_INTERVAL:
                    self._shoot(player)
                    return

        # ---------- PASS ----------
        if now - player.last_pass_at >= MIN_PASS_INTERVAL:
            pass_probability = 0.55 + player.vision / 400
            if nearby_defender:
                pass_probability += 0.20
            if random.random() < clamp(pass_probability, 0.40, 0.92):
                if self._attempt_pass(player):
                    return

        # ---------- DRIBBLE ----------
        if now - player.last_dribble_at >= MIN_DRIBBLE_INTERVAL:
            dribble_chance = 0.30 + player.dribbling / 400
            if not nearby_defender:
                dribble_chance = 0.55
            if random.random() < dribble_chance:
                self._attempt_dribble(player)

    # ========================================================
    # PASSING
    # ========================================================

    def _attempt_pass(self, player):
        teammates = [
            tm for tm in self._team(player.side).active()
            if tm.id != player.id
        ]
        if not teammates:
            return False

        direction = 1 if player.side == "home" else -1

        candidates = []
        for teammate in teammates:
            d = math.sqrt(
                (teammate.x - player.x) ** 2 + (teammate.y - player.y) ** 2
            )
            if d < 3 or d > 45:
                continue

            lane_blocked = self._pass_lane_blocked(player, teammate)
            forward = (teammate.x - player.x) * direction
            space = self._space_around(teammate, max_distance=6)

            score = (
                forward * 0.6
                + space * 3.0
                + teammate.rating() * 0.04
                - d * 0.12
                - lane_blocked * 25
            )
            # Prefer to pass to someone in a more advanced position.
            if forward > 0:
                score += 2.5

            candidates.append((teammate, d, score, forward))

        if not candidates:
            return False

        candidates.sort(key=lambda x: x[2], reverse=True)
        receiver = candidates[0][0]
        distance_to_receiver = candidates[0][1]
        forward_pass = candidates[0][3]

        # Through ball?
        is_through_ball = forward_pass > 8 and distance_to_receiver > 12

        base_quality = 0.60 + player.passing / 250 + player.vision / 400
        pressure = self._pressure_on_player(player)
        quality = base_quality * (1 - pressure * 0.4)

        if is_through_ball:
            quality -= 0.10

        quality = clamp(quality, 0.35, 0.95)

        self.stats["passes"][player.side] += 1
        self._team(player.side).stats["passes"] += 1
        player.passes += 1
        player.last_pass_at = time.monotonic()

        if random.random() <= quality:
            # SUCCESS
            self.stats["passesCompleted"][player.side] += 1
            self._team(player.side).stats["passesCompleted"] += 1
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
                through=is_through_ball,
            )
            return True

        # FAILED
        self.ball.owner_id = None
        self.ball.owner_side = None
        self.ball.state = "loose"

        angle = math.atan2(receiver.y - player.y, receiver.x - player.x)
        speed = BALL_SPEED * (0.70 if is_through_ball else 0.55)
        self.ball.vx = math.cos(angle) * speed
        self.ball.vy = math.sin(angle) * speed

        if is_through_ball:
            self.ball.vx *= 1.25
            self.ball.vy *= 1.25

        self.ball.last_touch_side = player.side
        self.ball.last_touch_player = player.id

        self._event(
            "pass",
            team=player.side,
            player=player.id,
            receiver=receiver.id,
            completed=False,
            through=is_through_ball,
        )
        return True

    def _pass_lane_blocked(self, passer, receiver):
        opponents = self._team(self._other_side(passer.side)).active()
        count = 0
        for opp in opponents:
            d = point_to_segment_distance(
                opp.x, opp.y, passer.x, passer.y, receiver.x, receiver.y
            )
            if d < 2.2:
                count += 1
        return count

    # ========================================================
    # DRIBBLING
    # ========================================================

    def _attempt_dribble(self, player):
        player.last_dribble_at = time.monotonic()
        defender = self._nearest_opponent(player, max_distance=7)

        if not defender:
            direction = 1 if player.side == "home" else -1
            player.target_x = clamp(
                player.x + direction * random.uniform(3, 7), 3, 97
            )
            self._event(
                "dribble", team=player.side, player=player.id, successful=True
            )
            return

        attacker_power = (
            player.dribbling + player.balance * 0.30 + player.acceleration * 0.25
        )
        defender_power = (
            defender.defending + defender.strength * 0.20 + defender.aggression * 0.15
        )

        chance = clamp(
            0.50 + (attacker_power - defender_power) / 180, 0.22, 0.82
        )

        if random.random() < chance:
            direction = 1 if player.side == "home" else -1
            player.target_x = clamp(
                player.x + direction * random.uniform(3, 6), 3, 97
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
            self.stats["tackles"][defender.side] += 1
            self._team(defender.side).stats["tackles"] += 1

            self._event(
                "tackle",
                team=defender.side,
                player=defender.id,
                opponent=player.id,
            )

            # Injury risk from tackle.
            if random.random() < 0.008:
                self._injure_player(player, severity=random.choice([1, 1, 2]))

            self._give_ball_to(defender)

    # ========================================================
    # SHOOTING
    # ========================================================

    def _shoot(self, player):
        player.last_shot_at = time.monotonic()
        player.shots += 1
        self.stats["shots"][player.side] += 1
        self._team(player.side).stats["shots"] += 1

        goal_distance = self._distance_to_opponent_goal(player)
        angle_quality = 1 - abs(player.y - 30) / 40
        pressure = self._pressure_on_player(player)

        quality = (
            player.shooting * 0.55
            + player.composure * 0.20
            + player.balance * 0.10
            + angle_quality * 15
            - pressure * 12
        )
        quality = clamp(quality, 20, 100)

        goal_probability = 0.025 + quality / 1000
        distance_factor = clamp(1 - (goal_distance - 8) / 70, 0.25, 1.0)
        goal_probability *= distance_factor

        if player.position in {"ST", "CF"}:
            goal_probability *= 1.18
        if player.position in {"CB", "LCB", "RCB"}:
            goal_probability *= 0.55

        goal_probability = clamp(goal_probability, 0.01, 0.22)

        on_target_probability = clamp(
            0.28
            + player.shooting / 180
            + player.composure / 400
            - pressure * 0.08,
            0.22,
            0.78,
        )

        self._event(
            "shot",
            team=player.side,
            player=player.id,
            distance=round(goal_distance, 1),
        )

        if random.random() < goal_probability:
            player.shots_on_target += 1
            self.stats["shotsOnTarget"][player.side] += 1
            self._team(player.side).stats["shotsOnTarget"] += 1
            self._goal(player.side, scorer=player)
            return

        if random.random() < on_target_probability:
            player.shots_on_target += 1
            self.stats["shotsOnTarget"][player.side] += 1
            self._team(player.side).stats["shotsOnTarget"] += 1

            goalkeeper = self._team(self._other_side(player.side)).goalkeeper()

            save_power = (
                goalkeeper.goalkeeping
                + goalkeeper.positioning * 0.30
                + goalkeeper.composure * 0.20
            )
            save_chance = clamp(
                0.42 + save_power / 220 - quality / 500, 0.30, 0.90
            )

            if random.random() < save_chance:
                goalkeeper.saves += 1
                self._event(
                    "save",
                    team=goalkeeper.side,
                    player=goalkeeper.id,
                    shooter=player.id,
                )
                self._give_ball_to(goalkeeper)
                return

            # Rebound
            self.ball.owner_id = None
            self.ball.owner_side = None
            self.ball.state = "loose"
            self.ball.x = 96 if player.side == "home" else 4
            self.ball.y = clamp(
                player.y + random.uniform(-8, 8), 2, 58
            )
            self.ball.vx = -12 if player.side == "home" else 12
            self.ball.vy = random.uniform(-6, 6)

            self._event("rebound", team=player.side, player=player.id)
            return

        # Off target
        self.ball.owner_id = None
        self.ball.owner_side = None
        self.ball.state = "loose"
        self.ball.x = 98 if player.side == "home" else 2
        self.ball.y = clamp(player.y + random.uniform(-12, 12), 0, 60)
        self.ball.vx = 8 if player.side == "home" else -8
        self.ball.vy = random.uniform(-4, 4)

        self._event("shot_off_target", team=player.side, player=player.id)

    # ========================================================
    # GOAL
    # ========================================================

    def _goal(self, side, scorer=None):
        self.score[side] += 1
        if scorer:
            scorer.goals += 1

        self._event(
            "goal",
            team=side,
            player=scorer.id if scorer else None,
            score={"home": self.score["home"], "away": self.score["away"]},
        )

        self.ball.owner_id = None
        self.ball.owner_side = None
        self.ball.state = "owned"
        self.ball.x = 50
        self.ball.y = 30
        self.ball.vx = 0
        self.ball.vy = 0

        kickoff_side = self._other_side(side)
        self.possession_side = kickoff_side

        team = self._team(kickoff_side)
        candidates = [
            p for p in team.active() if p.position not in {"GK", "G"}
        ]
        if not candidates:
            candidates = team.active()

        if candidates:
            player = min(candidates, key=lambda p: abs(p.y - 30))
            self._give_ball_to(player)

        self._event("kickoff_after_goal", team=kickoff_side)

    # ========================================================
    # DISTANCES / PRESSURE
    # ========================================================

    def _distance_to_opponent_goal(self, player):
        goal_x = 100 if player.side == "home" else 0
        dx = goal_x - player.x
        dy = 30 - player.y
        return math.sqrt(dx * dx + dy * dy)

    def _pressure_on_player(self, player):
        opponent = self._nearest_opponent(player, max_distance=12)
        if not opponent:
            return 0.0
        d = distance(
            {"x": player.x, "y": player.y},
            {"x": opponent.x, "y": opponent.y},
        )
        return clamp(1 - d / 12, 0, 1)

    def _nearest_opponent(self, player, max_distance=100):
        opponents = self._team(self._other_side(player.side)).active()
        nearest = None
        nearest_d = max_distance
        for opp in opponents:
            d = distance(
                {"x": player.x, "y": player.y},
                {"x": opp.x, "y": opp.y},
            )
            if d < nearest_d:
                nearest = opp
                nearest_d = d
        return nearest

    def _nearest_player(self, x, y, side=None, max_distance=100):
        players = self._team(side).active() if side else self._active_players()
        nearest = None
        nearest_d = max_distance
        for player in players:
            d = math.sqrt((player.x - x) ** 2 + (player.y - y) ** 2)
            if d < nearest_d:
                nearest = player
                nearest_d = d
        return nearest

    # ========================================================
    # TACTICS
    # ========================================================

    def set_tactics(self, side, tactics):
        with self.lock:
            if side not in {"home", "away"}:
                raise ValueError("side must be home or away")

            team = self._team(side)
            if not isinstance(tactics, dict):
                tactics = {}

            team.tactics["mentality"] = str(
                tactics.get("mentality", team.tactics["mentality"])
            )
            team.tactics["tempo"] = clamp(
                safe_float(
                    tactics.get("tempo", team.tactics["tempo"]),
                    team.tactics["tempo"],
                ),
                0,
                100,
            )
            team.tactics["pressing"] = str(
                tactics.get("pressing", team.tactics["pressing"])
            )
            team.tactics["defensiveLine"] = str(
                tactics.get("defensiveLine", team.tactics["defensiveLine"])
            )
            team.tactics["width"] = clamp(
                safe_float(
                    tactics.get("width", team.tactics["width"]),
                    team.tactics["width"],
                ),
                0,
                100,
            )

            # Refresh positions to reflect new width.
            self._apply_positions(
                team, attacking_to_right=(side == "home")
            )

            self._event(
                "tactics_change",
                team=side,
                tactics=deepcopy(team.tactics),
            )
            return self.snapshot()

    # ========================================================
    # FORMATION
    # ========================================================

    def set_formation(self, side, formation):
        with self.lock:
            if side not in {"home", "away"}:
                raise ValueError("side must be home or away")

            formation = str(formation).strip()
            if formation not in FORMATION_POSITIONS:
                raise ValueError(
                    "Unsupported formation. Use 4-3-3, 4-4-2, 4-2-3-1, 3-5-2 or 5-3-2."
                )

            team = self._team(side)
            team.formation = formation

            self._apply_positions(
                team, attacking_to_right=(side == "home")
            )

            self._event("formation_change", team=side, formation=formation)
            return self.snapshot()

    # ========================================================
    # SUBSTITUTIONS
    # ========================================================

    def substitute(self, side, outgoing_id, incoming_id):
        with self.lock:
            if side not in {"home", "away"}:
                raise ValueError("side must be home or away")

            team = self._team(side)

            if team.substitutions_used >= 5:
                raise ValueError("Maximum substitutions reached.")

            outgoing = self._find_player(
                str(outgoing_id) if outgoing_id is not None else None
            )
            incoming = self._find_player(
                str(incoming_id) if incoming_id is not None else None
            )

            if outgoing is None:
                raise ValueError("Outgoing player not found.")
            if incoming is None:
                raise ValueError("Incoming player not found.")

            if outgoing.side != side:
                raise ValueError("Outgoing player belongs to another team.")
            if incoming.side != side:
                raise ValueError("Incoming player belongs to another team.")

            if not outgoing.is_on_pitch:
                raise ValueError("Outgoing player is not on the pitch.")
            if incoming.is_on_pitch:
                raise ValueError("Incoming player is already on the pitch.")

            # Match position/role so the sub slots into shape.
            incoming.position = outgoing.position
            incoming.role = outgoing.role

            outgoing.is_on_pitch = False
            incoming.is_on_pitch = True
            incoming.injured = False  # bench player is fit

            incoming.x = outgoing.x
            incoming.y = outgoing.y
            incoming.base_x = outgoing.base_x
            incoming.base_y = outgoing.base_y
            incoming.target_x = outgoing.x
            incoming.target_y = outgoing.y

            team.substitutions_used += 1

            self._apply_positions(
                team, attacking_to_right=(side == "home")
            )

            self._event(
                "substitution",
                team=side,
                player=incoming.id,
                outgoing=outgoing.id,
                incoming=incoming.id,
            )

            # If subbed player had the ball, release to nearest teammate.
            if self.ball.owner_id == outgoing.id:
                self.ball.owner_id = None
                self.ball.owner_side = None
                teammate = self._nearest_player(
                    outgoing.x, outgoing.y, side=side, max_distance=20
                )
                if teammate:
                    self._give_ball_to(teammate)
                else:
                    self._reset_ball()

            return self.snapshot()

    # ========================================================
    # SNAPSHOT
    # ========================================================

    def _player_stamina(self):
        result = {}
        for player in self.home.players + self.away.players:
            result[player.id] = round(player.stamina_current, 1)
        return result

    def _snapshot_stats(self):
        return {
            "possession": deepcopy(self.stats["possession"]),
            "shots": deepcopy(self.stats["shots"]),
            "shotsOnTarget": deepcopy(self.stats["shotsOnTarget"]),
            "passes": deepcopy(self.stats["passes"]),
            "passesCompleted": deepcopy(self.stats["passesCompleted"]),
            "tackles": deepcopy(self.stats["tackles"]),
            "corners": deepcopy(self.stats["corners"]),
            "fouls": deepcopy(self.stats["fouls"]),
            "yellowCards": deepcopy(self.stats["yellowCards"]),
            "redCards": deepcopy(self.stats["redCards"]),
            "offsides": deepcopy(self.stats["offsides"]),
        }

    def snapshot(self):
        with self.lock:
            return {
                "ok": True,
                "matchId": self.match_id,
                "status": self.status,
                "running": self.running,
                "finished": self.finished,
                "half": self.half,
                "minute": self.minute(),
                "second": self.second(),
                "clock": self.clock_string(),
                "footballSeconds": round(self.football_seconds, 2),
                "injuryTime": (
                    self.first_half_injury
                    if self.half == 1
                    else self.second_half_injury
                ),
                "score": {
                    "home": self.score["home"],
                    "away": self.score["away"],
                },
                "homeScore": self.score["home"],
                "awayScore": self.score["away"],
                "home": self.home.to_dict(),
                "away": self.away.to_dict(),
                "ball": self.ball.to_dict(),
                "possession": self.possession_side,
                "possessionSide": self.possession_side,
                "stats": self._snapshot_stats(),
                "events": deepcopy(self.events),
                "lastEvent": deepcopy(self.last_event),
                "playerStamina": self._player_stamina(),
                "result": deepcopy(self.result),
            }

    # ========================================================
    # CLEANUP
    # ========================================================

    def destroy(self):
        with self.lock:
            self.destroyed = True
            self.running = False
            self.finished = True
            self.status = "finished"
            self.stop_event.set()


FootballEngine = FootballMatch
