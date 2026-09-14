from __future__ import annotations

import copy
import math
import random
import threading
import time
from typing import Any


# ============================================================
# CONSTANTS
# ============================================================

PITCH_WIDTH = 100.0
PITCH_HEIGHT = 60.0

REAL_MATCH_SECONDS = 480.0
FOOTBALL_MINUTES = 90.0

HALF_REAL_SECONDS = REAL_MATCH_SECONDS / 2.0


DEFAULT_TACTICS = {
    "mentality": "balanced",
    "tempo": "normal",
    "pressing": "medium",
    "defensiveLine": "medium",
    "width": "normal",
}


FORMATIONS = {
    "4-4-2": [
        (8, 30),
        (20, 8),
        (20, 23),
        (20, 37),
        (20, 52),
        (38, 8),
        (38, 23),
        (38, 37),
        (38, 52),
        (52, 23),
        (52, 37),
    ],

    "4-3-3": [
        (8, 30),
        (20, 8),
        (20, 23),
        (20, 37),
        (20, 52),
        (38, 16),
        (38, 30),
        (38, 44),
        (52, 10),
        (52, 30),
        (52, 50),
    ],

    "3-5-2": [
        (8, 30),
        (20, 15),
        (20, 30),
        (20, 45),
        (35, 7),
        (35, 20),
        (35, 30),
        (35, 40),
        (35, 53),
        (52, 23),
        (52, 37),
    ],

    "5-3-2": [
        (8, 30),
        (18, 7),
        (18, 19),
        (18, 30),
        (18, 41),
        (18, 53),
        (37, 15),
        (37, 30),
        (37, 45),
        (52, 23),
        (52, 37),
    ],

    "4-2-3-1": [
        (8, 30),
        (20, 8),
        (20, 23),
        (20, 37),
        (20, 52),
        (35, 20),
        (35, 40),
        (47, 10),
        (47, 30),
        (47, 50),
        (58, 30),
    ],
}


FORMATION_ROLES = {
    "4-4-2": [
        "GK",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "MID",
        "MID",
        "MID",
        "MID",
        "FWD",
        "FWD",
    ],

    "4-3-3": [
        "GK",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "MID",
        "MID",
        "MID",
        "FWD",
        "FWD",
        "FWD",
    ],

    "3-5-2": [
        "GK",
        "DEF",
        "DEF",
        "DEF",
        "MID",
        "MID",
        "MID",
        "MID",
        "MID",
        "FWD",
        "FWD",
    ],

    "5-3-2": [
        "GK",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "MID",
        "MID",
        "MID",
        "FWD",
        "FWD",
    ],

    "4-2-3-1": [
        "GK",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "MID",
        "MID",
        "MID",
        "MID",
        "MID",
        "FWD",
    ],
}


# ============================================================
# HELPERS
# ============================================================

def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(maximum, value),
    )


