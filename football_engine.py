import copy
import math
import random
import threading
import time
import uuid
from typing import Any


# ============================================================
# MATCH CONSTANTS
# ============================================================

PITCH_W = 100.0
PITCH_H = 60.0

REAL_MATCH_SECONDS = 480.0
FOOTBALL_MINUTES = 90.0

TICK_SECONDS = 0.05

MAX_EVENTS = 300

HOME_DIRECTION = 1
AWAY_DIRECTION = -1


# ============================================================
# DEFAULT TACTICS
# ============================================================

DEFAULT_TACTICS = {
    "mentality": "balanced",
    "tempo": 60,
    "pressing": "medium",
    "defensiveLine": "medium",
    "width": 55,
}


# ============================================================
# FORMATIONS
#
# Coordinates are for HOME.
# Away coordinates are mirrored automatically.
# x = 0 own goal
# x = 100 opponent goal
# y = 0 top touchline
# y = 60 bottom touchline
# ============================================================

FORMATION_POSITIONS = {
    "4-4-2": [
        ("GK", 7, 30),
        ("LB", 22, 8),
        ("CB", 20, 22),
        ("CB", 20, 38),
        ("RB", 22, 52),
        ("LM", 43, 9),
        ("CM", 40, 23),
        ("CM", 40, 37),
        ("RM", 43, 51),
        ("ST", 68, 23),
        ("ST", 68, 37),
    ],

    "4-3-3": [
        ("GK", 7, 30),
        ("LB", 22, 8),
        ("CB", 20, 22),
        ("CB", 20, 38),
        ("RB", 22, 52),
        ("CM", 43, 18),
        ("CM", 40, 30),
        ("CM", 43, 42),
        ("LW", 65, 9),
        ("ST", 70, 30),
        ("RW", 65, 51),
    ],

    "3-5-2": [
        ("GK", 7, 30),
        ("CB", 20, 16),
        ("CB", 19, 30),
        ("CB", 20, 44),
        ("LWB", 42, 7),
        ("CM", 40, 20),
        ("CM", 39, 30),
        ("CM", 40, 40),
        ("RWB", 42, 53),
        ("ST", 68, 23),
        ("ST", 68, 37),
    ],

    "5-3-2": [
        ("GK", 7, 30),
        ("LWB", 30, 7),
        ("CB", 22, 19),
        ("CB", 20, 30),
        ("CB", 22, 41),
        ("RWB", 30, 53),
        ("CM", 44, 19),
        ("CM", 42, 30),
        ("CM", 44, 41),
        ("ST", 69, 23),
        ("ST", 69, 37),
    ],

    "4-2-3-1": [
        ("GK", 7, 30),
        ("LB", 22, 8),
        ("CB", 20, 22),
        ("CB", 20, 38),
        ("RB", 22, 52),
        ("DM", 36, 23),
        ("DM", 36, 37),
        ("LW", 59, 9),
        ("AM", 56, 30),
        ("RW", 59, 51),
        ("ST", 70, 30),
    ],
}


# ============================================================
# ROLE GROUPS
# ============================================================

DEFENDER_ROLES = {
    "GK",
    "LB",
    "RB",
    "CB",
    "LWB",
    "RWB",
}

MIDFIELD_ROLES = {
    "CM",
    "DM",
    "LM",
    "RM",
    "AM",
}

ATTACKING_ROLES = {
    "LW",
    "RW",
    "ST",
}


# ============================================================
# HELPERS
# ============================================================

def clamp(value, low, high):
    return max(low, min(high, value))


def distance(ax, ay, bx, by):
    return math.sqrt(
        ((ax - bx) ** 2) +
        ((ay - by) ** 2)
    )


def lerp(a, b, amount):
    return a + (b - a) * amount


def chance(probability):
    return random.random() < clamp(probability, 0.0, 1.0)


def normalize_name(value):
    return str(value or "").strip()


# ============================================================
# FOOTBALL MATCH
# ============================================================

