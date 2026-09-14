# football_engine.py

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

MATCH_REAL_DURATION_SECONDS = 480.0
MATCH_MINUTES = 90.0

TICK_SECONDS = 0.05

MAX_EVENTS = 300
MAX_SPEED = 0.55

HALF_TIME_MINUTE = 45.0
FULL_TIME_MINUTE = 90.0


# ============================================================
# FORMATIONS
# x = length of pitch
# y = width of pitch
# ============================================================

FORMATIONS = {
    "4-4-2": [
        ("GK", 6, 30),
        ("LB", 18, 8),
        ("CB", 16, 21),
        ("CB", 16, 39),
        ("RB", 18, 52),
        ("LM", 38, 9),
        ("CM", 36, 22),
        ("CM", 36, 38),
        ("RM", 38, 51),
        ("ST", 72, 21),
        ("ST", 72, 39),
    ],

    "4-3-3": [
        ("GK", 6, 30),
        ("LB", 18, 8),
        ("CB", 16, 21),
        ("CB", 16, 39),
        ("RB", 18, 52),
        ("CM", 35, 17),
        ("CM", 35, 30),
        ("CM", 35, 43),
        ("LW", 67, 8),
        ("ST", 74, 30),
        ("RW", 67, 52),
    ],

    "3-5-2": [
        ("GK", 6, 30),
        ("CB", 17, 16),
        ("CB", 15, 30),
        ("CB", 17, 44),
        ("LWB", 39, 5),
        ("CM", 35, 18),
        ("CM", 35, 30),
        ("CM", 35, 42),
        ("RWB", 39, 55),
        ("ST", 72, 22),
        ("ST", 72, 38),
    ],

    "5-3-2": [
        ("GK", 6, 30),
        ("LWB", 22, 5),
        ("CB", 17, 18),
        ("CB", 15, 30),
        ("CB", 17, 42),
        ("RWB", 22, 55),
        ("CM", 37, 18),
        ("CM", 35, 30),
        ("CM", 37, 42),
        ("ST", 72, 22),
        ("ST", 72, 38),
    ],

    "4-2-3-1": [
        ("GK", 6, 30),
        ("LB", 18, 8),
        ("CB", 16, 21),
        ("CB", 16, 39),
        ("RB", 18, 52),
        ("DM", 30, 21),
        ("DM", 30, 39),
        ("LW", 53, 9),
        ("AM", 53, 30),
        ("RW", 53, 51),
        ("ST", 74, 30),
    ],
}


FORMATION_ROLES = {
    "4-4-2": [
        "GK",
        "LB",
        "CB",
        "CB",
        "RB",
        "LM",
        "CM",
        "CM",
        "RM",
        "ST",
        "ST",
    ],
    "4-3-3": [
        "GK",
        "LB",
        "CB",
        "CB",
        "RB",
        "CM",
        "CM",
        "CM",
        "LW",
        "ST",
        "RW",
    ],
    "3-5-2": [
        "GK",
        "CB",
        "CB",
        "CB",
        "LWB",
        "CM",
        "CM",
        "CM",
        "RWB",
        "ST",
        "ST",
    ],
    "5-3-2": [
        "GK",
        "LWB",
        "CB",
        "CB",
        "CB",
        "RWB",
        "CM",
        "CM",
        "CM",
        "ST",
        "ST",
    ],
    "4-2-3-1": [
        "GK",
        "LB",
        "CB",
        "CB",
        "RB",
        "DM",
        "DM",
        "LW",
        "AM",
        "RW",
        "ST",
    ],
}


DEFENDER_ROLES = {
    "GK",
    "LB",
    "RB",
    "CB",
    "LWB",
    "RWB",
}

MIDFIELD_ROLES = {
    "DM",
    "CM",
    "LM",
    "RM",
    "LW",
    "RW",
    "AM",
}

ATTACKER_ROLES = {
    "ST",
    "CF",
}


# ============================================================
# HELPERS
# ============================================================