def distance(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    return math.sqrt(
        (x2 - x1) ** 2
        + (y2 - y1) ** 2
    )


def move_towards(
    x: float,
    y: float,
    tx: float,
    ty: float,
    amount: float,
) -> tuple[float, float]:

    dx = tx - x
    dy = ty - y

    length = math.sqrt(
        dx * dx + dy * dy
    )

    if length <= amount or length == 0:
        return tx, ty

    ratio = amount / length

    return (
        x + dx * ratio,
        y + dy * ratio,
    )


def rating(
    player: dict[str, Any],
    name: str,
    default: float = 60,
) -> float:
    try:
        return float(
            player.get(
                name,
                default,
            )
        )
    except Exception:
        return default


def player_name(
    player: dict[str, Any],
) -> str:
    return str(
        player.get(
            "name",
            player.get(
                "displayName",
                "Player",
            ),
        )
    )


def player_id(
    player: dict[str, Any],
) -> str:
    return str(
        player.get(
            "id",
            player.get(
                "playerId",
                "",
            ),
        )
    )


def create_fallback_player(
    team_prefix: str,
    index: int,
) -> dict[str, Any]:

    return {
        "id": f"{team_prefix}-fallback-{index}",
        "name": f"{team_prefix.title()} Player {index}",
        "number": index,
        "position": "MID",
        "overall": 60,
        "pace": 60,
        "passing": 60,
        "dribbling": 60,
        "shooting": 60,
        "defending": 60,
        "stamina": 80,
    }


# ============================================================
# FOOTBALL MATCH
# ============================================================

class FootballMatch:

    def __init__(
        self,
        config: dict[str, Any],
    ):

        self.lock = threading.RLock()

        self.match_id = str(
            config.get(
                "matchId",
                "",
            )
        )

        self.config = copy.deepcopy(
            config
        )

        self.status = "ready"

        self.phase = "first_half"

        self.running = False

        self.match_seconds = self._initial_seconds(
            config
        )

        self.events = copy.deepcopy(
            config.get(
                "initialEvents",
                [],
            )
        )

        self.score = {
            "home": int(
                config.get(
                    "initialScore",
                    {},
                ).get(
                    "home",
                    0,
                )
            ),
            "away": int(
                config.get(
                    "initialScore",
                    {},
                ).get(
                    "away",
                    0,
                )
            ),
        }

        self.possession_seconds = {
            "home": 0.0,
            "away": 0.0,
        }

        self.event_counter = (
            len(self.events)
        )

        self.ball = {
            "x": 50.0,
            "y": 30.0,
            "ownerId": None,
            "phase": "kickoff",
            "flight": None,
            "setPiece": None,
        }

        self.restart = None

        self.thread = None

        self.stop_event = threading.Event()

        self._create_teams(
            config
        )

        self._prepare_initial_state()

    # ========================================================
    # INITIAL TIME
    # ========================================================

    def _initial_seconds(
        self,
        config: dict[str, Any],
    ) -> float:

        minute = float(
            config.get(
                "initialMinute",
                0,
            )
        )

        second = float(
            config.get(
                "initialSecond",
                0,
            )
        )

        return clamp(
            (
                minute * 60
                + second
            )
            * REAL_MATCH_SECONDS
            / (90 * 60),
            0,
            REAL_MATCH_SECONDS,
        )

    # ========================================================
    # TEAMS
    # ========================================================

    def _create_teams(
        self,
        config: dict[str, Any],
    ):

        home_players = config.get(
            "homePlayers",
            [],
        )

        away_players = config.get(
            "awayPlayers",
            [],
        )

        home_lineup = config.get(
            "homeLineupIds",
            [],
        )

        away_lineup = config.get(
            "awayLineupIds",
            [],
        )

        self.home = self._create_team(
            "home",
            config.get(
                "homeTeam",
                {},
            ),
            home_players,
            home_lineup,
            config.get(
                "homeFormation",
                "4-4-2",
            ),
            config.get(
                "homeTactics",
                {},
            ),
        )

        self.away = self._create_team(
            "away",
            config.get(
                "awayTeam",
                {},
            ),
            away_players,
            away_lineup,
            config.get(
                "awayFormation",
                "4-4-2",
            ),
            config.get(
                "awayTactics",
                {},
            ),
        )

    def _create_team(
        self,
        side: str,
        team_data: Any,
        source_players: list[Any],
        lineup_ids: list[Any],
        formation: str,
        tactics: dict[str, Any],
    ):

        team_data = (
            team_data
            if isinstance(
                team_data,
                dict,
            )
            else {}
        )

        source_players = (
            source_players
            if isinstance(
                source_players,
                list,
            )
            else []
        )

        lineup_ids = [
            str(x)
            for x in (
                lineup_ids
                if isinstance(
                    lineup_ids,
                    list,
                )
                else []
            )
        ]

        clean_players = []

        for index, player in enumerate(
            source_players
        ):
            if not isinstance(
                player,
                dict,
            ):
                continue

            clean_players.append(
                self._clean_player(
                    player,
                    index,
                    side,
                )
            )

        if len(clean_players) < 18:
            existing_ids = {
                p["id"]
                for p in clean_players
            }

            for i in range(
                1,
                19,
            ):

                fallback = (
                    create_fallback_player(
                        side,
                        i,
                    )
                )

                if fallback["id"] not in existing_ids:
                    clean_players.append(
                        fallback
                    )

                if len(clean_players) >= 18:
                    break

        by_id = {
            p["id"]: p
            for p in clean_players
        }

        selected = []

        for pid in lineup_ids:
            player = by_id.get(pid)

            if player and player not in selected:
                selected.append(player)

        for player in clean_players:
            if len(selected) >= 11:
                break

            if player not in selected:
                selected.append(player)

        selected = selected[:11]

        bench = [
            p
            for p in clean_players
            if p not in selected
        ]

        if formation not in FORMATIONS:
            formation = "4-4-2"

        roles = FORMATION_ROLES[
            formation
        ]

        positions = FORMATIONS[
            formation
        ]

        players = []

        for index, player in enumerate(
            selected
        ):

            role = roles[index]

            base_x, base_y = positions[
                index
            ]

            if side == "away":
                base_x = (
                    PITCH_WIDTH
                    - base_x
                )

            player = copy.deepcopy(
                player
            )

            player["role"] = role
            player["onPitch"] = True
            player["substituted"] = False
            player["hasBall"] = False

            player["x"] = float(
                base_x
            )

            player["y"] = float(
                base_y
            )

            player["targetX"] = float(
                base_x
            )

            player["targetY"] = float(
                base_y
            )

            player["actionCooldown"] = random.uniform(
                0.2,
                1.2,
            )

            players.append(player)

        for player in bench:
            player["onPitch"] = False
            player["substituted"] = False
            player["hasBall"] = False
            player["x"] = -10
            player["y"] = -10
            player["targetX"] = -10
            player["targetY"] = -10

        merged_tactics = {
            **DEFAULT_TACTICS,
            **(
                tactics
                if isinstance(
                    tactics,
                    dict,
                )
                else {}
            ),
        }

        return {
            "id": str(
                team_data.get(
                    "id",
                    f"{side}-team",
                )
            ),
            "name": str(
                team_data.get(
                    "name",
                    side.title(),
                )
            ),
            "logo": team_data.get(
                "logo"
            ),
            "formation": formation,
            "tactics": merged_tactics,
            "players": players,
            "bench": bench,
            "substitutionsUsed": 0,
            "stats": self._empty_stats(),
        }

    def _clean_player(
        self,
        player: dict[str, Any],
        index: int,
        side: str,
    ):

        pid = player_id(
            player
        )

        if not pid:
            pid = (
                f"{side}-player-{index}"
            )

        return {
            "id": pid,
            "name": player_name(
                player
            ),
            "number": int(
                player.get(
                    "number",
                    player.get(
                        "shirtNumber",
                        index + 1,
                    ),
                )
                or index + 1
            ),
            "position": str(
                player.get(
                    "position",
                    "MID",
                )
            ),
            "overall": rating(
                player,
                "overall",
            ),
            "pace": rating(
                player,
                "pace",
            ),
            "passing": rating(
                player,
                "passing",
            ),
            "dribbling": rating(
                player,
                "dribbling",
            ),
            "shooting": rating(
                player,
                "shooting",
            ),
            "defending": rating(
                player,
                "defending",
            ),
            "stamina": rating(
                player,
                "stamina",
                80,
            ),
        }

    def _empty_stats(self):
        return {
            "passes": 0,
            "completedPasses": 0,
            "shots": 0,
            "shotsOnTarget": 0,
            "goals": 0,
            "corners": 0,
            "tackles": 0,
            "interceptions": 0,
            "saves": 0,
            "dribbles": 0,
            "dribblesWon": 0,
            "fouls": 0,
        }

    # ========================================================
    # INITIAL STATE
    # ========================================================

    def _prepare_initial_state(self):

        if self.match_seconds >= REAL_MATCH_SECONDS:
            self.status = "finished"
            self.phase = "second_half"

            self.ball["phase"] = "fulltime"

            return

        if self.match_seconds >= HALF_REAL_SECONDS:
            self.status = "halftime"
            self.phase = "first_half"

            self._set_kickoff(
                "away"
            )

            return

        self.status = "ready"

        self.phase = "first_half"

        self._set_kickoff(
            "home"
        )

    # ========================================================
    # MATCH CONTROL
    # ========================================================

    def start(self):

        with self.lock:

            if self.status == "finished":
                return self.snapshot()

            if self.status == "halftime":
                self.phase = "second_half"

                self.status = "live"

                self._set_kickoff(
                    "away"
                )

            elif self.status in (
                "ready",
                "paused",
            ):

                if self.match_seconds >= HALF_REAL_SECONDS:
                    self.phase = "second_half"

                    self._set_kickoff(
                        "away"
                    )

                else:
                    self.phase = "first_half"

                    if not self.restart:
                        self._set_kickoff(
                            "home"
                        )

                self.status = "live"

            else:
                return self.snapshot()

            self.running = True

            self.stop_event.clear()

            if (
                self.thread is None
                or not self.thread.is_alive()
            ):

                self.thread = threading.Thread(
                    target=self._run_loop,
                    daemon=True,
                )

                self.thread.start()

            return self.snapshot()

    def pause(self):

        with self.lock:

            if self.status == "live":
                self.status = "paused"

            self.running = False

            self.stop_event.set()

            return self.snapshot()

    def finish(self):

        with self.lock:

            self.running = False

            self.stop_event.set()

            self.match_seconds = REAL_MATCH_SECONDS

            self.status = "finished"

            self.phase = "second_half"

            self.ball["phase"] = "fulltime"

            self.ball["flight"] = None

            self.ball["setPiece"] = None

            self.restart = None

            self._add_event(
                "fulltime",
                None,
                None,
                "Full time",
            )

            return self.snapshot()

    # ========================================================
    # BACKGROUND LOOP
    # ========================================================

    def _run_loop(self):

        last = time.monotonic()

        while True:

            if self.stop_event.is_set():
                break

            with self.lock:

                if not self.running:
                    break

                now = time.monotonic()

                dt = now - last

                last = now

                dt = clamp(
                    dt,
                    0.01,
                    0.15,
                )

                self._simulate(
                    dt
                )

            time.sleep(0.05)

    # ========================================================
    # SIMULATION
    # ========================================================

    def _simulate(
        self,
        dt: float,
    ):

        if self.status != "live":
            return

        self.match_seconds += dt

        if self.match_seconds >= REAL_MATCH_SECONDS:
            self.match_seconds = REAL_MATCH_SECONDS

            self.status = "finished"

            self.running = False

            self.ball["phase"] = "fulltime"

            self._add_event(
                "fulltime",
                None,
                None,
                "Full time",
            )

            return

        if (
            self.phase == "first_half"
            and self.match_seconds >= HALF_REAL_SECONDS
        ):

            self.match_seconds = HALF_REAL_SECONDS

            self.status = "halftime"

            self.running = False

            self.ball["phase"] = "halftime"

            self._add_event(
                "halftime",
                None,
                None,
                "Half time",
            )

            return

        self._update_possession(
            dt
        )

        self._update_stamina(
            dt
        )

        self._update_player_targets()

        self._move_players(
            dt
        )

        self._update_ball(
            dt
        )

        self._update_cooldowns(
            dt
        )

        self._sync_ball_owner()

    # ========================================================
    # STAMINA
    # ========================================================

    def _update_stamina(
        self,
        dt: float,
    ):

        for side in (
            "home",
            "away",
        ):

            team = self._team(
                side
            )

            for player in team[
                "players"
            ]:

                if not player[
                    "onPitch"
                ]:
                    continue

                stamina = float(
                    player.get(
                        "stamina",
                        80,
                    )
                )

                pressure_mode = team[
                    "tactics"
                ].get(
                    "pressing",
                    "medium",
                )

                drain = 0.005

                if pressure_mode == "high":
                    drain = 0.012

                elif pressure_mode == "low":
                    drain = 0.003

                player[
                    "stamina"
                ] = clamp(
                    stamina
                    - drain * dt,
                    45,
                    100,
                )

    # ========================================================
    # TACTICAL TARGETS
    # ========================================================

    def _update_player_targets(self):

        owner_id = self.ball.get(
            "ownerId"
        )

        owner_side = (
            self._side_of_player(
                owner_id
            )
            if owner_id
            else None
        )

        for side in (
            "home",
            "away",
        ):

            team = self._team(
                side
            )

            formation = team[
                "formation"
            ]

            positions = FORMATIONS.get(
                formation,
                FORMATIONS["4-4-2"],
            )

            roles = FORMATION_ROLES.get(
                formation,
                FORMATION_ROLES["4-4-2"],
            )

            tactics = team[
                "tactics"
            ]

            for index, player in enumerate(
                team["players"]
            ):

                if not player[
                    "onPitch"
                ]:
                    continue

                base_x, base_y = positions[
                    min(
                        index,
                        len(positions) - 1,
                    )
                ]

                if side == "away":
                    base_x = (
                        PITCH_WIDTH
                        - base_x
                    )

                role = roles[
                    min(
                        index,
                        len(roles) - 1,
                    )
                ]

                player["role"] = role

                target_x = base_x
                target_y = base_y

                forward = (
                    1
                    if side == "home"
                    else -1
                )

                mentality = tactics.get(
                    "mentality",
                    "balanced",
                )

                defensive_line = tactics.get(
                    "defensiveLine",
                    "medium",
                )

                width = tactics.get(
                    "width",
                    "normal",
                )

                pressing = tactics.get(
                    "pressing",
                    "medium",
                )

                # Width
                if width == "wide":
                    target_y = (
                        30
                        + (
                            target_y - 30
                        )
                        * 1.18
                    )

                elif width == "narrow":
                    target_y = (
                        30
                        + (
                            target_y - 30
                        )
                        * 0.72
                    )

                # Mentality
                if mentality == "attacking":
                    if role == "FWD":
                        target_x += (
                            forward * 7
                        )
                    elif role == "MID":
                        target_x += (
                            forward * 4
                        )

                elif mentality == "defensive":
                    target_x -= (
                        forward * 4
                    )

                # Defensive line
                if defensive_line == "high":
                    target_x += (
                        forward * 4
                    )

                elif defensive_line == "low":
                    target_x -= (
                        forward * 5
                    )

                # Own possession
                if owner_side == side:

                    ball_x = self.ball[
                        "x"
                    ]

                    if role == "FWD":
                        target_x += (
                            forward
                            * clamp(
                                abs(
                                    ball_x
                                    - 50
                                )
                                * 0.08,
                                0,
                                7,
                            )
                        )

                    elif role == "MID":
                        target_x += (
                            forward
                            * 2
                        )

                # Opponent possession
                elif owner_side and owner_side != side:

                    ball_x = self.ball[
                        "x"
                    ]

                    shift = (
                        ball_x - 50
                    ) * 0.14

                    if side == "away":
                        shift = -shift

                    target_x += clamp(
                        shift,
                        -7,
                        7,
                    )

                    # Defenders track danger
                    if role == "DEF":

                        opponent = self._player(
                            owner_id
                        )

                        if opponent:

                            target_x = (
                                target_x
                                * 0.65
                                + opponent[
                                    "x"
                                ]
                                * 0.35
                            )

                            target_y = (
                                target_y
                                * 0.55
                                + opponent[
                                    "y"
                                ]
                                * 0.45
                            )

                    # High pressing
                    if pressing == "high":

                        nearest = self._nearest_players(
                            side,
                            self.ball["x"],
                            self.ball["y"],
                        )

                        if (
                            nearest
                            and nearest[0][0]["id"]
                            == player["id"]
                        ):
                            target_x = self.ball[
                                "x"
                            ]
                            target_y = self.ball[
                                "y"
                            ]

                        elif (
                            len(nearest) > 1
                            and nearest[1][0]["id"]
                            == player["id"]
                        ):
                            target_x = self.ball[
                                "x"
                            ]
                            target_y = self.ball[
                                "y"
                            ]

                target_x = clamp(
                    target_x,
                    3,
                    97,
                )

                target_y = clamp(
                    target_y,
                    3,
                    57,
                )

                player[
                    "targetX"
                ] = target_x

                player[
                    "targetY"
                ] = target_y

    # ========================================================
    # PLAYER MOVEMENT
    # ========================================================

    def _move_players(
        self,
        dt: float,
    ):

        owner_id = self.ball.get(
            "ownerId"
        )

        for side in (
            "home",
            "away",
        ):

            team = self._team(
                side
            )

            pressing = team[
                "tactics"
            ].get(
                "pressing",
                "medium",
            )

            for player in team[
                "players"
            ]:

                if not player[
                    "onPitch"
                ]:
                    continue

                if player[
                    "id"
                ] == owner_id:
                    continue

                pace = rating(
                    player,
                    "pace",
                    60,
                )

                stamina = rating(
                    player,
                    "stamina",
                    80,
                )

                speed = (
                    3.0
                    + pace / 100 * 3.0
                )

                stamina_factor = (
                    0.72
                    + stamina / 100 * 0.28
                )

                if pressing == "high":
                    speed *= 1.06

                amount = (
                    speed
                    * stamina_factor
                    * dt
                )

                x, y = move_towards(
                    player["x"],
                    player["y"],
                    player["targetX"],
                    player["targetY"],
                    amount,
                )

                player["x"] = clamp(
                    x,
                    2,
                    98,
                )

                player["y"] = clamp(
                    y,
                    2,
                    58,
                )

    # ========================================================
    # BALL
    # ========================================================

    def _update_ball(
        self,
        dt: float,
    ):

        if self.ball.get(
            "flight"
        ):

            self._advance_ball_flight(
                dt
            )

            return

        if self.restart:

            self._handle_restart(
                dt
            )

            return

        if self.ball.get(
            "setPiece"
        ):

            self._handle_corner(
                dt
            )

            return

        owner_id = self.ball.get(
            "ownerId"
        )

        if owner_id:

            owner = self._player(
                owner_id
            )

            if not owner:
                self.ball[
                    "ownerId"
                ] = None
                return

            self.ball[
                "x"
            ] = owner["x"]

            self.ball[
                "y"
            ] = owner["y"]

            self.ball[
                "phase"
            ] = "controlled"

            self._carrier_action(
                owner
            )

        else:
            self._find_loose_ball_owner()

    # ========================================================
    # CARRIER
    # ========================================================

    def _carrier_action(
        self,
        player: dict[str, Any],
    ):

        cooldown = float(
            player.get(
                "actionCooldown",
                0,
            )
        )

        if cooldown > 0:
            return

        player[
            "actionCooldown"
        ] = random.uniform(
            0.7,
            1.6,
        )

        side = self._side_of_player(
            player["id"]
        )

        if not side:
            return

        goal_x = (
            100
            if side == "home"
            else 0
        )

        dist_goal = distance(
            player["x"],
            player["y"],
            goal_x,
            30,
        )

        pressure = self._pressure(
            side,
            player["x"],
            player["y"],
        )

        in_box = self._inside_box(
            side,
            player["x"],
            player["y"],
        )

        role = player.get(
            "role",
            "MID",
        )

        shooting = rating(
            player,
            "shooting",
            60,
        )

        passing = rating(
            player,
            "passing",
            60,
        )

        dribbling = rating(
            player,
            "dribbling",
            60,
        )

        # Goalkeeper prefers passing
        if role == "GK":

            target = self._best_pass_target(
                side,
                player,
            )

            if target:
                self._start_pass(
                    player,
                    target,
                )

            return

        # Close to goal -> shooting
        if (
            in_box
            and (
                random.random()
                <
                0.42
                + shooting / 300
            )
        ):

            self._start_shot(
                player
            )

            return

        # Good shooting range
        if (
            dist_goal < 23
            and random.random()
            <
            0.20
            + shooting / 450
        ):

            self._start_shot(
                player
            )

            return

        # Heavy pressure -> pass
        if pressure > 0.62:

            target = self._best_pass_target(
                side,
                player,
            )

            if target:
                self._start_pass(
                    player,
                    target,
                )

                return

        # Dribble when space exists
        dribble_probability = (
            0.18
            + dribbling / 300
        )

        if (
            pressure < 0.55
            and random.random()
            < dribble_probability
        ):

            self._dribble(
                player
            )

            return

        # Passing
        target = self._best_pass_target(
            side,
            player,
        )

        if (
            target
            and random.random()
            <
            0.55
            + passing / 250
        ):

            self._start_pass(
                player,
                target,
            )

            return

        # Otherwise carry forward
        forward = (
            1
            if side == "home"
            else -1
        )

        player[
            "targetX"
        ] = clamp(
            player["x"]
            + forward * random.uniform(
                5,
                11,
            ),
            3,
            97,
        )

        player[
            "targetY"
        ] = clamp(
            player["y"]
            + random.uniform(
                -4,
                4,
            ),
            3,
            57,
        )

    # ========================================================
    # PASSING
    # ========================================================

    def _best_pass_target(
        self,
        side: str,
        passer: dict[str, Any],
    ):

        team = self._team(
            side
        )

        opponents = self._team(
            "away"
            if side == "home"
            else "home"
        )[
            "players"
        ]

        candidates = []

        forward = (
            1
            if side == "home"
            else -1
        )

        for player in team[
            "players"
        ]:

            if not player[
                "onPitch"
            ]:
                continue

            if player[
                "id"
            ] == passer[
                "id"
            ]:
                continue

            dist = distance(
                passer["x"],
                passer["y"],
                player["x"],
                player["y"],
            )

            if dist > 40:
                continue

            space = self._space_around(
                player,
                opponents,
            )

            forward_gain = (
                player["x"]
                - passer["x"]
            ) * forward

            score = (
                space * 2.0
                + forward_gain * 0.8
                - dist * 0.45
            )

            if player.get(
                "role"
            ) == "FWD":
                score += 4

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

    def _start_pass(
        self,
        passer: dict[str, Any],
        target: dict[str, Any],
    ):

        side = self._side_of_player(
            passer["id"]
        )

        if not side:
            return

        opponents_side = (
            "away"
            if side == "home"
            else "home"
        )

        opponents = self._team(
            opponents_side
        )[
            "players"
        ]

        dist = distance(
            passer["x"],
            passer["y"],
            target["x"],
            target["y"],
        )

        pressure = self._pressure(
            side,
            passer["x"],
            passer["y"],
        )

        passing = rating(
            passer,
            "passing",
            60,
        )

        success_probability = (
            0.82
            + (passing - 60)
            / 250
            - dist / 130
            - pressure * 0.18
        )

        success_probability = clamp(
            success_probability,
            0.25,
            0.96,
        )

        success = (
            random.random()
            < success_probability
        )

        destination = target

        if not success:

            nearest = self._nearest_opponent(
                side,
                passer["x"],
                passer["y"],
            )

            if nearest:
                destination = nearest

        duration = clamp(
            0.25
            + dist / 55,
            0.25,
            1.05,
        )

        self.ball[
            "ownerId"
        ] = None

        self.ball[
            "phase"
        ] = "pass"

        self.ball[
            "flight"
        ] = {
            "kind": "pass",
            "startX": passer["x"],
            "startY": passer["y"],
            "endX": destination["x"],
            "endY": destination["y"],
            "duration": duration,
            "elapsed": 0.0,
            "targetId": destination[
                "id"
            ],
            "success": success,
            "passerId": passer[
                "id"
            ],
            "team": side,
        }

    # ========================================================
    # DRIBBLING
    # ========================================================

    def _dribble(
        self,
        player: dict[str, Any],
    ):

        side = self._side_of_player(
            player["id"]
        )

        if not side:
            return

        team = self._team(
            side
        )

        team["stats"][
            "dribbles"
        ] += 1

        defender = self._nearest_opponent(
            side,
            player["x"],
            player["y"],
        )

        if defender:

            defending = rating(
                defender,
                "defending",
                60,
            )

            dribbling = rating(
                player,
                "dribbling",
                60,
            )

            pace = rating(
                player,
                "pace",
                60,
            )

            defender_pace = rating(
                defender,
                "pace",
                60,
            )

            probability = (
                0.50
                + (
                    dribbling
                    + pace
                    - defending
                    - defender_pace
                )
                / 240
            )

            probability = clamp(
                probability,
                0.18,
                0.90,
            )

            success = (
                random.random()
                < probability
            )

            if not success:

                self.ball[
                    "ownerId"
                ] = defender[
                    "id"
                ]

                self.ball[
                    "phase"
                ] = "tackle"

                self._team(
                    "away"
                    if side == "home"
                    else "home"
                )[
                    "stats"
                ][
                    "tackles"
                ] += 1

                self._add_event(
                    "tackle",
                    side,
                    player,
                    f"{player_name(player)} lost the ball to {player_name(defender)}",
                )

                return

            team["stats"][
                "dribblesWon"
            ] += 1

        forward = (
            1
            if side == "home"
            else -1
        )

        player[
            "targetX"
        ] = clamp(
            player["x"]
            + forward * random.uniform(
                5,
                10,
            ),
            3,
            97,
        )

        player[
            "targetY"
        ] = clamp(
            player["y"]
            + random.uniform(
                -4,
                4,
            ),
            3,
            57,
        )

        self._add_event(
            "dribble",
            side,
            player,
            f"{player_name(player)} dribbles forward",
        )

    # ========================================================
    # SHOOTING
    # ========================================================

    def _start_shot(
        self,
        player: dict[str, Any],
    ):

        side = self._side_of_player(
            player["id"]
        )

        if not side:
            return

        team = self._team(
            side
        )

        team["stats"][
            "shots"
        ] += 1

        goal_x = (
            100
            if side == "home"
            else 0
        )

        goal_distance = distance(
            player["x"],
            player["y"],
            goal_x,
            30,
        )

        pressure = self._pressure(
            side,
            player["x"],
            player["y"],
        )

        shooting = rating(
            player,
            "shooting",
            60,
        )

        distance_factor = clamp(
            1
            - (
                goal_distance - 5
            )
            / 38,
            0.15,
            1.0,
        )

        pressure_factor = clamp(
            1
            - pressure * 0.35,
            0.55,
            1.0,
        )

        quality = clamp(
            (
                shooting / 100
                * 0.60
                + distance_factor
                * 0.30
                + pressure_factor
                * 0.10
            ),
            0.10,
            1.0,
        )

        goalkeeper = self._goalkeeper(
            "away"
            if side == "home"
            else "home"
        )

        keeper_rating = (
            rating(
                goalkeeper,
                "overall",
                65,
            )
            if goalkeeper
            else 65
        )

        on_target_probability = clamp(
            0.25
            + quality * 0.62,
            0.25,
            0.92,
        )

        save_probability = clamp(
            0.22
            + keeper_rating / 250
            - quality * 0.35,
            0.08,
            0.72,
        )

        duration = clamp(
            0.35
            + goal_distance / 70,
            0.35,
            0.95,
        )

        end_y = clamp(
            30
            + random.uniform(
                -7,
                7,
            ),
            1,
            59,
        )

        self.ball[
            "ownerId"
        ] = None

        self.ball[
            "phase"
        ] = "shot"

        self.ball[
            "flight"
        ] = {
            "kind": "shot",
            "startX": player["x"],
            "startY": player["y"],
            "endX": goal_x,
            "endY": end_y,
            "duration": duration,
            "elapsed": 0.0,
            "shooterId": player[
                "id"
            ],
            "team": side,
            "quality": quality,
            "onTargetProbability":
                on_target_probability,
            "saveProbability":
                save_probability,
        }

        self._add_event(
            "shot",
            side,
            player,
            f"{player_name(player)} shoots",
        )

    # ========================================================
    # BALL FLIGHT
    # ========================================================

    def _advance_ball_flight(
        self,
        dt: float,
    ):

        flight = self.ball.get(
            "flight"
        )

        if not flight:
            return

        flight[
            "elapsed"
        ] += dt

        duration = max(
            0.01,
            float(
                flight[
                    "duration"
                ]
            ),
        )

        progress = clamp(
            flight[
                "elapsed"
            ] / duration,
            0,
            1,
        )

        start_x = flight[
            "startX"
        ]

        start_y = flight[
            "startY"
        ]

        end_x = flight[
            "endX"
        ]

        end_y = flight[
            "endY"
        ]

        self.ball[
            "x"
        ] = (
            start_x
            + (
                end_x
                - start_x
            )
            * progress
        )

        self.ball[
            "y"
        ] = (
            start_y
            + (
                end_y
                - start_y
            )
            * progress
        )

        if progress < 1:
            return

        self.ball[
            "flight"
        ] = None

        kind = flight[
            "kind"
        ]

        if kind == "pass":
            self._resolve_pass(
                flight
            )

        elif kind == "shot":
            self._resolve_shot(
                flight
            )

    # ========================================================
    # PASS RESULT
    # ========================================================

    def _resolve_pass(
        self,
        flight: dict[str, Any],
    ):

        target_id = flight[
            "targetId"
        ]

        target = self._player(
            target_id
        )

        if not target:
            self.ball[
                "ownerId"
            ] = None
            return

        side = flight[
            "team"
        ]

        success = bool(
            flight[
                "success"
            ]
        )

        if success:

            self.ball[
                "ownerId"
            ] = target[
                "id"
            ]

            self.ball[
                "phase"
            ] = "controlled"

            self._team(
                side
            )[
                "stats"
            ][
                "passes"
            ] += 1

            self._team(
                side
            )[
                "stats"
            ][
                "completedPasses"
            ] += 1

            self._add_event(
                "pass",
                side,
                target,
                f"Pass completed to {player_name(target)}",
            )

        else:

            opponent_side = (
                "away"
                if side == "home"
                else "home"
            )

            self._team(
                side
            )[
                "stats"
            ][
                "passes"
            ] += 1

            self._team(
                opponent_side
            )[
                "stats"
            ][
                "interceptions"
            ] += 1

            self.ball[
                "ownerId"
            ] = target[
                "id"
            ]

            self.ball[
                "phase"
            ] = "interception"

            self._add_event(
                "interception",
                opponent_side,
                target,
                f"{player_name(target)} intercepts the pass",
            )

    # ========================================================
    # SHOT RESULT
    # ========================================================

    def _resolve_shot(
        self,
        flight: dict[str, Any],
    ):

        shooter_id = flight[
            "shooterId"
        ]

        shooter = self._player(
            shooter_id
        )

        if not shooter:
            return

        side = flight[
            "team"
        ]

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        quality = float(
            flight[
                "quality"
            ]
        )

        on_target_probability = float(
            flight[
                "onTargetProbability"
            ]
        )

        save_probability = float(
            flight[
                "saveProbability"
            ]
        )

        on_target = (
            random.random()
            < on_target_probability
        )

        if on_target:

            self._team(
                side
            )[
                "stats"
            ][
                "shotsOnTarget"
            ] += 1

        if (
            on_target
            and random.random()
            > save_probability
        ):

            self._score_goal(
                side,
                shooter,
            )

            return

        if on_target:

            goalkeeper = self._goalkeeper(
                opponent_side
            )

            if goalkeeper:

                self._team(
                    opponent_side
                )[
                    "stats"
                ][
                    "saves"
                ] += 1

                self.ball[
                    "ownerId"
                ] = goalkeeper[
                    "id"
                ]

                self.ball[
                    "phase"
                ] = "saved"

                self._add_event(
                    "save",
                    opponent_side,
                    goalkeeper,
                    f"{player_name(goalkeeper)} makes a save",
                )

                return

        # Missed shot
        corner_chance = (
            0.18
            + quality * 0.12
        )

        if (
            random.random()
            < corner_chance
        ):

            self._set_corner(
                side
            )

        else:

            self._set_goal_kick(
                opponent_side
            )

    # ========================================================
    # GOAL
    # ========================================================

    def _score_goal(
        self,
        side: str,
        scorer: dict[str, Any],
    ):

        self.score[
            side
        ] += 1

        self._team(
            side
        )[
            "stats"
        ][
            "goals"
        ] += 1

        self.ball[
            "x"
        ] = 50

        self.ball[
            "y"
        ] = 30

        self.ball[
            "ownerId"
        ] = None

        self.ball[
            "phase"
        ] = "goal"

        self.ball[
            "flight"
        ] = None

        self.ball[
            "setPiece"
        ] = None

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        self.restart = {
            "type": "kickoff",
            "team": opponent_side,
            "timer": 1.5,
        }

        self._add_event(
            "goal",
            side,
            scorer,
            f"GOAL! {player_name(scorer)} scores",
        )

    # ========================================================
    # CORNER
    # ========================================================

    def _set_corner(
        self,
        attacking_side: str,
    ):

        self._team(
            attacking_side
        )[
            "stats"
        ][
            "corners"
        ] += 1

        corner_y = random.choice(
            [2.0, 58.0]
        )

        corner_x = (
            98.0
            if attacking_side == "home"
            else 2.0
        )

        self.ball[
            "x"
        ] = corner_x

        self.ball[
            "y"
        ] = corner_y

        self.ball[
            "ownerId"
        ] = None

        self.ball[
            "phase"
        ] = "corner"

        self.ball[
            "setPiece"
        ] = {
            "type": "corner",
            "team": attacking_side,
            "timer": 1.0,
        }

        self._add_event(
            "corner",
            attacking_side,
            None,
            "Corner kick",
        )

    def _handle_corner(
        self,
        dt: float,
    ):

        set_piece = self.ball.get(
            "setPiece"
        )

        if not set_piece:
            return

        set_piece[
            "timer"
        ] -= dt

        if set_piece[
            "timer"
        ] > 0:
            return

        side = set_piece[
            "team"
        ]

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        attackers = [
            p
            for p in self._team(
                side
            )[
                "players"
            ]
            if p[
                "onPitch"
            ]
            and p.get(
                "role"
            ) in (
                "FWD",
                "MID",
            )
        ]

        defenders = [
            p
            for p in self._team(
                opponent_side
            )[
                "players"
            ]
            if p[
                "onPitch"
            ]
        ]

        if not attackers:
            self.ball[
                "setPiece"
            ] = None

            return

        target = random.choice(
            attackers
        )

        # Move selected attacker into box
        if side == "home":
            target["x"] = clamp(
                target["x"] + 12,
                65,
                88,
            )
        else:
            target["x"] = clamp(
                target["x"] - 12,
                12,
                35,
            )

        target["y"] = clamp(
            target["y"],
            12,
            48,
        )

        target_space = self._space_around(
            target,
            defenders,
        )

        success_probability = clamp(
            0.45
            + target_space / 30,
            0.25,
            0.82,
        )

        success = (
            random.random()
            < success_probability
        )

        self.ball[
            "setPiece"
        ] = None

        if success:

            self.ball[
                "ownerId"
            ] = target[
                "id"
            ]

            self.ball[
                "x"
            ] = target[
                "x"
            ]

            self.ball[
                "y"
            ] = target[
                "y"
            ]

            self.ball[
                "phase"
            ] = "corner_cross"

            target[
                "actionCooldown"
            ] = 0.1

            self._add_event(
                "cross",
                side,
                target,
                f"Corner reaches {player_name(target)}",
            )

        else:

            defender = random.choice(
                defenders
            ) if defenders else None

            if defender:

                self.ball[
                    "ownerId"
                ] = defender[
                    "id"
                ]

                self.ball[
                    "phase"
                ] = "clearance"

                self._add_event(
                    "clearance",
                    opponent_side,
                    defender,
                    f"{player_name(defender)} clears the corner",
                )

    # ========================================================
    # GOAL KICK / KICKOFF
    # ========================================================

    def _set_goal_kick(
        self,
        side: str,
    ):

        goalkeeper = self._goalkeeper(
            side
        )

        self.restart = {
            "type": "goal_kick",
            "team": side,
            "timer": 1.0,
        }

        self.ball[
            "ownerId"
        ] = None

        self.ball[
            "phase"
        ] = "goal_kick"

        if goalkeeper:
            goalkeeper[
                "x"
            ] = (
                7
                if side == "home"
                else 93
            )

            goalkeeper[
                "y"
            ] = 30

    def _set_kickoff(
        self,
        side: str,
    ):

        self.ball[
            "x"
        ] = 50

        self.ball[
            "y"
        ] = 30

        self.ball[
            "ownerId"
        ] = None

        self.ball[
            "phase"
        ] = "kickoff"

        self.ball[
            "setPiece"
        ] = None

        self.restart = {
            "type": "kickoff",
            "team": side,
            "timer": 1.0,
        }

    def _handle_restart(
        self,
        dt: float,
    ):

        if not self.restart:
            return

        self.restart[
            "timer"
        ] -= dt

        if self.restart[
            "timer"
        ] > 0:
            return

        restart_type = self.restart[
            "type"
        ]

        side = self.restart[
            "team"
        ]

        self.restart = None

        if restart_type == "kickoff":

            players = self._team(
                side
            )[
                "players"
            ]

            candidates = [
                p
                for p in players
                if p[
                    "onPitch"
                ]
                and p.get(
                    "role"
                ) in (
                    "MID",
                    "FWD",
                )
            ]

            if candidates:

                player = min(
                    candidates,
                    key=lambda p: distance(
                        p["x"],
                        p["y"],
                        50,
                        30,
                    ),
                )

                player[
                    "x"
                ] = 50

                player[
                    "y"
                ] = 30

                self.ball[
                    "ownerId"
                ] = player[
                    "id"
                ]

                self.ball[
                    "phase"
                ] = "controlled"

                self._add_event(
                    "kickoff",
                    side,
                    player,
                    "Kick-off",
                )

        elif restart_type == "goal_kick":

            goalkeeper = self._goalkeeper(
                side
            )

            if goalkeeper:

                self.ball[
                    "ownerId"
                ] = goalkeeper[
                    "id"
                ]

                self.ball[
                    "x"
                ] = goalkeeper[
                    "x"
                ]

                self.ball[
                    "y"
                ] = goalkeeper[
                    "y"
                ]

                self.ball[
                    "phase"
                ] = "controlled"

    # ========================================================
    # PRESSURE
    # ========================================================

    def _pressure(
        self,
        attacking_side: str,
        x: float,
        y: float,
    ) -> float:

        defending_side = (
            "away"
            if attacking_side == "home"
            else "home"
        )

        opponents = self._team(
            defending_side
        )[
            "players"
        ]

        pressure = 0.0

        for defender in opponents:

            if not defender[
                "onPitch"
            ]:
                continue

            d = distance(
                x,
                y,
                defender["x"],
                defender["y"],
            )

            if d < 10:

                pressure += (
                    1
                    - d / 10
                )

        return clamp(
            pressure / 2.5,
            0,
            1,
        )

    # ========================================================
    # LOOSE BALL
    # ========================================================

    def _find_loose_ball_owner(
        self,
    ):

        candidates = []

        for side in (
            "home",
            "away",
        ):

            for player in self._team(
                side
            )[
                "players"
            ]:

                if not player[
                    "onPitch"
                ]:
                    continue

                d = distance(
                    player["x"],
                    player["y"],
                    self.ball["x"],
                    self.ball["y"],
                )

                if d < 2.0:
                    candidates.append(
                        (
                            d,
                            player,
                        )
                    )

        if candidates:

            candidates.sort(
                key=lambda item: item[0]
            )

            player = candidates[0][1]

            self.ball[
                "ownerId"
            ] = player[
                "id"
            ]

            self.ball[
                "phase"
            ] = "controlled"

    # ========================================================
    # POSSESSION
    # ========================================================

    def _update_possession(
        self,
        dt: float,
    ):

        owner_id = self.ball.get(
            "ownerId"
        )

        if not owner_id:
            return

        side = self._side_of_player(
            owner_id
        )

        if side:
            self.possession_seconds[
                side
            ] += dt

    # ========================================================
    # COOLDOWNS
    # ========================================================

    def _update_cooldowns(
        self,
        dt: float,
    ):

        for side in (
            "home",
            "away",
        ):

            for player in self._team(
                side
            )[
                "players"
            ]:

                player[
                    "actionCooldown"
                ] = max(
                    0,
                    float(
                        player.get(
                            "actionCooldown",
                            0,
                        )
                    )
                    - dt,
                )

    # ========================================================
    # HELPERS
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

    def _player(
        self,
        pid: Any,
    ):

        if pid is None:
            return None

        pid = str(pid)

        for side in (
            "home",
            "away",
        ):

            for player in self._team(
                side
            )[
                "players"
            ]:

                if player[
                    "id"
                ] == pid:
                    return player

            for player in self._team(
                side
            )[
                "bench"
            ]:

                if player[
                    "id"
                ] == pid:
                    return player

        return None

    def _side_of_player(
        self,
        pid: Any,
    ):

        if pid is None:
            return None

        pid = str(pid)

        for side in (
            "home",
            "away",
        ):

            team = self._team(
                side
            )

            for player in (
                team["players"]
                + team["bench"]
            ):

                if player[
                    "id"
                ] == pid:
                    return side

        return None

    def _goalkeeper(
        self,
        side: str,
    ):

        players = self._team(
            side
        )[
            "players"
        ]

        for player in players:

            if player.get(
                "role"
            ) == "GK":

                return player

        return (
            players[0]
            if players
            else None
        )

    def _nearest_opponent(
        self,
        side: str,
        x: float,
        y: float,
    ):

        opponent_side = (
            "away"
            if side == "home"
            else "home"
        )

        candidates = []

        for player in self._team(
            opponent_side
        )[
            "players"
        ]:

            if not player[
                "onPitch"
            ]:
                continue

            d = distance(
                x,
                y,
                player["x"],
                player["y"],
            )

            candidates.append(
                (
                    d,
                    player,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[0]
        )

        return candidates[0][1]

    def _nearest_players(
        self,
        side: str,
        x: float,
        y: float,
    ):

        candidates = []

        for player in self._team(
            side
        )[
            "players"
        ]:

            if not player[
                "onPitch"
            ]:
                continue

            d = distance(
                x,
                y,
                player["x"],
                player["y"],
            )

            candidates.append(
                (
                    player,
                    d,
                )
            )

        candidates.sort(
            key=lambda item: item[1]
        )

        return candidates

    def _space_around(
        self,
        player: dict[str, Any],
        opponents: list[dict[str, Any]],
    ) -> float:

        nearest = 100.0

        for opponent in opponents:

            if not opponent[
                "onPitch"
            ]:
                continue

            d = distance(
                player["x"],
                player["y"],
                opponent["x"],
                opponent["y"],
            )

            nearest = min(
                nearest,
                d,
            )

        return clamp(
            nearest,
            0,
            15,
        )

    def _inside_box(
        self,
        side: str,
        x: float,
        y: float,
    ) -> bool:

        if not (
            10 <= y <= 50
        ):
            return False

        if side == "home":
            return x >= 82

        return x <= 18

    # ========================================================
    # TACTICS / FORMATION
    # ========================================================

    def set_tactics(
        self,
        side: str,
        tactics: dict[str, Any],
    ):

        with self.lock:

            team = self._team(
                side
            )

            team[
                "tactics"
            ] = {
                **team[
                    "tactics"
                ],
                **tactics,
            }

            return self.snapshot()

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

            team[
                "formation"
            ] = formation

            positions = FORMATIONS[
                formation
            ]

            roles = FORMATION_ROLES[
                formation
            ]

            for index, player in enumerate(
                team["players"]
            ):

                if index >= len(
                    positions
                ):
                    break

                x, y = positions[
                    index
                ]

                if side == "away":
                    x = (
                        PITCH_WIDTH
                        - x
                    )

                player[
                    "role"
                ] = roles[
                    index
                ]

                player[
                    "targetX"
                ] = x

                player[
                    "targetY"
                ] = y

            return self.snapshot()

    # ========================================================
    # SUBSTITUTION
    # ========================================================

    def substitute(
        self,
        side: str,
        outgoing_id: Any,
        incoming_id: Any,
    ):

        with self.lock:

            team = self._team(
                side
            )

            if team[
                "substitutionsUsed"
            ] >= 5:

                raise ValueError(
                    "Maximum of 5 substitutions reached"
                )

            outgoing_id = str(
                outgoing_id
            )

            incoming_id = str(
                incoming_id
            )

            outgoing = None

            for player in team[
                "players"
            ]:

                if player[
                    "id"
                ] == outgoing_id:

                    outgoing = player
                    break

            incoming = None

            for player in team[
                "bench"
            ]:

                if player[
                    "id"
                ] == incoming_id:

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

            incoming[
                "onPitch"
            ] = True

            incoming[
                "substituted"
            ] = True

            incoming[
                "x"
            ] = outgoing[
                "x"
            ]

            incoming[
                "y"
            ] = outgoing[
                "y"
            ]

            incoming[
                "targetX"
            ] = outgoing[
                "targetX"
            ]

            incoming[
                "targetY"
            ] = outgoing[
                "targetY"
            ]

            incoming[
                "role"
            ] = outgoing.get(
                "role",
                "MID",
            )

            outgoing[
                "onPitch"
            ] = False

            outgoing[
                "substituted"
            ] = True

            outgoing[
                "hasBall"
            ] = False

            outgoing[
                "x"
            ] = -10

            outgoing[
                "y"
            ] = -10

            if self.ball.get(
                "ownerId"
            ) == outgoing_id:

                self.ball[
                    "ownerId"
                ] = incoming_id

            team[
                "players"
            ].remove(
                outgoing
            )

            team[
                "bench"
            ].remove(
                incoming
            )

            team[
                "players"
            ].append(
                incoming
            )

            team[
                "bench"
            ].append(
                outgoing
            )

            team[
                "substitutionsUsed"
            ] += 1

            self._add_event(
                "substitution",
                side,
                incoming,
                f"{player_name(incoming)} replaces {player_name(outgoing)}",
            )

            return self.snapshot()

    # ========================================================
    # EVENTS
    # ========================================================

    def _add_event(
        self,
        event_type: str,
        side: str | None,
        player: dict[str, Any] | None,
        message: str,
    ):

        self.event_counter += 1

        minute = int(
            self.match_seconds
            / REAL_MATCH_SECONDS
            * 90
        )

        minute = min(
            90,
            max(0, minute),
        )

        second_float = (
            self.match_seconds
            / REAL_MATCH_SECONDS
            * 90
            * 60
        )

        second = int(
            second_float
            % 60
        )

        event = {
            "id": self.event_counter,
            "type": event_type,
            "team": side,
            "playerId": (
                player["id"]
                if player
                else None
            ),
            "playerName": (
                player_name(player)
                if player
                else None
            ),
            "minute": minute,
            "second": second,
            "clock": (
                f"{minute:02d}:{second:02d}"
            ),
            "message": message,
        }

        self.events.append(
            event
        )

        if len(
            self.events
        ) > 300:

            self.events = self.events[
                -300:
            ]

    # ========================================================
    # BALL OWNER SYNC
    # ========================================================

    def _sync_ball_owner(self):

        owner_id = self.ball.get(
            "ownerId"
        )

        for side in (
            "home",
            "away",
        ):

            for player in self._team(
                side
            )[
                "players"
            ]:

                player[
                    "hasBall"
                ] = (
                    player["id"]
                    == owner_id
                )

    # ========================================================
    # SNAPSHOT
    # ========================================================

    def snapshot(self):

        with self.lock:

            minute_float = (
                self.match_seconds
                / REAL_MATCH_SECONDS
                * 90
            )

            minute = int(
                minute_float
            )

            total_seconds = (
                minute_float * 60
            )

            second = int(
                total_seconds % 60
            )

            total_possession = (
                self.possession_seconds[
                    "home"
                ]
                + self.possession_seconds[
                    "away"
                ]
            )

            if total_possession > 0:

                home_possession = (
                    self.possession_seconds[
                        "home"
                    ]
                    / total_possession
                    * 100
                )

            else:
                home_possession = 50.0

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

            home[
                "stats"
            ][
                "possession"
            ] = round(
                home_possession,
                1,
            )

            away[
                "stats"
            ][
                "possession"
            ] = round(
                away_possession,
                1,
            )

            result = None

            if self.status == "finished":

                if (
                    self.score["home"]
                    >
                    self.score["away"]
                ):
                    winner = "home"

                elif (
                    self.score["away"]
                    >
                    self.score["home"]
                ):
                    winner = "away"

                else:
                    winner = "draw"

                result = {
                    "winner": winner,
                    "home": self.score[
                        "home"
                    ],
                    "away": self.score[
                        "away"
                    ],
                }

            return {
                "matchId": self.match_id,

                "status": self.status,

                "phase": self.phase,

                "running": self.running,

                "minute": minute,

                "second": second,

                "score": copy.deepcopy(
                    self.score
                ),

                "home": home,

                "away": away,

                "ball": copy.deepcopy(
                    self.ball
                ),

                "events": copy.deepcopy(
                    self.events
                ),

                "result": result,

                "realDurationSeconds":
                    REAL_MATCH_SECONDS,
            }