class FootballMatch:

    def __init__(self, config: dict[str, Any]):
        self.lock = threading.RLock()

        self.match_id = str(
            config.get("matchId") or uuid.uuid4()
        )

        self.running = False
        self.thread = None

        self.status = "ready"

        self.elapsed_real = 0.0

        self.minute = int(
            config.get("minute", 0) or 0
        )

        self.second = int(
            config.get("second", 0) or 0
        )

        self.match_real_seconds = (
            (self.minute * 60.0)
            + self.second
        ) * (
            REAL_MATCH_SECONDS /
            (FOOTBALL_MINUTES * 60.0)
        )

        self.home = self._create_team(
            "home",
            config.get("home", {}),
        )

        self.away = self._create_team(
            "away",
            config.get("away", {}),
        )

        self.score = {
            "home": int(
                config.get("score", {}).get("home", 0)
            ),
            "away": int(
                config.get("score", {}).get("away", 0)
            ),
        }

        self.ball = {
            "x": 50.0,
            "y": 30.0,
            "ownerId": None,
            "ownerSide": None,
            "phase": "kickoff",
            "targetX": 50.0,
            "targetY": 30.0,
            "speed": 0.0,
        }

        self.events = []

        self.possession_seconds = {
            "home": 0.0,
            "away": 0.0,
        }

        self.last_action_at = 0.0

        self.action_cooldown = 0.0

        self.pending_restart = "kickoff"

        self.halftime_done = False

        self.last_goal_time = -999.0

        self.last_corner_time = -999.0

        self.last_shot_time = -999.0

        self.stats = {
            "home": self._empty_stats(),
            "away": self._empty_stats(),
        }

        self._assign_kickoff()

    # ========================================================
    # TEAM CREATION
    # ========================================================

    def _create_team(self, side, data):
        team = {
            "id": str(
                data.get("id")
                or f"{side}-team"
            ),

            "name": normalize_name(
                data.get("name")
                or (
                    "Home FC"
                    if side == "home"
                    else "Away FC"
                )
            ),

            "logo": data.get("logo") or "",

            "formation": (
                data.get("formation")
                or "4-3-3"
            ),

            "tactics": {
                **DEFAULT_TACTICS,
                **(
                    data.get("tactics")
                    or {}
                ),
            },

            "players": [],

            "bench": [],

            "substitutionsUsed": int(
                data.get(
                    "substitutionsUsed",
                    0
                ) or 0
            ),
        }

        raw_players = (
            data.get("players")
            or data.get("lineup")
            or []
        )

        raw_bench = (
            data.get("bench")
            or []
        )

        positions = FORMATION_POSITIONS.get(
            team["formation"],
            FORMATION_POSITIONS["4-3-3"],
        )

        players = []

        for index in range(11):

            raw = (
                raw_players[index]
                if index < len(raw_players)
                else {}
            )

            role, x, y = positions[index]

            player = self._create_player(
                raw,
                index,
                role,
                x,
                y,
                side,
            )

            players.append(player)

        team["players"] = players

        bench = []

        for index, raw in enumerate(raw_bench):

            if not isinstance(raw, dict):
                raw = {}

            bench.append(
                self._create_bench_player(
                    raw,
                    index,
                    side,
                )
            )

        if len(bench) == 0:

            for index in range(7):

                bench.append(
                    self._create_bench_player(
                        {
                            "name": f"Substitute {index + 1}"
                        },
                        index,
                        side,
                    )
                )

        team["bench"] = bench

        return team

    # ========================================================
    # PLAYER CREATION
    # ========================================================

    def _create_player(
        self,
        raw,
        index,
        role,
        x,
        y,
        side,
    ):

        if not isinstance(raw, dict):
            raw = {}

        player_id = str(
            raw.get("id")
            or raw.get("playerId")
            or f"{side}-player-{index + 1}"
        )

        name = normalize_name(
            raw.get("name")
            or raw.get("displayName")
            or f"Player {index + 1}"
        )

        number = int(
            raw.get("number")
            or raw.get("shirtNumber")
            or index + 1
        )

        ratings = {
            "pace": self._rating(
                raw,
                "pace",
                68,
            ),
            "passing": self._rating(
                raw,
                "passing",
                raw.get("pass", 68),
            ),
            "shooting": self._rating(
                raw,
                "shooting",
                65,
            ),
            "dribbling": self._rating(
                raw,
                "dribbling",
                67,
            ),
            "defending": self._rating(
                raw,
                "defending",
                65,
            ),
            "stamina": self._rating(
                raw,
                "stamina",
                75,
            ),
            "strength": self._rating(
                raw,
                "strength",
                70,
            ),
            "vision": self._rating(
                raw,
                "vision",
                68,
            ),
            "goalkeeping": self._rating(
                raw,
                "goalkeeping",
                65,
            ),
        }

        return {
            "id": player_id,
            "name": name,
            "number": number,
            "position": role,
            "role": role,

            "x": float(x),
            "y": float(y),

            "targetX": float(x),
            "targetY": float(y),

            "hasBall": False,

            "onPitch": True,
            "substituted": False,

            "stamina": 100.0,

            "ratings": ratings,

            "lastActionAt": 0.0,

            "shots": 0,
            "shotsOnTarget": 0,
            "goals": 0,

            "passes": 0,
            "successfulPasses": 0,

            "tackles": 0,
            "interceptions": 0,

            "dribbles": 0,
            "successfulDribbles": 0,

            "assists": 0,

            "yellow": False,

            "red": False,
        }

    def _create_bench_player(
        self,
        raw,
        index,
        side,
    ):

        if not isinstance(raw, dict):
            raw = {}

        return {
            "id": str(
                raw.get("id")
                or f"{side}-bench-{index + 1}"
            ),

            "name": normalize_name(
                raw.get("name")
                or f"Substitute {index + 1}"
            ),

            "number": int(
                raw.get("number")
                or index + 12
            ),

            "position": (
                raw.get("position")
                or "SUB"
            ),

            "role": (
                raw.get("role")
                or raw.get("position")
                or "SUB"
            ),

            "onPitch": False,

            "substituted": False,

            "ratings": {
                "pace": self._rating(
                    raw,
                    "pace",
                    68,
                ),
                "passing": self._rating(
                    raw,
                    "passing",
                    68,
                ),
                "shooting": self._rating(
                    raw,
                    "shooting",
                    65,
                ),
                "dribbling": self._rating(
                    raw,
                    "dribbling",
                    67,
                ),
                "defending": self._rating(
                    raw,
                    "defending",
                    65,
                ),
                "stamina": self._rating(
                    raw,
                    "stamina",
                    75,
                ),
                "strength": self._rating(
                    raw,
                    "strength",
                    70,
                ),
                "vision": self._rating(
                    raw,
                    "vision",
                    68,
                ),
                "goalkeeping": self._rating(
                    raw,
                    "goalkeeping",
                    65,
                ),
            },

            "stamina": 100.0,
        }

    def _rating(self, raw, key, default):
        try:
            value = raw.get(key, default)

            if value is None:
                return float(default)

            return float(
                clamp(
                    float(value),
                    1,
                    100,
                )
            )

        except Exception:
            return float(default)

    # ========================================================
    # STATS
    # ========================================================

    def _empty_stats(self):
        return {
            "shots": 0,
            "shotsOnTarget": 0,
            "goals": 0,
            "corners": 0,
            "fouls": 0,
            "offsides": 0,
            "passes": 0,
            "successfulPasses": 0,
            "tackles": 0,
            "interceptions": 0,
            "dribbles": 0,
            "possession": 50,
        }

    # ========================================================
    # KICKOFF
    # ========================================================

    def _assign_kickoff(self):

        self.ball["x"] = 50.0
        self.ball["y"] = 30.0
        self.ball["phase"] = "kickoff"

        home_mid = self._find_role(
            self.home,
            {"CM", "AM", "ST"},
        )

        if home_mid:
            self.ball["ownerId"] = home_mid["id"]
            self.ball["ownerSide"] = "home"
            home_mid["hasBall"] = True
            return

        away_mid = self._find_role(
            self.away,
            {"CM", "AM", "ST"},
        )

        if away_mid:
            self.ball["ownerId"] = away_mid["id"]
            self.ball["ownerSide"] = "away"
            away_mid["hasBall"] = True

    # ========================================================
    # START
    # ========================================================

    def start(self):

        with self.lock:

            if self.status == "finished":
                return self.snapshot()

            if self.running:
                return self.snapshot()

            self.running = True
            self.status = "playing"

            self.thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
            )

            self.thread.start()

            self._event(
                "match",
                "Match started",
                0,
            )

            return self.snapshot()

    # ========================================================
    # PAUSE
    # ========================================================

    def pause(self):

        with self.lock:
            self.running = False

            if self.status == "playing":
                self.status = "paused"

            return self.snapshot()

    # ========================================================
    # RUN LOOP
    # ========================================================

    def _run_loop(self):

        previous = time.monotonic()

        while True:

            with self.lock:

                if not self.running:
                    break

                if self.status == "finished":
                    self.running = False
                    break

                now = time.monotonic()

                dt = now - previous
                previous = now

                dt = clamp(
                    dt,
                    0.01,
                    0.20,
                )

                self.advance(dt)

            time.sleep(TICK_SECONDS)

    # ========================================================
    # ADVANCE MATCH
    # ========================================================

    def advance(self, real_dt):

        if self.status != "playing":
            return

        self.elapsed_real += real_dt

        self.match_real_seconds += real_dt

        football_seconds = (
            self.match_real_seconds
            * (
                FOOTBALL_MINUTES * 60
                / REAL_MATCH_SECONDS
            )
        )

        football_seconds = clamp(
            football_seconds,
            0,
            90 * 60,
        )

        self.minute = int(
            football_seconds // 60
        )

        self.second = int(
            football_seconds % 60
        )

        if self.minute >= 45 and not self.halftime_done:

            self.halftime_done = True

            self.status = "halftime"

            self.running = False

            self._event(
                "halftime",
                "Half time",
                self.minute,
            )

            return

        if self.minute >= 90:

            self.finish()

            return

        self._update_possession(
            real_dt
        )

        self._update_stamina(
            real_dt
        )

        self._update_ball(
            real_dt
        )

        self._update_players(
            real_dt
        )

        self._handle_restart()

        self.action_cooldown -= real_dt

        if self.action_cooldown <= 0:

            self.action_cooldown = (
                self._action_interval()
            )

            self._make_match_action()

    # ========================================================
    # ACTION SPEED
    # ========================================================

    def _action_interval(self):

        tempo_home = float(
            self.home["tactics"].get(
                "tempo",
                60,
            )
        )

        tempo_away = float(
            self.away["tactics"].get(
                "tempo",
                60,
            )
        )

        tempo = (
            tempo_home +
            tempo_away
        ) / 2

        return clamp(
            0.65 - (tempo / 100) * 0.25,
            0.35,
            0.75,
        )

    # ========================================================
    # POSSESSION
    # ========================================================

    def _update_possession(self, dt):

        owner_side = self.ball.get(
            "ownerSide"
        )

        if owner_side in {
            "home",
            "away",
        }:

            self.possession_seconds[
                owner_side
            ] += dt

    # ========================================================
    # STAMINA
    # ========================================================

    def _update_stamina(self, dt):

        for side in (
            "home",
            "away",
        ):

            team = self._team(side)

            pressing = team["tactics"].get(
                "pressing",
                "medium",
            )

            pressure = {
                "low": 0.45,
                "medium": 0.75,
                "high": 1.10,
            }.get(
                pressing,
                0.75,
            )

            for player in team["players"]:

                if not player["onPitch"]:
                    continue

                base = (
                    0.0025
                    * pressure
                )

                if player["hasBall"]:
                    base *= 1.25

                player["stamina"] = clamp(
                    player["stamina"]
                    - (
                        base
                        * dt
                        * 10
                    ),
                    40,
                    100,
                )

    # ========================================================
    # PLAYER MOVEMENT
    # ========================================================

    def _update_players(self, dt):

        for side in (
            "home",
            "away",
        ):

            team = self._team(side)

            for player in team["players"]:

                if not player["onPitch"]:
                    continue

                self._calculate_target(
                    side,
                    player,
                )

                self._move_player(
                    player,
                    dt,
                )

    # ========================================================
    # TARGET CALCULATION
    # ========================================================

    def _calculate_target(
        self,
        side,
        player,
    ):

        team = self._team(side)
        opponent = self._opponent(side)

        role = player["role"]

        direction = (
            1
            if side == "home"
            else -1
        )

        ball_x = self.ball["x"]
        ball_y = self.ball["y"]

        own_x = (
            ball_x
            if direction == 1
            else 100 - ball_x
        )

        # ----------------------------------------------------
        # Base formation position
        # ----------------------------------------------------

        base_x, base_y = (
            self._base_position(
                team,
                player,
            )
        )

        target_x = base_x
        target_y = base_y

        # ----------------------------------------------------
        # How attacking is the team?
        # ----------------------------------------------------

        mentality = team["tactics"].get(
            "mentality",
            "balanced",
        )

        mentality_push = {
            "defensive": -7,
            "balanced": 2,
            "attacking": 9,
        }.get(
            mentality,
            2,
        )

        # ----------------------------------------------------
        # If team owns the ball
        # ----------------------------------------------------

        owns_ball = (
            self.ball.get("ownerSide")
            == side
        )

        # ----------------------------------------------------
        # DEFENDERS
        # ----------------------------------------------------

        if role in DEFENDER_ROLES:

            target_x = base_x

            defensive_line = team[
                "tactics"
            ].get(
                "defensiveLine",
                "medium",
            )

            line_push = {
                "low": -4,
                "medium": 0,
                "high": 6,
            }.get(
                defensive_line,
                0,
            )

            if owns_ball:
                target_x += (
                    mentality_push * 0.35
                )

            else:
                target_x += line_push

                if own_x > 45:
                    target_x += 3

            # Fullbacks overlap more
            if role in {
                "LB",
                "RB",
                "LWB",
                "RWB",
            } and owns_ball:

                target_x += 7

        # ----------------------------------------------------
        # MIDFIELDERS
        # ----------------------------------------------------

        elif role in MIDFIELD_ROLES:

            if owns_ball:

                # Midfield follows the attack
                target_x = (
                    base_x
                    + mentality_push
                    + max(
                        0,
                        (own_x - 35) * 0.30,
                    )
                )

                # AM attacks box strongly
                if role == "AM":
                    target_x += 8

            else:

                target_x = (
                    base_x
                    + (
                        (own_x - 45)
                        * 0.20
                    )
                )

                # Recover behind ball
                if own_x < 35:
                    target_x -= 3

        # ----------------------------------------------------
        # ATTACKERS
        # ----------------------------------------------------

        elif role in ATTACKING_ROLES:

            if owns_ball:

                # Attackers must get forward.
                target_x = max(
                    base_x + 8,
                    70 + mentality_push,
                )

                # Striker attacks penalty box
                if role == "ST":

                    if own_x >= 50:
                        target_x = 82

                    if own_x >= 68:
                        target_x = 87

                    target_y = (
                        30
                        + (
                            ball_y - 30
                        ) * 0.35
                    )

                # Wingers attack space
                elif role in {
                    "LW",
                    "RW",
                }:

                    target_x = 78

                    if role == "LW":
                        target_y = 10

                    else:
                        target_y = 50

                    # Cut inside when ball is central
                    if 25 < ball_y < 35:
                        target_y = (
                            21
                            if role == "LW"
                            else 39
                        )

            else:

                # Attackers stay dangerous
                # instead of dropping too deep.
                target_x = max(
                    base_x,
                    66,
                )

                if role == "ST":

                    target_x = 72

                    # Run behind defensive line
                    if own_x > 48:
                        target_x = 82

                elif role == "LW":

                    target_x = 70
                    target_y = 11

                elif role == "RW":

                    target_x = 70
                    target_y = 49

        # ----------------------------------------------------
        # BALL PROXIMITY
        # ----------------------------------------------------

        if owns_ball:

            ball_distance = distance(
                player["x"],
                player["y"],
                ball_x,
                ball_y,
            )

            if (
                ball_distance < 16
                and role not in {
                    "ST",
                    "LW",
                    "RW",
                }
            ):

                target_x = lerp(
                    target_x,
                    ball_x,
                    0.25,
                )

                target_y = lerp(
                    target_y,
                    ball_y,
                    0.25,
                )

        # ----------------------------------------------------
        # SUPPORT THE BALL CARRIER
        # ----------------------------------------------------

        if owns_ball:

            owner = self._get_ball_owner()

            if owner and owner["id"] != player["id"]:

                owner_distance = distance(
                    player["x"],
                    player["y"],
                    owner["x"],
                    owner["y"],
                )

                if (
                    role in MIDFIELD_ROLES
                    and owner_distance > 9
                ):

                    target_x = lerp(
                        target_x,
                        owner["x"],
                        0.20,
                    )

                    target_y = lerp(
                        target_y,
                        owner["y"],
                        0.12,
                    )

        # ----------------------------------------------------
        # PRESSING
        # ----------------------------------------------------

        opponent_has_ball = (
            self.ball.get("ownerSide")
            == opponent
        )

        if opponent_has_ball:

            pressing = team["tactics"].get(
                "pressing",
                "medium",
            )

            press_distance = {
                "low": 14,
                "medium": 20,
                "high": 28,
            }.get(
                pressing,
                20,
            )

            if role in {
                "ST",
                "LW",
                "RW",
                "AM",
                "CM",
            }:

                target_x = lerp(
                    target_x,
                    ball_x,
                    0.55,
                )

                target_y = lerp(
                    target_y,
                    ball_y,
                    0.45,
                )

                if distance(
                    player["x"],
                    player["y"],
                    ball_x,
                    ball_y,
                ) < press_distance:

                    target_x = ball_x
                    target_y = ball_y

        # ----------------------------------------------------
        # WIDTH
        # ----------------------------------------------------

        width = float(
            team["tactics"].get(
                "width",
                55,
            )
        )

        width_factor = (
            width / 100
        )

        if role in {
            "LW",
            "RW",
            "LM",
            "RM",
            "LB",
            "RB",
            "LWB",
            "RWB",
        }:

            center = 30

            if role in {
                "LW",
                "LM",
                "LB",
                "LWB",
            }:
                target_y = lerp(
                    target_y,
                    5,
                    width_factor * 0.25,
                )

            else:
                target_y = lerp(
                    target_y,
                    55,
                    width_factor * 0.25,
                )

        # ----------------------------------------------------
        # KEEP INSIDE PITCH
        # ----------------------------------------------------

        player["targetX"] = clamp(
            target_x,
            4,
            96,
        )

        player["targetY"] = clamp(
            target_y,
            3,
            57,
        )

    # ========================================================
    # BASE POSITION
    # ========================================================

    def _base_position(
        self,
        team,
        player,
    ):

        formation = team["formation"]

        positions = FORMATION_POSITIONS.get(
            formation,
            FORMATION_POSITIONS["4-3-3"],
        )

        index = next(
            (
                i
                for i, p in enumerate(
                    team["players"]
                )
                if p["id"] == player["id"]
            ),
            0,
        )

        _, x, y = positions[
            min(
                index,
                len(positions) - 1,
            )
        ]

        if team is self.away:
            x = 100 - x

        return float(x), float(y)

    # ========================================================
    # PLAYER MOVEMENT
    # ========================================================

    def _move_player(
        self,
        player,
        dt,
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
            dx * dx + dy * dy
        )

        if dist < 0.2:
            return

        pace = float(
            player["ratings"].get(
                "pace",
                68,
            )
        )

        stamina_factor = (
            0.65
            + (
                player["stamina"]
                / 100
            ) * 0.35
        )

        speed = (
            4.0
            + (
                pace / 100
            ) * 3.2
        )

        speed *= stamina_factor

        step = speed * dt

        if step >= dist:

            player["x"] = player["targetX"]
            player["y"] = player["targetY"]

        else:

            player["x"] += (
                dx / dist
            ) * step

            player["y"] += (
                dy / dist
            ) * step

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

    def _update_ball(self, dt):

        if self.ball["phase"] != "pass":
            return

        tx = self.ball["targetX"]
        ty = self.ball["targetY"]

        dx = tx - self.ball["x"]
        dy = ty - self.ball["y"]

        dist = math.sqrt(
            dx * dx + dy * dy
        )

        if dist < 0.8:

            self.ball["x"] = tx
            self.ball["y"] = ty

            self._receive_ball()

            return

        speed = max(
            self.ball["speed"],
            20,
        )

        step = speed * dt

        if step >= dist:

            self.ball["x"] = tx
            self.ball["y"] = ty

            self._receive_ball()

        else:

            self.ball["x"] += (
                dx / dist
            ) * step

            self.ball["y"] += (
                dy / dist
            ) * step

    # ========================================================
    # RECEIVE PASS
    # ========================================================

    def _receive_ball(self):

        target_id = self.ball.get(
            "targetPlayerId"
        )

        side = self.ball.get(
            "ownerSide"
        )

        if not target_id or not side:
            return

        team = self._team(side)

        target = next(
            (
                p
                for p in team["players"]
                if p["id"] == target_id
                and p["onPitch"]
            ),
            None,
        )

        if target:

            self._clear_ball_owners()

            target["hasBall"] = True

            self.ball["ownerId"] = (
                target["id"]
            )

            self.ball["ownerSide"] = side

            self.ball["phase"] = "controlled"

            self.ball["x"] = target["x"]
            self.ball["y"] = target["y"]

            return

        self._loose_ball()

    # ========================================================
    # MATCH ACTION
    # ========================================================

    def _make_match_action(self):

        owner = self._get_ball_owner()

        if not owner:

            self._recover_loose_ball()

            return

        side = self.ball["ownerSide"]

        team = self._team(side)

        opponent = self._opponent(side)

        direction = (
            1
            if side == "home"
            else -1
        )

        attacking_x = (
            self.ball["x"]
            if direction == 1
            else 100 - self.ball["x"]
        )

        # ----------------------------------------------------
        # DEFENDER PRESSURE
        # ----------------------------------------------------

        defenders = self._nearby_opponents(
            side,
            self.ball["x"],
            self.ball["y"],
            12,
        )

        pressure = len(defenders)

        # ----------------------------------------------------
        # SHOOTING ZONE
        # ----------------------------------------------------

        if self._is_shooting_position(
            side,
            owner,
        ):

            if self._should_shoot(
                side,
                owner,
                pressure,
            ):

                self._shoot(
                    side,
                    owner,
                )

                return

        # ----------------------------------------------------
        # CROSSING
        # ----------------------------------------------------

        if self._is_crossing_position(
            side,
            owner,
        ):

            if chance(
                self._cross_probability(
                    owner,
                    attacking_x,
                )
            ):

                self._cross(
                    side,
                    owner,
                )

                return

        # ----------------------------------------------------
        # THROUGH BALL
        # ----------------------------------------------------

        runner = self._best_forward_runner(
            side,
            owner,
        )

        if runner:

            if self._should_through_ball(
                side,
                owner,
                runner,
                attacking_x,
            ):

                self._pass(
                    side,
                    owner,
                    runner,
                    through=True,
                )

                return

        # ----------------------------------------------------
        # DRIBBLE FORWARD
        # ----------------------------------------------------

        if (
            attacking_x > 45
            and self._has_space_ahead(
                side,
                owner,
            )
        ):

            if chance(
                self._dribble_probability(
                    owner,
                    pressure,
                )
            ):

                self._dribble(
                    side,
                    owner,
                )

                return

        # ----------------------------------------------------
        # NORMAL PASS
        # ----------------------------------------------------

        receiver = self._best_pass_target(
            side,
            owner,
        )

        if receiver:

            self._pass(
                side,
                owner,
                receiver,
                through=False,
            )

            return

        # ----------------------------------------------------
        # MOVE FORWARD WITH BALL
        # ----------------------------------------------------

        self._dribble(
            side,
            owner,
        )

    # ========================================================
    # SHOOTING POSITION
    # ========================================================

    def _is_shooting_position(
        self,
        side,
        player,
    ):

        direction = (
            1
            if side == "home"
            else -1
        )

        attacking_x = (
            player["x"]
            if direction == 1
            else 100 - player["x"]
        )

        center_distance = abs(
            player["y"] - 30
        )

        return (
            attacking_x >= 76
            and center_distance <= 23
        )

    # ========================================================
    # SHOULD SHOOT
    # ========================================================

    def _should_shoot(
        self,
        side,
        player,
        pressure,
    ):

        direction = (
            1
            if side == "home"
            else -1
        )

        attacking_x = (
            player["x"]
            if direction == 1
            else 100 - player["x"]
        )

        distance_to_goal = (
            100 - attacking_x
        )

        shooting = (
            player["ratings"]["shooting"]
            / 100
        )

        mentality = self._team(
            side
        )["tactics"].get(
            "mentality",
            "balanced",
        )

        mentality_bonus = {
            "defensive": -0.12,
            "balanced": 0.03,
            "attacking": 0.16,
        }.get(
            mentality,
            0.03,
        )

        if attacking_x >= 88:

            base = 0.68

        elif attacking_x >= 82:

            base = 0.48

        else:

            base = 0.22

        distance_bonus = clamp(
            (
                25 - distance_to_goal
            ) / 25,
            0,
            1,
        ) * 0.18

        pressure_penalty = (
            pressure * 0.06
        )

        probability = (
            base
            + shooting * 0.25
            + distance_bonus
            + mentality_bonus
            - pressure_penalty
        )

        return chance(
            clamp(
                probability,
                0.05,
                0.92,
            )
        )

    # ========================================================
    # SHOOT
    # ========================================================

    def _shoot(
        self,
        side,
        player,
    ):

        if self.elapsed_real - self.last_shot_time < 0.35:
            return

        self.last_shot_time = self.elapsed_real

        team = self._team(side)
        opponent = self._opponent(side)

        direction = (
            1
            if side == "home"
            else -1
        )

        attacking_x = (
            player["x"]
            if direction == 1
            else 100 - player["x"]
        )

        distance_to_goal = (
            100 - attacking_x
        )

        shooting = (
            player["ratings"]["shooting"]
        )

        keeper = self._goalkeeper(
            opponent
        )

        keeper_rating = (
            keeper["ratings"].get(
                "goalkeeping",
                65,
            )
            if keeper
            else 65
        )

        angle_bonus = (
            1
            - (
                abs(
                    player["y"] - 30
                )
                / 30
            )
        )

        pressure = len(
            self._nearby_opponents(
                side,
                player["x"],
                player["y"],
                9,
            )
        )

        quality = (
            0.18
            + (
                shooting / 100
            ) * 0.48
            + angle_bonus * 0.18
            - (
                distance_to_goal
                / 30
            ) * 0.15
            - pressure * 0.025
            - (
                keeper_rating / 100
            ) * 0.16
        )

        quality = clamp(
            quality,
            0.04,
            0.82,
        )

        player["shots"] += 1

        team["stats"]["shots"] += 1

        self._event(
            "shot",
            f"{player['name']} takes a shot",
            self.minute,
            side=side,
            playerId=player["id"],
            playerName=player["name"],
        )

        # On target probability
        on_target_probability = clamp(
            0.35
            + (
                shooting / 100
            ) * 0.45
            + angle_bonus * 0.15
            - pressure * 0.04,
            0.18,
            0.92,
        )

        on_target = chance(
            on_target_probability
        )

        if on_target:

            player["shotsOnTarget"] += 1

            team["stats"][
                "shotsOnTarget"
            ] += 1

        # Goal probability
        if on_target and chance(quality):

            self._goal(
                side,
                player,
            )

            return

        if on_target:

            self._save(
                opponent,
                player,
            )

            return

        # Miss
        if chance(0.55):

            self._corner_or_goal_kick(
                side,
                player,
                blocked=False,
            )

        else:

            self._event(
                "miss",
                f"{player['name']} misses the target",
                self.minute,
                side=side,
                playerId=player["id"],
            )

            self._set_goal_kick(
                opponent
            )

    # ========================================================
    # GOAL
    # ========================================================

    def _goal(
        self,
        side,
        scorer,
    ):

        if (
            self.elapsed_real
            - self.last_goal_time
            < 0.5
        ):
            return

        self.last_goal_time = (
            self.elapsed_real
        )

        self.score[side] += 1

        scorer["goals"] += 1

        self._team(side)[
            "stats"
        ]["goals"] += 1

        self._event(
            "goal",
            f"GOAL! {scorer['name']} scores",
            self.minute,
            side=side,
            playerId=scorer["id"],
            playerName=scorer["name"],
        )

        self.ball["ownerId"] = None
        self.ball["ownerSide"] = None
        self.ball["phase"] = "goal"

        self._clear_ball_owners()

        opponent = self._opponent(side)

        self._reset_positions(
            opponent
        )

        self._assign_kickoff_to(
            opponent
        )

    # ========================================================
    # GOALKEEPER SAVE
    # ========================================================

    def _save(
        self,
        defending_team,
        shooter,
    ):

        keeper = self._goalkeeper(
            defending_team
        )

        if keeper:

            self._event(
                "save",
                f"{keeper['name']} makes a save",
                self.minute,
                side=(
                    "away"
                    if defending_team is self.away
                    else "home"
                ),
                playerId=keeper["id"],
                playerName=keeper["name"],
            )

        self._set_goal_kick(
            defending_team
        )

    # ========================================================
    # PASSING
    # ========================================================

    def _pass(
        self,
        side,
        passer,
        receiver,
        through=False,
    ):

        team = self._team(side)

        passing = (
            passer["ratings"]["passing"]
        )

        vision = (
            passer["ratings"]["vision"]
        )

        pressure = len(
            self._nearby_opponents(
                side,
                passer["x"],
                passer["y"],
                10,
            )
        )

        forward_bonus = 0.0

        direction = (
            1
            if side == "home"
            else -1
        )

        passer_attacking_x = (
            passer["x"]
            if direction == 1
            else 100 - passer["x"]
        )

        receiver_attacking_x = (
            receiver["x"]
            if direction == 1
            else 100 - receiver["x"]
        )

        if (
            receiver_attacking_x
            > passer_attacking_x
        ):

            forward_bonus = 0.14

        probability = (
            0.60
            + (
                passing / 100
            ) * 0.28
            + (
                vision / 100
            ) * 0.10
            + forward_bonus
            - pressure * 0.035
        )

        if through:

            probability -= 0.10

        probability = clamp(
            probability,
            0.35,
            0.96,
        )

        passer["passes"] += 1

        team["stats"]["passes"] += 1

        self._clear_ball_owners()

        if chance(probability):

            passer["successfulPasses"] += 1

            team["stats"][
                "successfulPasses"
            ] += 1

            target_x = receiver["x"]
            target_y = receiver["y"]

            if through:

                target_x += (
                    5
                    if side == "home"
                    else -5
                )

                target_x = clamp(
                    target_x,
                    3,
                    97,
                )

            self.ball["phase"] = "pass"

            self.ball["ownerId"] = passer["id"]

            self.ball["ownerSide"] = side

            self.ball["targetPlayerId"] = (
                receiver["id"]
            )

            self.ball["targetX"] = target_x
            self.ball["targetY"] = target_y

            self.ball["speed"] = (
                28
                if through
                else 22
            )

            self._event(
                "pass",
                (
                    f"{passer['name']} "
                    f"{'plays a through ball to' if through else 'passes to'} "
                    f"{receiver['name']}"
                ),
                self.minute,
                side=side,
                playerId=passer["id"],
                targetId=receiver["id"],
            )

        else:

            self._event(
                "bad_pass",
                f"{passer['name']} loses the ball",
                self.minute,
                side=side,
                playerId=passer["id"],
            )

            self._loose_ball()

            self._attempt_interception(
                side,
                passer["x"],
                passer["y"],
            )

    # ========================================================
    # BEST PASS TARGET
    # ========================================================

    def _best_pass_target(
        self,
        side,
        passer,
    ):

        team = self._team(side)

        candidates = []

        direction = (
            1
            if side == "home"
            else -1
        )

        for player in team["players"]:

            if not player["onPitch"]:
                continue

            if player["id"] == passer["id"]:
                continue

            d = distance(
                passer["x"],
                passer["y"],
                player["x"],
                player["y"],
            )

            if d > 30:
                continue

            receiver_attacking_x = (
                player["x"]
                if direction == 1
                else 100 - player["x"]
            )

            passer_attacking_x = (
                passer["x"]
                if direction == 1
                else 100 - passer["x"]
            )

            forward = (
                receiver_attacking_x
                - passer_attacking_x
            )

            openness = (
                self._space_score(
                    side,
                    player,
                )
            )

            attack_value = (
                forward * 1.6
                + openness * 12
                - d * 0.30
            )

            # Strong preference for players ahead
            if forward > 5:
                attack_value += 16

            if player["role"] in {
                "ST",
                "LW",
                "RW",
            }:
                attack_value += 8

            candidates.append(
                (
                    attack_value,
                    player,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return candidates[0][1]

    # ========================================================
    # FORWARD RUNNER
    # ========================================================

    def _best_forward_runner(
        self,
        side,
        passer,
    ):

        team = self._team(side)

        direction = (
            1
            if side == "home"
            else -1
        )

        passer_x = (
            passer["x"]
            if direction == 1
            else 100 - passer["x"]
        )

        candidates = []

        for player in team["players"]:

            if not player["onPitch"]:
                continue

            if player["id"] == passer["id"]:
                continue

            if player["role"] not in {
                "ST",
                "LW",
                "RW",
                "AM",
            }:
                continue

            player_x = (
                player["x"]
                if direction == 1
                else 100 - player["x"]
            )

            forward = (
                player_x - passer_x
            )

            if forward < 5:
                continue

            space = self._space_score(
                side,
                player,
            )

            score = (
                forward * 1.5
                + space * 20
            )

            if player["role"] == "ST":
                score += 8

            candidates.append(
                (
                    score,
                    player,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        return candidates[0][1]

    # ========================================================
    # THROUGH BALL DECISION
    # ========================================================

    def _should_through_ball(
        self,
        side,
        passer,
        runner,
        attacking_x,
    ):

        if attacking_x < 48:
            return False

        runner_space = self._space_score(
            side,
            runner,
        )

        vision = (
            passer["ratings"]["vision"]
            / 100
        )

        passing = (
            passer["ratings"]["passing"]
            / 100
        )

        probability = (
            0.08
            + vision * 0.22
            + passing * 0.15
            + runner_space * 0.45
        )

        if attacking_x > 68:
            probability += 0.12

        return chance(
            clamp(
                probability,
                0.08,
                0.75,
            )
        )

    # ========================================================
    # SPACE SCORE
    # ========================================================

    def _space_score(
        self,
        side,
        player,
    ):

        opponents = self._opponent(
            side
        )["players"]

        nearest = 99.0

        for defender in opponents:

            if not defender["onPitch"]:
                continue

            d = distance(
                player["x"],
                player["y"],
                defender["x"],
                defender["y"],
            )

            nearest = min(
                nearest,
                d,
            )

        return clamp(
            nearest / 18,
            0,
            1,
        )

    # ========================================================
    # DRIBBLE
    # ========================================================

    def _has_space_ahead(
        self,
        side,
        player,
    ):

        direction = (
            1
            if side == "home"
            else -1
        )

        for defender in self._opponent(
            side
        )["players"]:

            if not defender["onPitch"]:
                continue

            d = distance(
                player["x"],
                player["y"],
                defender["x"],
                defender["y"],
            )

            if d > 10:
                continue

            defender_direction_x = (
                defender["x"]
                - player["x"]
            ) * direction

            if defender_direction_x > 0:
                return False

        return True

    def _dribble_probability(
        self,
        player,
        pressure,
    ):

        dribbling = (
            player["ratings"]["dribbling"]
            / 100
        )

        pace = (
            player["ratings"]["pace"]
            / 100
        )

        return clamp(
            0.16
            + dribbling * 0.28
            + pace * 0.12
            - pressure * 0.08,
            0.05,
            0.72,
        )

    def _dribble(
        self,
        side,
        player,
    ):

        direction = (
            1
            if side == "home"
            else -1
        )

        opponents = self._nearby_opponents(
            side,
            player["x"],
            player["y"],
            10,
        )

        pressure = len(opponents)

        success_probability = clamp(
            0.48
            + (
                player["ratings"]["dribbling"]
                / 100
            ) * 0.35
            - pressure * 0.08,
            0.12,
            0.90,
        )

        player["dribbles"] += 1

        if chance(success_probability):

            player["successfulDribbles"] += 1

            self._team(side)[
                "stats"
            ]["dribbles"] += 1

            advance = random.uniform(
                2.0,
                5.5,
            )

            player["x"] += (
                advance * direction
            )

            player["x"] = clamp(
                player["x"],
                3,
                97,
            )

            self.ball["x"] = player["x"]
            self.ball["y"] = player["y"]

            self._event(
                "dribble",
                f"{player['name']} beats a defender",
                self.minute,
                side=side,
                playerId=player["id"],
            )

        else:

            self._event(
                "tackle",
                f"{player['name']} is dispossessed",
                self.minute,
                side=side,
                playerId=player["id"],
            )

            self._attempt_tackle(
                side,
                player,
            )

    # ========================================================
    # CROSS
    # ========================================================

    def _is_crossing_position(
        self,
        side,
        player,
    ):

        direction = (
            1
            if side == "home"
            else -1
        )

        attacking_x = (
            player["x"]
            if direction == 1
            else 100 - player["x"]
        )

        wide = (
            player["y"] < 17
            or player["y"] > 43
        )

        return (
            attacking_x >= 68
            and wide
        )

    def _cross_probability(
        self,
        player,
        attacking_x,
    ):

        passing = (
            player["ratings"]["passing"]
            / 100
        )

        return clamp(
            0.18
            + passing * 0.30
            + (
                attacking_x
                / 100
            ) * 0.20,
            0.15,
            0.65,
        )

    def _cross(
        self,
        side,
        player,
    ):

        attackers = [
            p
            for p in self._team(side)["players"]
            if p["onPitch"]
            and p["role"] in {
                "ST",
                "AM",
                "LW",
                "RW",
            }
        ]

        if not attackers:
            return

        target = min(
            attackers,
            key=lambda p: abs(
                p["x"]
                - (
                    86
                    if side == "home"
                    else 14
                )
            )
            + abs(
                p["y"] - 30
            ) * 0.3,
        )

        self._event(
            "cross",
            f"{player['name']} sends a cross into the box",
            self.minute,
            side=side,
            playerId=player["id"],
            targetId=target["id"],
        )

        self._clear_ball_owners()

        self.ball["phase"] = "pass"

        self.ball["ownerSide"] = side

        self.ball["ownerId"] = player["id"]

        self.ball["targetPlayerId"] = (
            target["id"]
        )

        self.ball["targetX"] = (
            88
            if side == "home"
            else 12
        )

        self.ball["targetY"] = clamp(
            target["y"]
            + random.uniform(
                -7,
                7,
            ),
            8,
            52,
        )

        self.ball["speed"] = 24

        # Immediate box contest
        if chance(0.62):

            if chance(
                (
                    target["ratings"]["shooting"]
                    / 100
                ) * 0.52
            ):

                self._header_shot(
                    side,
                    target,
                )

            else:

                self._clear_cross(
                    side
                )

        else:

            self._clear_cross(
                side
            )

    # ========================================================
    # HEADER
    # ========================================================

    def _header_shot(
        self,
        side,
        player,
    ):

        self._clear_ball_owners()

        shooting = (
            player["ratings"]["shooting"]
        )

        opponent = self._opponent(side)

        keeper = self._goalkeeper(
            opponent
        )

        keeper_rating = (
            keeper["ratings"]["goalkeeping"]
            if keeper
            else 65
        )

        probability = clamp(
            0.12
            + (
                shooting / 100
            ) * 0.28
            - (
                keeper_rating / 100
            ) * 0.10,
            0.05,
            0.50,
        )

        self._team(side)[
            "stats"
        ]["shots"] += 1

        player["shots"] += 1

        self._event(
            "header",
            f"{player['name']} heads towards goal",
            self.minute,
            side=side,
            playerId=player["id"],
        )

        if chance(probability):

            self._goal(
                side,
                player,
            )

        else:

            self._set_goal_kick(
                opponent
            )

    # ========================================================
    # CLEAR CROSS
    # ========================================================

    def _clear_cross(
        self,
        attacking_side,
    ):

        defending_side = self._opponent(
            attacking_side
        )

        self._event(
            "clearance",
            "Defence clears the cross",
            self.minute,
        )

        if chance(0.35):

            self._set_corner(
                attacking_side
            )

        else:

            self._set_goal_kick(
                defending_side
            )

    # ========================================================
    # TACKLE
    # ========================================================

    def _attempt_tackle(
        self,
        attacking_side,
        attacker,
    ):

        defenders = self._nearby_opponents(
            attacking_side,
            attacker["x"],
            attacker["y"],
            9,
        )

        if not defenders:

            self._loose_ball()
            return

        defender = min(
            defenders,
            key=lambda p: distance(
                p["x"],
                p["y"],
                attacker["x"],
                attacker["y"],
            ),
        )

        defending_side = self._opponent(
            attacking_side
        )

        tackle_rating = (
            defender["ratings"]["defending"]
            / 100
        )

        attacker_rating = (
            attacker["ratings"]["dribbling"]
            / 100
        )

        probability = clamp(
            0.45
            + tackle_rating * 0.30
            - attacker_rating * 0.18,
            0.15,
            0.85,
        )

        if chance(probability):

            defender["tackles"] += 1

            defending_side["stats"][
                "tackles"
            ] += 1

            self._clear_ball_owners()

            defender["hasBall"] = True

            self.ball["ownerId"] = (
                defender["id"]
            )

            self.ball["ownerSide"] = (
                "home"
                if attacking_side == "away"
                else "away"
            )

            self.ball["phase"] = "controlled"

            self.ball["x"] = defender["x"]
            self.ball["y"] = defender["y"]

            self._event(
                "tackle",
                f"{defender['name']} wins the ball",
                self.minute,
                side=self.ball["ownerSide"],
                playerId=defender["id"],
            )

        else:

            self._loose_ball()

    # ========================================================
    # INTERCEPTION
    # ========================================================

    def _attempt_interception(
        self,
        attacking_side,
        x,
        y,
    ):

        defending_side = self._opponent(
            attacking_side
        )

        defenders = self._nearby_opponents(
            attacking_side,
            x,
            y,
            8,
        )

        if not defenders:
            return

        defender = min(
            defenders,
            key=lambda p: distance(
                p["x"],
                p["y"],
                x,
                y,
            ),
        )

        if chance(
            (
                defender["ratings"]["defending"]
                / 100
            ) * 0.65
        ):

            defender["interceptions"] += 1

            defending_side["stats"][
                "interceptions"
            ] += 1

            self._clear_ball_owners()

            defender["hasBall"] = True

            self.ball["ownerId"] = (
                defender["id"]
            )

            self.ball["ownerSide"] = (
                "home"
                if attacking_side == "away"
                else "away"
            )

            self.ball["phase"] = "controlled"

            self.ball["x"] = defender["x"]
            self.ball["y"] = defender["y"]

    # ========================================================
    # NEARBY OPPONENTS
    # ========================================================

    def _nearby_opponents(
        self,
        side,
        x,
        y,
        radius,
    ):

        opponent = self._opponent(
            side
        )

        return [
            p
            for p in opponent["players"]
            if p["onPitch"]
            and distance(
                p["x"],
                p["y"],
                x,
                y,
            ) <= radius
        ]

    # ========================================================
    # BALL OWNER
    # ========================================================

    def _get_ball_owner(self):

        owner_id = self.ball.get(
            "ownerId"
        )

        side = self.ball.get(
            "ownerSide"
        )

        if not owner_id or not side:
            return None

        team = self._team(side)

        return next(
            (
                p
                for p in team["players"]
                if p["id"] == owner_id
                and p["onPitch"]
            ),
            None,
        )

    # ========================================================
    # CLEAR OWNERS
    # ========================================================

    def _clear_ball_owners(self):

        for team in (
            self.home,
            self.away,
        ):

            for player in team["players"]:
                player["hasBall"] = False

    # ========================================================
    # LOOSE BALL
    # ========================================================

    def _loose_ball(self):

        self._clear_ball_owners()

        self.ball["ownerId"] = None
        self.ball["ownerSide"] = None
        self.ball["phase"] = "loose"

    # ========================================================
    # RECOVER LOOSE BALL
    # ========================================================

    def _recover_loose_ball(self):

        candidates = []

        for side in (
            "home",
            "away",
        ):

            for player in self._team(side)[
                "players"
            ]:

                if not player["onPitch"]:
                    continue

                d = distance(
                    player["x"],
                    player["y"],
                    self.ball["x"],
                    self.ball["y"],
                )

                if d < 15:

                    candidates.append(
                        (
                            d,
                            side,
                            player,
                        )
                    )

        if not candidates:
            return

        candidates.sort(
            key=lambda item: item[0]
        )

        _, side, player = candidates[0]

        self._clear_ball_owners()

        player["hasBall"] = True

        self.ball["ownerId"] = (
            player["id"]
        )

        self.ball["ownerSide"] = side

        self.ball["phase"] = "controlled"

        self.ball["x"] = player["x"]
        self.ball["y"] = player["y"]

    # ========================================================
    # RESTARTS
    # ========================================================

    def _handle_restart(self):

        if self.pending_restart == "kickoff":

            if self.ball["phase"] == "kickoff":

                self.pending_restart = None

        elif self.pending_restart == "corner":

            pass

        elif self.pending_restart == "goal_kick":

            pass

    # ========================================================
    # CORNER / GOAL KICK
    # ========================================================

    def _corner_or_goal_kick(
        self,
        attacking_side,
        shooter,
        blocked=False,
    ):

        if chance(0.45):

            self._set_corner(
                attacking_side
            )

        else:

            self._set_goal_kick(
                self._opponent(
                    attacking_side
                )
            )

    def _set_corner(
        self,
        attacking_side,
    ):

        if (
            self.elapsed_real
            - self.last_corner_time
            < 0.7
        ):
            return

        self.last_corner_time = (
            self.elapsed_real
        )

        self._team(
            attacking_side
        )["stats"]["corners"] += 1

        self._event(
            "corner",
            (
                "Corner kick for "
                + (
                    self.home["name"]
                    if attacking_side == "home"
                    else self.away["name"]
                )
            ),
            self.minute,
            side=attacking_side,
        )

        x = (
            96
            if attacking_side == "home"
            else 4
        )

        y = (
            3
            if random.random() < 0.5
            else 57
        )

        self._clear_ball_owners()

        self.ball["x"] = x
        self.ball["y"] = y
        self.ball["phase"] = "corner"
        self.ball["ownerSide"] = attacking_side
        self.ball["ownerId"] = None

        # Corner creates immediate danger
        if chance(0.52):

            attackers = [
                p
                for p in self._team(
                    attacking_side
                )["players"]
                if p["onPitch"]
                and p["role"] in {
                    "ST",
                    "AM",
                    "LW",
                    "RW",
                }
            ]

            if attackers:

                target = random.choice(
                    attackers
                )

                if chance(
                    (
                        target["ratings"]["shooting"]
                        / 100
                    ) * 0.50
                ):

                    self._header_shot(
                        attacking_side,
                        target,
                    )

                else:

                    self._set_goal_kick(
                        self._opponent(
                            attacking_side
                        )
                    )

    def _set_goal_kick(
        self,
        defending_team,
    ):

        side = (
            "home"
            if defending_team is self.home
            else "away"
        )

        keeper = self._goalkeeper(
            defending_team
        )

        self._clear_ball_owners()

        if keeper:

            keeper["hasBall"] = True

            self.ball["ownerId"] = (
                keeper["id"]
            )

            self.ball["ownerSide"] = side

            self.ball["phase"] = "controlled"

            self.ball["x"] = keeper["x"]
            self.ball["y"] = keeper["y"]

            self._event(
                "goal_kick",
                f"{keeper['name']} takes a goal kick",
                self.minute,
                side=side,
                playerId=keeper["id"],
            )

    # ========================================================
    # RESET AFTER GOAL
    # ========================================================

    def _reset_positions(
        self,
        kicking_side,
    ):

        for side in (
            "home",
            "away",
        ):

            team = self._team(side)

            for player in team["players"]:

                if not player["onPitch"]:
                    continue

                x, y = self._base_position(
                    team,
                    player,
                )

                player["x"] = x
                player["y"] = y

                player["targetX"] = x
                player["targetY"] = y

    def _assign_kickoff_to(
        self,
        side,
    ):

        team = self._team(side)

        player = self._find_role(
            team,
            {"ST", "AM", "CM"},
        )

        if not player:
            player = team["players"][0]

        self._clear_ball_owners()

        player["hasBall"] = True

        self.ball["ownerId"] = (
            player["id"]
        )

        self.ball["ownerSide"] = side

        self.ball["phase"] = "controlled"

        self.ball["x"] = 50
        self.ball["y"] = 30

    # ========================================================
    # FORMATION
    # ========================================================

    def set_formation(
        self,
        side,
        formation,
    ):

        if formation not in FORMATION_POSITIONS:
            formation = "4-3-3"

        team = self._team(
            side
        )

        team["formation"] = formation

        self._event(
            "formation",
            f"{team['name']} changes formation to {formation}",
            self.minute,
            side=side,
        )

        return self.snapshot()

    # ========================================================
    # TACTICS
    # ========================================================

    def set_tactics(
        self,
        side,
        tactics,
    ):

        team = self._team(
            side
        )

        if not isinstance(tactics, dict):
            tactics = {}

        team["tactics"].update(
            tactics
        )

        team["tactics"]["tempo"] = clamp(
            float(
                team["tactics"].get(
                    "tempo",
                    60,
                )
            ),
            1,
            100,
        )

        team["tactics"]["width"] = clamp(
            float(
                team["tactics"].get(
                    "width",
                    55,
                )
            ),
            1,
            100,
        )

        self._event(
            "tactics",
            f"{team['name']} changed tactics",
            self.minute,
            side=side,
        )

        return self.snapshot()

    # ========================================================
    # SUBSTITUTION
    # ========================================================

    def substitute(
        self,
        side,
        outgoing_id,
        incoming_id,
    ):

        team = self._team(side)

        if team["substitutionsUsed"] >= 5:

            return self.snapshot()

        outgoing = next(
            (
                p
                for p in team["players"]
                if p["id"] == outgoing_id
                and p["onPitch"]
            ),
            None,
        )

        incoming = next(
            (
                p
                for p in team["bench"]
                if p["id"] == incoming_id
                and not p["onPitch"]
            ),
            None,
        )

        if not outgoing or not incoming:

            return self.snapshot()

        incoming["onPitch"] = True
        incoming["substituted"] = True

        incoming["x"] = outgoing["x"]
        incoming["y"] = outgoing["y"]

        incoming["targetX"] = outgoing[
            "targetX"
        ]

        incoming["targetY"] = outgoing[
            "targetY"
        ]

        # Make bench player compatible
        replacement = {
            **incoming,
            "position": (
                outgoing["position"]
            ),
            "role": (
                outgoing["role"]
            ),
            "hasBall": outgoing["hasBall"],
            "stamina": 100.0,
            "shots": 0,
            "shotsOnTarget": 0,
            "goals": 0,
            "passes": 0,
            "successfulPasses": 0,
            "tackles": 0,
            "interceptions": 0,
            "dribbles": 0,
            "successfulDribbles": 0,
            "assists": 0,
            "yellow": False,
            "red": False,
        }

        if outgoing["hasBall"]:

            self.ball["ownerId"] = (
                incoming["id"]
            )

            self.ball["ownerSide"] = side

            self.ball["x"] = incoming["x"]
            self.ball["y"] = incoming["y"]

        outgoing["hasBall"] = False
        outgoing["onPitch"] = False
        outgoing["substituted"] = True

        team["players"] = [
            replacement
            if p["id"] == outgoing_id
            else p
            for p in team["players"]
        ]

        team["bench"] = [
            p
            for p in team["bench"]
            if p["id"] != incoming_id
        ]

        team["bench"].append(
            outgoing
        )

        team["substitutionsUsed"] += 1

        self._event(
            "substitution",
            (
                f"{team['name']}: "
                f"{outgoing['name']} "
                f"off, "
                f"{incoming['name']} on"
            ),
            self.minute,
            side=side,
            outgoingId=outgoing_id,
            incomingId=incoming_id,
        )

        return self.snapshot()

    # ========================================================
    # FINISH
    # ========================================================

    def finish(self):

        with self.lock:

            if self.status == "finished":
                return self.snapshot()

            self.running = False

            self.status = "finished"

            self.minute = 90
            self.second = 0

            self._event(
                "fulltime",
                (
                    f"Full time: "
                    f"{self.score['home']}"
                    f"-"
                    f"{self.score['away']}"
                ),
                90,
            )

            return self.snapshot()

    # ========================================================
    # FIND ROLE
    # ========================================================

    def _find_role(
        self,
        team,
        roles,
    ):

        for player in team["players"]:

            if (
                player["onPitch"]
                and player["role"] in roles
            ):
                return player

        return None

    # ========================================================
    # GOALKEEPER
    # ========================================================

    def _goalkeeper(
        self,
        team,
    ):

        return next(
            (
                p
                for p in team["players"]
                if p["onPitch"]
                and p["role"] == "GK"
            ),
            None,
        )

    # ========================================================
    # TEAM HELPERS
    # ========================================================

    def _team(self, side):

        return (
            self.home
            if side == "home"
            else self.away
        )

    def _opponent(self, side):

        return (
            self.away
            if side == "home"
            else self.home
        )

    # ========================================================
    # EVENTS
    # ========================================================

    def _event(
        self,
        event_type,
        message,
        minute,
        **extra,
    ):

        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "message": message,
            "minute": int(minute),
            "second": int(
                self.second
            ),
            "timestamp": time.time(),
        }

        event.update(extra)

        self.events.append(event)

        if len(self.events) > MAX_EVENTS:

            self.events = self.events[
                -MAX_EVENTS:
            ]

    # ========================================================
    # SNAPSHOT
    # ========================================================

    def snapshot(self):

        with self.lock:

            total_possession = (
                self.possession_seconds["home"]
                + self.possession_seconds["away"]
            )

            if total_possession <= 0:

                home_possession = 50
                away_possession = 50

            else:

                home_possession = round(
                    (
                        self.possession_seconds[
                            "home"
                        ]
                        / total_possession
                    ) * 100
                )

                away_possession = (
                    100
                    - home_possession
                )

            home = copy.deepcopy(
                self.home
            )

            away = copy.deepcopy(
                self.away
            )

            home["stats"] = copy.deepcopy(
                self.home["stats"]
            )

            away["stats"] = copy.deepcopy(
                self.away["stats"]
            )

            home["stats"]["possession"] = (
                home_possession
            )

            away["stats"]["possession"] = (
                away_possession
            )

            return {
                "matchId": self.match_id,

                "status": self.status,

                "minute": self.minute,

                "second": self.second,

                "score": copy.deepcopy(
                    self.score
                ),

                "home": home,

                "away": away,

                "ball": copy.deepcopy(
                    self.ball
                ),

                "events": copy.deepcopy(
                    self.events[
                        -MAX_EVENTS:
                    ]
                ),

                "stats": {
                    "home": home["stats"],
                    "away": away["stats"],
                },

                "result": {
                    "home": self.score["home"],
                    "away": self.score["away"],
                },
            }