def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def distance(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    return math.sqrt(
        ((x2 - x1) ** 2) +
        ((y2 - y1) ** 2)
    )


def lerp(a: float, b: float, amount: float) -> float:
    return a + ((b - a) * amount)


def chance(probability: float) -> bool:
    return random.random() < clamp(probability, 0.0, 1.0)


def normalize_name(value: Any, fallback: str) -> str:
    value = str(value or "").strip()
    return value if value else fallback


# ============================================================
# MATCH ENGINE
# ============================================================

class FootballMatch:

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.config = config or {}

        self.lock = threading.RLock()

        self.match_id = str(
            self.config.get("matchId")
            or self.config.get("id")
            or uuid.uuid4()
        )

        self.status = "created"

        self.minute = 0.0
        self.second = 0.0

        self.running = False
        self.finished = False

        self.thread: Optional[threading.Thread] = None

        self.ball = {
            "x": 50.0,
            "y": 30.0,
            "owner": None,
            "team": None,
            "speed": 0.0,
            "targetX": 50.0,
            "targetY": 30.0,
            "type": "kickoff",
        }

        self.possession_team = "home"

        self.events: List[Dict[str, Any]] = []

        self.score = {
            "home": 0,
            "away": 0,
        }

        self.stats = self._empty_match_stats()

        self.home = self._create_team(
            self.config.get("home") or {},
            "home",
            "Home",
        )

        self.away = self._create_team(
            self.config.get("away") or {},
            "away",
            "Away",
        )

        self.last_tick = time.time()

        self.halftime_done = False

        self._ensure_valid_players()

        self._set_initial_positions()

        self._add_event(
            "kickoff",
            "Match created",
            team=None,
            player=None,
        )

    # ========================================================
    # STATS
    # ========================================================

    def _empty_stats(self) -> Dict[str, Any]:
        return {
            "shots": 0,
            "shotsOnTarget": 0,
            "goals": 0,
            "passes": 0,
            "passesCompleted": 0,
            "keyPasses": 0,
            "dribbles": 0,
            "dribblesWon": 0,
            "tackles": 0,
            "tacklesWon": 0,
            "interceptions": 0,
            "crosses": 0,
            "crossesCompleted": 0,
            "corners": 0,
            "offsides": 0,
            "fouls": 0,
            "saves": 0,
            "possessionSeconds": 0.0,
            "yellowCards": 0,
            "redCards": 0,
        }

    def _empty_match_stats(self) -> Dict[str, Any]:
        return {
            "home": self._empty_stats(),
            "away": self._empty_stats(),
        }

    def _ensure_team_stats(
        self,
        team: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(
            team.get("stats"),
            dict,
        ):
            team["stats"] = self._empty_stats()

        defaults = self._empty_stats()

        for key, value in defaults.items():
            if key not in team["stats"]:
                team["stats"][key] = value

        return team["stats"]

    # ========================================================
    # TEAM CREATION
    # ========================================================

    def _create_team(
        self,
        source: Dict[str, Any],
        side: str,
        fallback_name: str,
    ) -> Dict[str, Any]:

        formation = (
            source.get("formation")
            or "4-3-3"
        )

        if formation not in FORMATIONS:
            formation = "4-3-3"

        tactics_source = (
            source.get("tactics")
            or {}
        )

        tactics = {
            "mentality": (
                tactics_source.get("mentality")
                or "balanced"
            ),

            "tempo": float(
                tactics_source.get(
                    "tempo",
                    60,
                )
            ),

            "pressing": (
                tactics_source.get("pressing")
                or "medium"
            ),

            "defensiveLine": (
                tactics_source.get(
                    "defensiveLine"
                )
                or "medium"
            ),

            "width": float(
                tactics_source.get(
                    "width",
                    55,
                )
            ),
        }

        team = {
            "id": normalize_name(
                source.get("id"),
                side,
            ),

            "name": normalize_name(
                source.get("name"),
                fallback_name,
            ),

            "logo": source.get(
                "logo",
                "",
            ),

            "formation": formation,

            "tactics": tactics,

            "players": [],

            "bench": [],

            "substitutionsUsed": int(
                source.get(
                    "substitutionsUsed",
                    0,
                )
                or 0
            ),

            # IMPORTANT
            # This was missing before and could
            # cause KeyError during match actions.
            "stats": self._empty_stats(),
        }

        source_players = (
            source.get("players")
            or source.get("lineup")
            or []
        )

        source_bench = (
            source.get("bench")
            or []
        )

        roles = FORMATION_ROLES[
            formation
        ]

        for index in range(11):
            source_player = (
                source_players[index]
                if index < len(source_players)
                else {}
            )

            role = (
                roles[index]
                if index < len(roles)
                else "CM"
            )

            player = self._create_player(
                source_player,
                index,
                role,
            )

            team["players"].append(
                player
            )

        for index, source_player in enumerate(
            source_bench
        ):
            player = self._create_player(
                source_player,
                index + 11,
                source_player.get(
                    "position",
                    "CM",
                ),
            )

            player["onPitch"] = False

            team["bench"].append(
                player
            )

        self._ensure_team_stats(team)

        return team

    # ========================================================
    # PLAYER CREATION
    # ========================================================

    def _create_player(
        self,
        source: Dict[str, Any],
        index: int,
        role: str,
    ) -> Dict[str, Any]:

        ratings = source.get(
            "ratings"
        ) or {}

        def rating(
            name: str,
            default: int,
        ) -> float:
            value = source.get(
                name,
                ratings.get(
                    name,
                    default,
                ),
            )

            try:
                return float(value)
            except Exception:
                return float(default)

        player = {
            "id": normalize_name(
                source.get("id")
                or source.get("playerId"),
                f"player-{index + 1}",
            ),

            "name": normalize_name(
                source.get("name")
                or source.get("displayName"),
                f"Player {index + 1}",
            ),

            "number": int(
                source.get(
                    "number",
                    source.get(
                        "shirtNumber",
                        index + 1,
                    ),
                )
                or index + 1
            ),

            "position": role,

            "role": role,

            "pace": rating(
                "pace",
                68,
            ),

            "passing": rating(
                "passing",
                68,
            ),

            "shooting": rating(
                "shooting",
                65,
            ),

            "dribbling": rating(
                "dribbling",
                67,
            ),

            "defending": rating(
                "defending",
                65,
            ),

            "stamina": rating(
                "stamina",
                75,
            ),

            "strength": rating(
                "strength",
                70,
            ),

            "vision": rating(
                "vision",
                68,
            ),

            "goalkeeping": rating(
                "goalkeeping",
                65,
            ),

            "x": 50.0,
            "y": 30.0,

            "targetX": 50.0,
            "targetY": 30.0,

            "energy": 100.0,

            "onPitch": True,

            "hasBall": False,

            "lastActionAt": 0.0,

            "shots": 0,
            "goals": 0,
            "assists": 0,
            "passes": 0,
            "completedPasses": 0,
            "dribbles": 0,
            "tackles": 0,
            "interceptions": 0,

            "yellowCard": False,
            "redCard": False,
        }

        return player

    # ========================================================
    # INITIAL PLAYERS
    # ========================================================

    def _ensure_valid_players(self):
        for team in [
            self.home,
            self.away,
        ]:
            self._ensure_team_stats(team)

            if len(team["players"]) < 11:
                roles = FORMATION_ROLES[
                    team["formation"]
                ]

                while len(
                    team["players"]
                ) < 11:
                    index = len(
                        team["players"]
                    )

                    role = (
                        roles[index]
                        if index < len(roles)
                        else "CM"
                    )

                    team["players"].append(
                        self._create_player(
                            {},
                            index,
                            role,
                        )
                    )

    def _set_initial_positions(self):
        self._apply_formation_positions(
            self.home,
            attacking_direction=1,
        )

        self._apply_formation_positions(
            self.away,
            attacking_direction=-1,
        )

        home_player = self._find_best_player(
            self.home,
            "CM",
        )

        if home_player:
            self._set_ball_owner(
                "home",
                home_player,
            )
        else:
            self.ball["owner"] = None

    # ========================================================
    # FORMATION
    # ========================================================

    def _apply_formation_positions(
        self,
        team: Dict[str, Any],
        attacking_direction: int,
    ):
        formation = team["formation"]

        positions = FORMATIONS.get(
            formation,
            FORMATIONS["4-3-3"],
        )

        roles = FORMATION_ROLES.get(
            formation,
            FORMATION_ROLES["4-3-3"],
        )

        for index, player in enumerate(
            team["players"][:11]
        ):
            role = (
                roles[index]
                if index < len(roles)
                else player.get(
                    "role",
                    "CM",
                )
            )

            player["role"] = role
            player["position"] = role

            base = (
                positions[index]
                if index < len(positions)
                else ("CM", 35, 30)
            )

            _, x, y = base

            if attacking_direction == -1:
                x = PITCH_WIDTH - x

            player["x"] = float(x)
            player["y"] = float(y)

            player["targetX"] = float(x)
            player["targetY"] = float(y)

            player["onPitch"] = True

    # ========================================================
    # FINDERS
    # ========================================================

    def _team(
        self,
        side: str,
    ) -> Dict[str, Any]:
        return (
            self.home
            if side == "home"
            else self.away
        )

    def _opponent(
        self,
        side: str,
    ) -> Dict[str, Any]:
        return (
            self.away
            if side == "home"
            else self.home
        )

    def _find_player(
        self,
        team: Dict[str, Any],
        player_id: str,
    ) -> Optional[Dict[str, Any]]:
        for player in team["players"]:
            if str(
                player["id"]
            ) == str(player_id):
                return player

        return None

    def _find_best_player(
        self,
        team: Dict[str, Any],
        preferred_role: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:

        players = [
            p for p in team["players"]
            if p.get("onPitch", True)
            and not p.get("redCard", False)
        ]

        if not players:
            return None

        if preferred_role:
            preferred = [
                p for p in players
                if p.get("role")
                == preferred_role
            ]

            if preferred:
                return random.choice(
                    preferred
                )

        return random.choice(players)

    # ========================================================
    # BALL
    # ========================================================

    def _set_ball_owner(
        self,
        side: str,
        player: Optional[Dict[str, Any]],
    ):
        self.ball["team"] = side

        if player:
            self.ball["owner"] = player["id"]
            self.ball["x"] = player["x"]
            self.ball["y"] = player["y"]

            for team_side in [
                "home",
                "away",
            ]:
                team = self._team(
                    team_side
                )

                for p in team["players"]:
                    p["hasBall"] = (
                        team_side == side
                        and p["id"]
                        == player["id"]
                    )
        else:
            self.ball["owner"] = None

    def _owner_player(
        self,
    ) -> Optional[Dict[str, Any]]:
        if not self.ball.get(
            "owner"
        ):
            return None

        side = self.ball.get(
            "team"
        )

        if side not in [
            "home",
            "away",
        ]:
            return None

        return self._find_player(
            self._team(side),
            self.ball["owner"],
        )

    # ========================================================
    # EVENTS
    # ========================================================

    def _add_event(
        self,
        event_type: str,
        message: str,
        team: Optional[str] = None,
        player: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        event = {
            "id": str(uuid.uuid4()),
            "minute": round(
                self.minute,
                2,
            ),
            "second": round(
                self.second,
                2,
            ),
            "type": event_type,
            "message": message,
            "team": team,
            "player": (
                player["id"]
                if player
                else None
            ),
        }

        if player:
            event["playerName"] = player[
                "name"
            ]

        if extra:
            event.update(extra)

        self.events.append(event)

        if len(self.events) > MAX_EVENTS:
            self.events = self.events[
                -MAX_EVENTS:
            ]

    # ========================================================
    # TACTICS
    # ========================================================

    def set_tactics(
        self,
        side: str,
        tactics: Dict[str, Any],
    ):
        with self.lock:
            team = self._team(side)

            current = team["tactics"]

            if "mentality" in tactics:
                current["mentality"] = str(
                    tactics["mentality"]
                )

            if "tempo" in tactics:
                try:
                    current["tempo"] = clamp(
                        float(
                            tactics["tempo"]
                        ),
                        1,
                        100,
                    )
                except Exception:
                    pass

            if "pressing" in tactics:
                current["pressing"] = str(
                    tactics["pressing"]
                )

            if "defensiveLine" in tactics:
                current[
                    "defensiveLine"
                ] = str(
                    tactics[
                        "defensiveLine"
                    ]
                )

            if "width" in tactics:
                try:
                    current["width"] = clamp(
                        float(
                            tactics["width"]
                        ),
                        1,
                        100,
                    )
                except Exception:
                    pass

            self._add_event(
                "tactics",
                f"{team['name']} changed tactics",
                team=side,
            )

            return self.snapshot()

    # ========================================================
    # FORMATION CHANGE
    # ========================================================

    def set_formation(
        self,
        side: str,
        formation: str,
    ):
        with self.lock:
            if formation not in FORMATIONS:
                raise ValueError(
                    "Invalid formation"
                )

            team = self._team(side)

            team["formation"] = formation

            direction = (
                1
                if side == "home"
                else -1
            )

            self._apply_formation_positions(
                team,
                direction,
            )

            self._add_event(
                "formation",
                f"{team['name']} changed formation to {formation}",
                team=side,
            )

            return self.snapshot()

    # ========================================================
    # START / PAUSE / FINISH
    # ========================================================

    def start(self):
        with self.lock:

            if self.finished:
                return self.snapshot()

            if self.running:
                return self.snapshot()

            self.running = True

            self.status = "playing"

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

            self._add_event(
                "match",
                "Match started",
            )

            return self.snapshot()

    def pause(self):
        with self.lock:
            self.running = False

            if not self.finished:
                self.status = "paused"

            self._add_event(
                "match",
                "Match paused",
            )

            return self.snapshot()

    def finish(self):
        with self.lock:
            self.running = False
            self.finished = True
            self.status = "finished"

            self.minute = 90.0
            self.second = 0.0

            self._add_event(
                "fulltime",
                "Full time",
            )

            return self.snapshot()

    # ========================================================
    # BACKGROUND LOOP
    # ========================================================

    def _run_loop(self):
        while True:
            if self.finished:
                break

            if not self.running:
                time.sleep(0.05)
                continue

            start = time.time()

            try:
                self.advance(
                    TICK_SECONDS
                )
            except Exception as exc:
                with self.lock:
                    self._add_event(
                        "engine_error",
                        f"Engine error: {exc}",
                    )

            elapsed = (
                time.time() - start
            )

            sleep_time = max(
                0.001,
                TICK_SECONDS - elapsed,
            )

            time.sleep(
                sleep_time
            )

    # ========================================================
    # ADVANCE MATCH
    # ========================================================

    def advance(
        self,
        real_seconds: float,
    ):
        with self.lock:

            if (
                not self.running
                or self.finished
            ):
                return

            football_seconds = (
                real_seconds
                * (
                    MATCH_MINUTES
                    / MATCH_REAL_DURATION_SECONDS
                )
                * 60.0
            )

            previous_minute = (
                self.minute
            )

            self.minute += (
                football_seconds
                / 60.0
            )

            if self.minute >= 90:
                self.minute = 90.0
                self.second = 0.0
                self.running = False
                self.finished = True
                self.status = "finished"

                self._add_event(
                    "fulltime",
                    "Full time",
                )

                return

            self.second = (
                self.minute
                * 60.0
            ) % 60

            # halftime
            if (
                self.minute >= 45
                and not self.halftime_done
            ):
                self.halftime_done = True

                self.running = False
                self.status = "halftime"

                self._add_event(
                    "halftime",
                    "Half time",
                )

                return

            # possession statistics
            possession_side = (
                self.ball.get("team")
            )

            if possession_side in [
                "home",
                "away",
            ]:
                self.stats[
                    possession_side
                ]["possessionSeconds"] += (
                    football_seconds
                )

            self._update_stamina(
                football_seconds
            )

            self._update_player_targets()

            self._move_players(
                football_seconds
            )

            self._update_ball(
                football_seconds
            )

            self._decide_actions()

            # keep clock safe
            if self.minute < previous_minute:
                self.minute = previous_minute

    # ========================================================
    # STAMINA
    # ========================================================

    def _update_stamina(
        self,
        football_seconds: float,
    ):
        minutes = (
            football_seconds
            / 60.0
        )

        for team in [
            self.home,
            self.away,
        ]:
            for player in team[
                "players"
            ]:

                if not player.get(
                    "onPitch",
                    True,
                ):
                    continue

                role = player.get(
                    "role",
                    "CM",
                )

                consumption = 0.018

                if role in [
                    "ST",
                    "LW",
                    "RW",
                    "LM",
                    "RM",
                ]:
                    consumption = 0.024

                if player.get(
                    "hasBall"
                ):
                    consumption += 0.008

                stamina_factor = clamp(
                    player.get(
                        "stamina",
                        75,
                    ) / 100.0,
                    0.4,
                    1.2,
                )

                player["energy"] = clamp(
                    player.get(
                        "energy",
                        100,
                    )
                    - (
                        consumption
                        * minutes
                        / stamina_factor
                    ),
                    40,
                    100,
                )

    # ========================================================
    # TARGET MOVEMENT
    # ========================================================

    def _update_player_targets(self):
        for side in [
            "home",
            "away",
        ]:
            team = self._team(side)

            opponent = self._opponent(
                side
            )

            attacking_direction = (
                1
                if side == "home"
                else -1
            )

            has_possession = (
                self.ball.get("team")
                == side
            )

            ball_x = self.ball.get(
                "x",
                50,
            )

            ball_y = self.ball.get(
                "y",
                30,
            )

            for player in team[
                "players"
            ]:

                if not player.get(
                    "onPitch",
                    True,
                ):
                    continue

                if player.get(
                    "redCard",
                    False,
                ):
                    continue

                role = player.get(
                    "role",
                    "CM",
                )

                base_x, base_y = (
                    self._base_position(
                        team,
                        player,
                        side,
                    )
                )

                target_x = base_x
                target_y = base_y

                # ------------------------------------------------
                # TEAM POSSESSION
                # ------------------------------------------------
                if has_possession:

                    if role in ATTACKER_ROLES:

                        if attacking_direction == 1:
                            target_x = clamp(
                                base_x + 13,
                                60,
                                88,
                            )
                        else:
                            target_x = clamp(
                                base_x - 13,
                                12,
                                40,
                            )

                    elif role in [
                        "LW",
                        "RW",
                        "LM",
                        "RM",
                    ]:

                        if attacking_direction == 1:
                            target_x = clamp(
                                base_x + 10,
                                45,
                                82,
                            )
                        else:
                            target_x = clamp(
                                base_x - 10,
                                18,
                                55,
                            )

                    elif role == "AM":

                        if attacking_direction == 1:
                            target_x = 60
                        else:
                            target_x = 40

                    elif role in [
                        "CM",
                        "DM",
                    ]:

                        if attacking_direction == 1:
                            target_x = base_x + 5
                        else:
                            target_x = base_x - 5

                    elif role in DEFENDER_ROLES:

                        if attacking_direction == 1:
                            target_x = base_x + 3
                        else:
                            target_x = base_x - 3

                # ------------------------------------------------
                # OPPONENT HAS BALL
                # ------------------------------------------------
                else:

                    distance_to_ball = distance(
                        player["x"],
                        player["y"],
                        ball_x,
                        ball_y,
                    )

                    pressing = team[
                        "tactics"
                    ].get(
                        "pressing",
                        "medium",
                    )

                    if pressing == "high":
                        press_distance = 30
                    elif pressing == "low":
                        press_distance = 15
                    else:
                        press_distance = 22

                    if (
                        distance_to_ball
                        < press_distance
                        and role not in [
                            "GK",
                        ]
                    ):
                        target_x = ball_x
                        target_y = ball_y

                    elif role in DEFENDER_ROLES:

                        defensive_line = team[
                            "tactics"
                        ].get(
                            "defensiveLine",
                            "medium",
                        )

                        if defensive_line == "high":
                            line = 34
                        elif defensive_line == "low":
                            line = 20
                        else:
                            line = 27

                        if side == "home":
                            target_x = line
                        else:
                            target_x = (
                                PITCH_WIDTH
                                - line
                            )

                    elif role in MIDFIELD_ROLES:

                        if side == "home":
                            target_x = 36
                        else:
                            target_x = 64

                # ------------------------------------------------
                # BALL CARRIER
                # ------------------------------------------------
                if player.get(
                    "hasBall"
                ):
                    target_x = player[
                        "x"
                    ]

                    target_y = player[
                        "y"
                    ]

                # ------------------------------------------------
                # ATTACKING RUNS
                # ------------------------------------------------
                if (
                    has_possession
                    and role in ATTACKER_ROLES
                ):

                    if side == "home":
                        target_x = max(
                            target_x,
                            76,
                        )
                    else:
                        target_x = min(
                            target_x,
                            24,
                        )

                # ------------------------------------------------
                # WIDTH
                # ------------------------------------------------
                width = team[
                    "tactics"
                ].get(
                    "width",
                    55,
                )

                width_factor = (
                    (width - 50)
                    / 100
                )

                if role in [
                    "LW",
                    "LM",
                ]:
                    target_y -= (
                        5 * width_factor
                    )

                if role in [
                    "RW",
                    "RM",
                ]:
                    target_y += (
                        5 * width_factor
                    )

                player[
                    "targetX"
                ] = clamp(
                    target_x,
                    3,
                    97,
                )

                player[
                    "targetY"
                ] = clamp(
                    target_y,
                    3,
                    57,
                )

    # ========================================================
    # BASE POSITION
    # ========================================================

    def _base_position(
        self,
        team: Dict[str, Any],
        player: Dict[str, Any],
        side: str,
    ):
        formation = team[
            "formation"
        ]

        roles = FORMATION_ROLES.get(
            formation,
            FORMATION_ROLES[
                "4-3-3"
            ],
        )

        try:
            index = team[
                "players"
            ].index(player)
        except ValueError:
            index = 0

        positions = FORMATIONS.get(
            formation,
            FORMATIONS[
                "4-3-3"
            ],
        )

        if index >= len(
            positions
        ):
            index = len(
                positions
            ) - 1

        _, x, y = positions[
            index
        ]

        if side == "away":
            x = PITCH_WIDTH - x

        return (
            float(x),
            float(y),
        )

    # ========================================================
    # PLAYER MOVEMENT
    # ========================================================

    def _move_players(
        self,
        football_seconds: float,
    ):
        move_factor = clamp(
            football_seconds
            * 0.8,
            0.1,
            1.0,
        )

        for team in [
            self.home,
            self.away,
        ]:
            for player in team[
                "players"
            ]:

                if not player.get(
                    "onPitch",
                    True,
                ):
                    continue

                if player.get(
                    "redCard",
                    False,
                ):
                    continue

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

                if dist <= 0.05:
                    continue

                pace = clamp(
                    player.get(
                        "pace",
                        68,
                    ),
                    30,
                    100,
                )

                energy = clamp(
                    player.get(
                        "energy",
                        100,
                    ),
                    40,
                    100,
                )

                speed = (
                    0.08
                    + (
                        pace
                        / 100
                    )
                    * 0.22
                )

                speed *= (
                    0.75
                    + (
                        energy
                        / 100
                    )
                    * 0.35
                )

                step = min(
                    dist,
                    speed
                    * move_factor
                    * 5,
                )

                player["x"] += (
                    dx / dist
                ) * step

                player["y"] += (
                    dy / dist
                ) * step

                player["x"] = clamp(
                    player["x"],
                    1,
                    99,
                )

                player["y"] = clamp(
                    player["y"],
                    1,
                    59,
                )

    # ========================================================
    # BALL MOVEMENT
    # ========================================================

    def _update_ball(
        self,
        football_seconds: float,
    ):
        if self.ball.get(
            "owner"
        ):
            owner = self._owner_player()

            if owner:
                self.ball["x"] = owner[
                    "x"
                ]

                self.ball["y"] = owner[
                    "y"
                ]

                return

            self.ball["owner"] = None

        target_x = self.ball.get(
            "targetX",
            self.ball["x"],
        )

        target_y = self.ball.get(
            "targetY",
            self.ball["y"],
        )

        dx = (
            target_x
            - self.ball["x"]
        )

        dy = (
            target_y
            - self.ball["y"]
        )

        dist = math.sqrt(
            dx * dx
            + dy * dy
        )

        if dist <= 0.5:
            self.ball["x"] = target_x
            self.ball["y"] = target_y

            self._try_ball_recovery()

            return

        speed = max(
            self.ball.get(
                "speed",
                1.0,
            ),
            0.5,
        )

        step = min(
            dist,
            speed
            * football_seconds
            * 1.8,
        )

        self.ball["x"] += (
            dx / dist
        ) * step

        self.ball["y"] += (
            dy / dist
        ) * step

        self.ball["x"] = clamp(
            self.ball["x"],
            -2,
            102,
        )

        self.ball["y"] = clamp(
            self.ball["y"],
            -2,
            62,
        )

        self._try_ball_recovery()

    # ========================================================
    # BALL RECOVERY
    # ========================================================

    def _try_ball_recovery(self):
        closest = None
        closest_distance = 999

        for side in [
            "home",
            "away",
        ]:
            team = self._team(side)

            for player in team[
                "players"
            ]:

                if not player.get(
                    "onPitch",
                    True,
                ):
                    continue

                if player.get(
                    "redCard",
                    False,
                ):
                    continue

                d = distance(
                    player["x"],
                    player["y"],
                    self.ball["x"],
                    self.ball["y"],
                )

                if d < closest_distance:
                    closest_distance = d
                    closest = (
                        side,
                        player,
                    )

        if (
            closest
            and closest_distance < 1.8
        ):
            side, player = closest

            self._set_ball_owner(
                side,
                player,
            )

    # ========================================================
    # DECISION ENGINE
    # ========================================================

    def _decide_actions(self):
        side = self.ball.get(
            "team"
        )

        owner = self._owner_player()

        if side not in [
            "home",
            "away",
        ]:
            return

        if not owner:
            return

        now = time.time()

        if (
            now
            - owner.get(
                "lastActionAt",
                0,
            )
            < 0.8
        ):
            return

        owner["lastActionAt"] = now

        self._try_pressure(
            side,
            owner,
        )

        if not owner.get(
            "hasBall"
        ):
            return

        attacking_direction = (
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
            - owner["x"]
        )

        # ----------------------------------------------------
        # SHOOT
        # ----------------------------------------------------

        if self._good_shooting_position(
            side,
            owner,
        ):
            shooting_probability = (
                self._shoot_probability(
                    side,
                    owner,
                )
            )

            if chance(
                shooting_probability
            ):
                self._shoot(
                    side,
                    owner,
                )
                return

        # ----------------------------------------------------
        # CROSS
        # ----------------------------------------------------

        if self._can_cross(
            side,
            owner,
        ):
            if chance(
                0.35
            ):
                self._cross(
                    side,
                    owner,
                )
                return

        # ----------------------------------------------------
        # DRIBBLE
        # ----------------------------------------------------

        if (
            distance_to_goal > 12
            and chance(
                self._dribble_probability(
                    owner
                )
            )
        ):
            self._dribble(
                side,
                owner,
            )
            return

        # ----------------------------------------------------
        # PASS
        # ----------------------------------------------------

        receiver = self._choose_pass_target(
            side,
            owner,
        )

        if receiver:
            pass_probability = (
                0.55
                + (
                    owner.get(
                        "vision",
                        68,
                    )
                    / 100
                )
                * 0.25
            )

            if distance_to_goal < 30:
                pass_probability -= 0.15

            if chance(
                pass_probability
            ):
                self._pass(
                    side,
                    owner,
                    receiver,
                )
                return

        # ----------------------------------------------------
        # CARRY FORWARD
        # ----------------------------------------------------

        owner["targetX"] = clamp(
            owner["x"]
            + (
                4
                * attacking_direction
            ),
            2,
            98,
        )

    # ========================================================
    # PRESSURE / TACKLE
    # ========================================================

    def _try_pressure(
        self,
        attacking_side: str,
        owner: Dict[str, Any],
    ):
        defending_side = (
            "away"
            if attacking_side == "home"
            else "home"
        )

        defending_team = self._team(
            defending_side
        )

        nearest = None
        nearest_distance = 999

        for player in defending_team[
            "players"
        ]:
            if not player.get(
                "onPitch",
                True,
            ):
                continue

            if player.get(
                "redCard",
                False,
            ):
                continue

            d = distance(
                player["x"],
                player["y"],
                owner["x"],
                owner["y"],
            )

            if d < nearest_distance:
                nearest_distance = d
                nearest = player

        if not nearest:
            return

        pressing = defending_team[
            "tactics"
        ].get(
            "pressing",
            "medium",
        )

        threshold = {
            "high": 5.0,
            "medium": 3.2,
            "low": 2.0,
        }.get(
            pressing,
            3.2,
        )

        if nearest_distance > threshold:
            return

        tackle_probability = (
            0.10
            + (
                nearest.get(
                    "defending",
                    65,
                )
                / 100
            )
            * 0.25
        )

        if chance(
            tackle_probability
        ):
            self._attempt_tackle(
                defending_side,
                nearest,
                attacking_side,
                owner,
            )

    # ========================================================
    # TACKLE
    # ========================================================

    def _attempt_tackle(
        self,
        defending_side: str,
        defender: Dict[str, Any],
        attacking_side: str,
        attacker: Dict[str, Any],
    ):
        team_stats = self._ensure_team_stats(
            self._team(
                defending_side
            )
        )

        team_stats[
            "tackles"
        ] += 1

        defender[
            "tackles"
        ] += 1

        success_probability = (
            0.38
            + (
                defender.get(
                    "defending",
                    65,
                )
                / 100
            )
            * 0.35
        )

        if chance(
            success_probability
        ):
            team_stats[
                "tacklesWon"
            ] += 1

            self._set_ball_owner(
                defending_side,
                defender,
            )

            self._add_event(
                "tackle",
                f"{defender['name']} won the ball",
                team=defending_side,
                player=defender,
            )
        else:
            if chance(
                0.04
            ):
                team_stats[
                    "fouls"
                ] += 1

                self._add_event(
                    "foul",
                    f"Foul by {defender['name']}",
                    team=defending_side,
                    player=defender,
                )

    # ========================================================
    # PASS TARGET
    # ========================================================

    def _choose_pass_target(
        self,
        side: str,
        passer: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:

        team = self._team(side)

        direction = (
            1
            if side == "home"
            else -1
        )

        candidates = []

        for player in team[
            "players"
        ]:

            if player["id"] == passer["id"]:
                continue

            if not player.get(
                "onPitch",
                True,
            ):
                continue

            if player.get(
                "redCard",
                False,
            ):
                continue

            dx = (
                player["x"]
                - passer["x"]
            ) * direction

            d = distance(
                passer["x"],
                passer["y"],
                player["x"],
                player["y"],
            )

            if d > 42:
                continue

            score = 0.0

            # forward pass
            if dx > 2:
                score += 3

            # attacking players are valuable
            if player.get(
                "role"
            ) in ATTACKER_ROLES:
                score += 4

            if player.get(
                "role"
            ) in [
                "LW",
                "RW",
                "AM",
            ]:
                score += 3

            # open space
            nearest_opponent = (
                self._nearest_opponent_distance(
                    side,
                    player,
                )
            )

            score += clamp(
                nearest_opponent / 10,
                0,
                3,
            )

            # avoid very long passes
            score -= d / 30

            score += random.uniform(
                -1.5,
                1.5,
            )

            candidates.append(
                (
                    score,
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
    # PASS
    # ========================================================

    def _pass(
        self,
        side: str,
        passer: Dict[str, Any],
        receiver: Dict[str, Any],
    ):
        team = self._team(side)

        stats = self._ensure_team_stats(
            team
        )

        stats[
            "passes"
        ] += 1

        passer[
            "passes"
        ] += 1

        passing = passer.get(
            "passing",
            68,
        )

        vision = passer.get(
            "vision",
            68,
        )

        target_distance = distance(
            passer["x"],
            passer["y"],
            receiver["x"],
            receiver["y"],
        )

        accuracy = (
            0.55
            + (
                passing
                / 100
            ) * 0.25
            + (
                vision
                / 100
            ) * 0.12
        )

        accuracy -= max(
            0,
            target_distance - 20,
        ) / 100

        # forward attacking pass
        direction = (
            1
            if side == "home"
            else -1
        )

        forward_distance = (
            receiver["x"]
            - passer["x"]
        ) * direction

        if forward_distance > 8:
            accuracy -= 0.04

        if chance(
            accuracy
        ):
            stats[
                "passesCompleted"
            ] += 1

            passer[
                "completedPasses"
            ] += 1

            self._set_ball_flight(
                receiver["x"],
                receiver["y"],
                speed=18,
                ball_type="pass",
                team=side,
            )

            self.ball[
                "owner"
            ] = None

            for p in team[
                "players"
            ]:
                p[
                    "hasBall"
                ] = False

            if forward_distance > 12:
                stats[
                    "keyPasses"
                ] += 1

            self._add_event(
                "pass",
                f"{passer['name']} passed to {receiver['name']}",
                team=side,
                player=passer,
                extra={
                    "receiver": receiver[
                        "id"
                    ],
                    "receiverName": receiver[
                        "name"
                    ],
                },
            )

        else:
            # bad pass
            self._set_ball_flight(
                receiver["x"]
                + random.uniform(
                    -5,
                    5,
                ),
                receiver["y"]
                + random.uniform(
                    -5,
                    5,
                ),
                speed=14,
                ball_type="bad_pass",
                team=side,
            )

            self.ball[
                "owner"
            ] = None

            for p in team[
                "players"
            ]:
                p[
                    "hasBall"
                ] = False

            self._add_event(
                "bad_pass",
                f"{passer['name']} misplaced the pass",
                team=side,
                player=passer,
            )

    # ========================================================
    # THROUGH BALL
    # ========================================================

    def _through_ball(
        self,
        side: str,
        passer: Dict[str, Any],
        receiver: Dict[str, Any],
    ):
        stats = self._ensure_team_stats(
            self._team(side)
        )

        stats[
            "passes"
        ] += 1

        passer[
            "passes"
        ] += 1

        direction = (
            1
            if side == "home"
            else -1
        )

        target_x = (
            receiver["x"]
            + (
                8
                * direction
            )
        )

        target_x = clamp(
            target_x,
            3,
            97,
        )

        target_y = receiver[
            "y"
        ]

        accuracy = (
            0.48
            + (
                passer.get(
                    "vision",
                    68,
                )
                / 100
            ) * 0.3
        )

        if chance(
            accuracy
        ):
            stats[
                "passesCompleted"
            ] += 1

            passer[
                "completedPasses"
            ] += 1

            self._set_ball_flight(
                target_x,
                target_y,
                speed=20,
                ball_type="through_ball",
                team=side,
            )

            self.ball[
                "owner"
            ] = None

            for p in self._team(
                side
            )["players"]:
                p[
                    "hasBall"
                ] = False

            self._add_event(
                "through_ball",
                f"{passer['name']} played a through ball",
                team=side,
                player=passer,
            )

    # ========================================================
    # DRIBBLING
    # ========================================================

    def _dribble_probability(
        self,
        player: Dict[str, Any],
    ) -> float:

        return (
            0.18
            + (
                player.get(
                    "dribbling",
                    67,
                )
                / 100
            ) * 0.35
        )

    def _dribble(
        self,
        side: str,
        player: Dict[str, Any],
    ):
        team = self._team(side)
        opponent = self._opponent(side)

        stats = self._ensure_team_stats(
            team
        )

        stats[
            "dribbles"
        ] += 1

        player[
            "dribbles"
        ] += 1

        nearest = self._nearest_opponent(
            side,
            player,
        )

        success = (
            0.50
            + (
                player.get(
                    "dribbling",
                    67,
                )
                / 100
            ) * 0.25
            + (
                player.get(
                    "pace",
                    68,
                )
                / 100
            ) * 0.15
        )

        if nearest:
            success -= (
                nearest.get(
                    "defending",
                    65,
                )
                / 100
            ) * 0.18

        if chance(
            success
        ):
            stats[
                "dribblesWon"
            ] += 1

            direction = (
                1
                if side == "home"
                else -1
            )

            player["x"] = clamp(
                player["x"]
                + (
                    3
                    * direction
                ),
                2,
                98,
            )

            if chance(
                0.5
            ):
                player["y"] = clamp(
                    player["y"]
                    + random.uniform(
                        -2.5,
                        2.5,
                    ),
                    2,
                    58,
                )

            self._add_event(
                "dribble",
                f"{player['name']} dribbled past a defender",
                team=side,
                player=player,
            )

        else:
            if nearest:
                self._attempt_tackle(
                    (
                        "away"
                        if side == "home"
                        else "home"
                    ),
                    nearest,
                    side,
                    player,
                )

    # ========================================================
    # SHOOTING
    # ========================================================

    def _good_shooting_position(
        self,
        side: str,
        player: Dict[str, Any],
    ) -> bool:

        if side == "home":
            attacking_x = player["x"]
        else:
            attacking_x = (
                100
                - player["x"]
            )

        center_distance = abs(
            player["y"]
            - 30
        )

        return (
            attacking_x >= 72
            and center_distance <= 25
        )

    def _shoot_probability(
        self,
        side: str,
        player: Dict[str, Any],
    ) -> float:

        if side == "home":
            goal_distance = (
                100
                - player["x"]
            )
        else:
            goal_distance = player[
                "x"
            ]

        shooting = player.get(
            "shooting",
            65,
        )

        probability = (
            0.08
            + (
                shooting
                / 100
            ) * 0.18
        )

        if goal_distance < 16:
            probability += 0.18
        elif goal_distance < 22:
            probability += 0.10
        elif goal_distance < 30:
            probability += 0.04

        return clamp(
            probability,
            0.04,
            0.50,
        )

    def _shoot(
        self,
        side: str,
        shooter: Dict[str, Any],
    ):
        team = self._team(side)
        opponent = self._opponent(side)

        stats = self._ensure_team_stats(
            team
        )

        stats[
            "shots"
        ] += 1

        shooter[
            "shots"
        ] += 1

        if side == "home":
            goal_x = 100
        else:
            goal_x = 0

        goal_distance = abs(
            goal_x
            - shooter["x"]
        )

        shooting = shooter.get(
            "shooting",
            65,
        )

        goalkeeper = self._goalkeeper(
            opponent
        )

        keeper_rating = (
            goalkeeper.get(
                "goalkeeping",
                65,
            )
            if goalkeeper
            else 65
        )

        base_goal_probability = (
            0.035
            + (
                shooting
                / 100
            ) * 0.07
        )

        if goal_distance < 14:
            base_goal_probability += 0.16
        elif goal_distance < 20:
            base_goal_probability += 0.10
        elif goal_distance < 27:
            base_goal_probability += 0.055

        angle_factor = 1.0 - (
            abs(
                shooter["y"]
                - 30
            )
            / 45
        )

        base_goal_probability *= (
            0.70
            + (
                angle_factor
                * 0.40
            )
        )

        base_goal_probability -= (
            keeper_rating
            / 100
        ) * 0.035

        goal_probability = clamp(
            base_goal_probability,
            0.015,
            0.35,
        )

        stats[
            "shotsOnTarget"
        ] += 1

        shot_on_target = chance(
            0.45
            + (
                shooting
                / 100
            ) * 0.30
        )

        if shot_on_target:
            if chance(
                goal_probability
            ):
                self._goal(
                    side,
                    shooter,
                )
                return

            if goalkeeper:
                self._save(
                    side,
                    shooter,
                    goalkeeper,
                )
                return

        self._miss(
            side,
            shooter,
        )

    # ========================================================
    # GOAL
    # ========================================================

    def _goal(
        self,
        side: str,
        scorer: Dict[str, Any],
    ):
        team = self._team(side)
        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        stats = self._ensure_team_stats(
            team
        )

        stats[
            "goals"
        ] += 1

        scorer[
            "goals"
        ] += 1

        self.score[
            side
        ] += 1

        self.ball[
            "owner"
        ] = None

        self.ball[
            "team"
        ] = None

        self.ball[
            "x"
        ] = 50

        self.ball[
            "y"
        ] = 30

        self._add_event(
            "goal",
            f"GOAL! {scorer['name']} scored for {team['name']}",
            team=side,
            player=scorer,
            extra={
                "score": dict(
                    self.score
                ),
            },
        )

        # reset formations
        self._apply_formation_positions(
            self.home,
            1,
        )

        self._apply_formation_positions(
            self.away,
            -1,
        )

        # kickoff to team that conceded
        kickoff_team = (
            opponent_side
        )

        kickoff_player = (
            self._find_best_player(
                self._team(
                    kickoff_team
                ),
                "CM",
            )
            or self._find_best_player(
                self._team(
                    kickoff_team
                )
            )
        )

        self._set_ball_owner(
            kickoff_team,
            kickoff_player,
        )

    # ========================================================
    # SAVE
    # ========================================================

    def _save(
        self,
        shooting_side: str,
        shooter: Dict[str, Any],
        goalkeeper: Dict[str, Any],
    ):
        defending_side = (
            "away"
            if shooting_side == "home"
            else "home"
        )

        stats = self._ensure_team_stats(
            self._team(
                defending_side
            )
        )

        stats[
            "saves"
        ] += 1

        self._set_ball_owner(
            defending_side,
            goalkeeper,
        )

        self._add_event(
            "save",
            f"{goalkeeper['name']} made a save from {shooter['name']}",
            team=defending_side,
            player=goalkeeper,
        )

    # ========================================================
    # MISS
    # ========================================================

    def _miss(
        self,
        side: str,
        shooter: Dict[str, Any],
    ):
        goal_x = (
            100
            if side == "home"
            else 0
        )

        direction = (
            1
            if side == "home"
            else -1
        )

        self.ball[
            "x"
        ] = goal_x + (
            2 * direction
        )

        self.ball[
            "y"
        ] = clamp(
            shooter["y"]
            + random.uniform(
                -10,
                10,
            ),
            -2,
            62,
        )

        self.ball[
            "owner"
        ] = None

        self.ball[
            "team"
        ] = None

        self._add_event(
            "shot",
            f"{shooter['name']} missed the target",
            team=side,
            player=shooter,
        )

        # goal kick
        defending_side = (
            "away"
            if side == "home"
            else "home"
        )

        self._add_event(
            "goal_kick",
            f"{self._team(defending_side)['name']} goal kick",
            team=defending_side,
        )

        keeper = self._goalkeeper(
            self._team(
                defending_side
            )
        )

        if keeper:
            self._set_ball_owner(
                defending_side,
                keeper,
            )

    # ========================================================
    # CROSS
    # ========================================================

    def _can_cross(
        self,
        side: str,
        player: Dict[str, Any],
    ) -> bool:
        attacking_x = (
            player["x"]
            if side == "home"
            else 100 - player["x"]
        )

        return (
            attacking_x >= 68
            and (
                player["y"] <= 12
                or player["y"] >= 48
            )
        )

    def _cross(
        self,
        side: str,
        player: Dict[str, Any],
    ):
        team = self._team(side)

        stats = self._ensure_team_stats(
            team
        )

        stats[
            "crosses"
        ] += 1

        if side == "home":
            target_x = 86
        else:
            target_x = 14

        target_y = random.uniform(
            20,
            40,
        )

        accuracy = (
            0.42
            + (
                player.get(
                    "passing",
                    68,
                )
                / 100
            ) * 0.28
        )

        self.ball[
            "owner"
        ] = None

        for p in team[
            "players"
        ]:
            p[
                "hasBall"
            ] = False

        if chance(
            accuracy
        ):
            stats[
                "crossesCompleted"
            ] += 1

            self._set_ball_flight(
                target_x,
                target_y,
                speed=16,
                ball_type="cross",
                team=side,
            )

            self._add_event(
                "cross",
                f"{player['name']} sent a cross into the box",
                team=side,
                player=player,
            )

            self._try_header_after_cross(
                side,
                target_x,
                target_y,
            )

        else:
            self._set_ball_flight(
                target_x,
                target_y
                + random.uniform(
                    -10,
                    10,
                ),
                speed=15,
                ball_type="bad_cross",
                team=side,
            )

            self._add_event(
                "bad_cross",
                f"{player['name']} overhit the cross",
                team=side,
                player=player,
            )

    # ========================================================
    # HEADER
    # ========================================================

    def _try_header_after_cross(
        self,
        side: str,
        target_x: float,
        target_y: float,
    ):
        team = self._team(side)

        attackers = [
            p
            for p in team[
                "players"
            ]
            if p.get(
                "role"
            ) in ATTACKER_ROLES
            and p.get(
                "onPitch",
                True,
            )
        ]

        if not attackers:
            return

        attackers.sort(
            key=lambda p: distance(
                p["x"],
                p["y"],
                target_x,
                target_y,
            )
        )

        receiver = attackers[0]

        if distance(
            receiver["x"],
            receiver["y"],
            target_x,
            target_y,
        ) > 18:
            return

        if chance(
            0.35
        ):
            self._set_ball_owner(
                side,
                receiver,
            )

            self._add_event(
                "header",
                f"{receiver['name']} won the cross",
                team=side,
                player=receiver,
            )

    # ========================================================
    # BALL FLIGHT
    # ========================================================

    def _set_ball_flight(
        self,
        target_x: float,
        target_y: float,
        speed: float,
        ball_type: str,
        team: Optional[str],
    ):
        self.ball[
            "targetX"
        ] = clamp(
            target_x,
            -3,
            103,
        )

        self.ball[
            "targetY"
        ] = clamp(
            target_y,
            -3,
            63,
        )

        self.ball[
            "speed"
        ] = speed

        self.ball[
            "type"
        ] = ball_type

        self.ball[
            "team"
        ] = team

        self.ball[
            "owner"
        ] = None

    # ========================================================
    # GOALKEEPER
    # ========================================================

    def _goalkeeper(
        self,
        team: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        for player in team[
            "players"
        ]:
            if player.get(
                "role"
            ) == "GK":
                return player

        return (
            team["players"][0]
            if team["players"]
            else None
        )

    # ========================================================
    # OPPONENT DISTANCE
    # ========================================================

    def _nearest_opponent(
        self,
        side: str,
        player: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:

        opponent = self._opponent(
            side
        )

        players = [
            p
            for p in opponent[
                "players"
            ]
            if p.get(
                "onPitch",
                True,
            )
        ]

        if not players:
            return None

        return min(
            players,
            key=lambda p: distance(
                p["x"],
                p["y"],
                player["x"],
                player["y"],
            ),
        )

    def _nearest_opponent_distance(
        self,
        side: str,
        player: Dict[str, Any],
    ) -> float:

        opponent = self._nearest_opponent(
            side,
            player,
        )

        if not opponent:
            return 50.0

        return distance(
            opponent["x"],
            opponent["y"],
            player["x"],
            player["y"],
        )

    # ========================================================
    # CORNER
    # ========================================================

    def _set_corner(
        self,
        side: str,
    ):
        stats = self._ensure_team_stats(
            self._team(side)
        )

        stats[
            "corners"
        ] += 1

        self._add_event(
            "corner",
            f"{self._team(side)['name']} won a corner",
            team=side,
        )

        self.ball[
            "x"
        ] = (
            96
            if side == "home"
            else 4
        )

        self.ball[
            "y"
        ] = (
            3
            if random.random() < 0.5
            else 57
        )

        taker = self._find_best_player(
            self._team(side),
            "LW",
        )

        if not taker:
            taker = self._find_best_player(
                self._team(side)
            )

        if taker:
            self._set_ball_owner(
                side,
                taker,
            )

    # ========================================================
    # INTERCEPTION
    # ========================================================

    def _attempt_interception(
        self,
        side: str,
        player: Dict[str, Any],
    ):
        stats = self._ensure_team_stats(
            self._team(side)
        )

        stats[
            "interceptions"
        ] += 1

        player[
            "interceptions"
        ] += 1

        self._set_ball_owner(
            side,
            player,
        )

        self._add_event(
            "interception",
            f"{player['name']} intercepted the ball",
            team=side,
            player=player,
        )

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
            team = self._team(side)

            if (
                team[
                    "substitutionsUsed"
                ] >= 5
            ):
                raise ValueError(
                    "Maximum substitutions reached"
                )

            outgoing = self._find_player(
                team,
                outgoing_id,
            )

            incoming = None

            for player in team[
                "bench"
            ]:
                if str(
                    player["id"]
                ) == str(
                    incoming_id
                ):
                    incoming = player
                    break

            if not outgoing:
                raise ValueError(
                    "Outgoing player not found"
                )

            if not incoming:
                raise ValueError(
                    "Incoming player not found"
                )

            outgoing["onPitch"] = False
            outgoing["hasBall"] = False

            incoming["onPitch"] = True
            incoming["hasBall"] = False

            incoming["x"] = outgoing[
                "x"
            ]

            incoming["y"] = outgoing[
                "y"
            ]

            incoming["targetX"] = outgoing[
                "x"
            ]

            incoming["targetY"] = outgoing[
                "y"
            ]

            incoming["role"] = outgoing[
                "role"
            ]

            incoming[
                "position"
            ] = outgoing[
                "position"
            ]

            team["players"] = [
                incoming
                if p["id"]
                == outgoing["id"]
                else p
                for p in team[
                    "players"
                ]
            ]

            team["bench"] = [
                p
                for p in team[
                    "bench"
                ]
                if p["id"]
                != incoming["id"]
            ]

            team["bench"].append(
                outgoing
            )

            team[
                "substitutionsUsed"
            ] += 1

            self._add_event(
                "substitution",
                f"{incoming['name']} replaced {outgoing['name']}",
                team=side,
                player=incoming,
                extra={
                    "outgoingId": outgoing[
                        "id"
                    ],
                    "incomingId": incoming[
                        "id"
                    ],
                },
            )

            return self.snapshot()

    # ========================================================
    # SNAPSHOT
    # ========================================================

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:

            self._ensure_team_stats(
                self.home
            )

            self._ensure_team_stats(
                self.away
            )

            # Keep match stats synchronized
            self.stats[
                "home"
            ] = dict(
                self.home["stats"]
            )

            self.stats[
                "away"
            ] = dict(
                self.away["stats"]
            )

            return {
                "matchId": self.match_id,

                "status": self.status,

                "minute": round(
                    self.minute,
                    2,
                ),

                "second": round(
                    self.second,
                    2,
                ),

                "score": dict(
                    self.score
                ),

                "ball": dict(
                    self.ball
                ),

                "home": self._snapshot_team(
                    self.home
                ),

                "away": self._snapshot_team(
                    self.away
                ),

                "stats": {
                    "home": dict(
                        self.home[
                            "stats"
                        ]
                    ),
                    "away": dict(
                        self.away[
                            "stats"
                        ]
                    ),
                },

                "events": list(
                    self.events
                ),
            }

    # ========================================================
    # TEAM SNAPSHOT
    # ========================================================

    def _snapshot_team(
        self,
        team: Dict[str, Any],
    ) -> Dict[str, Any]:

        self._ensure_team_stats(
            team
        )

        return {
            "id": team[
                "id"
            ],

            "name": team[
                "name"
            ],

            "logo": team.get(
                "logo",
                "",
            ),

            "formation": team[
                "formation"
            ],

            "tactics": dict(
                team[
                    "tactics"
                ]
            ),

            "substitutionsUsed": team[
                "substitutionsUsed"
            ],

            "stats": dict(
                team[
                    "stats"
                ]
            ),

            "players": [
                self._snapshot_player(
                    p
                )
                for p in team[
                    "players"
                ]
            ],

            "bench": [
                self._snapshot_player(
                    p
                )
                for p in team[
                    "bench"
                ]
            ],
        }

    # ========================================================
    # PLAYER SNAPSHOT
    # ========================================================

    def _snapshot_player(
        self,
        player: Dict[str, Any],
    ) -> Dict[str, Any]:

        return {
            "id": player[
                "id"
            ],

            "name": player[
                "name"
            ],

            "number": player[
                "number"
            ],

            "position": player[
                "position"
            ],

            "role": player[
                "role"
            ],

            "x": round(
                player[
                    "x"
                ],
                2,
            ),

            "y": round(
                player[
                    "y"
                ],
                2,
            ),

            "targetX": round(
                player[
                    "targetX"
                ],
                2,
            ),

            "targetY": round(
                player[
                    "targetY"
                ],
                2,
            ),

            "energy": round(
                player.get(
                    "energy",
                    100,
                ),
                2,
            ),

            "pace": player.get(
                "pace",
                68,
            ),

            "passing": player.get(
                "passing",
                68,
            ),

            "shooting": player.get(
                "shooting",
                65,
            ),

            "dribbling": player.get(
                "dribbling",
                67,
            ),

            "defending": player.get(
                "defending",
                65,
            ),

            "stamina": player.get(
                "stamina",
                75,
            ),

            "strength": player.get(
                "strength",
                70,
            ),

            "vision": player.get(
                "vision",
                68,
            ),

            "goalkeeping": player.get(
                "goalkeeping",
                65,
            ),

            "onPitch": player.get(
                "onPitch",
                True,
            ),

            "hasBall": player.get(
                "hasBall",
                False,
            ),

            "shots": player.get(
                "shots",
                0,
            ),

            "goals": player.get(
                "goals",
                0,
            ),

            "assists": player.get(
                "assists",
                0,
            ),

            "passes": player.get(
                "passes",
                0,
            ),

            "completedPasses": player.get(
                "completedPasses",
                0,
            ),

            "dribbles": player.get(
                "dribbles",
                0,
            ),

            "tackles": player.get(
                "tackles",
                0,
            ),

            "interceptions": player.get(
                "interceptions",
                0,
            ),

            "yellowCard": player.get(
                "yellowCard",
                False,
            ),

            "redCard": player.get(
                "redCard",
                False,
            ),
        }
