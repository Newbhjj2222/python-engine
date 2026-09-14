import random
import threading
import time
from typing import Any


PITCH_WIDTH = 100.0
PITCH_HEIGHT = 60.0

MATCH_MINUTES = 90

REAL_MATCH_SECONDS = 480.0

TICK_SECONDS = 0.20

FORMATION_POSITIONS = {
    "4-3-3": [
        ("GK", 5, 30),
        ("LB", 18, 10),
        ("CB", 17, 24),
        ("CB", 17, 36),
        ("RB", 18, 50),
        ("CM", 35, 20),
        ("CM", 36, 30),
        ("CM", 35, 42),
        ("LW", 50, 10),
        ("ST", 55, 30),
        ("RW", 50, 50),
    ],
    "4-4-2": [
        ("GK", 5, 30),
        ("LB", 18, 10),
        ("CB", 17, 24),
        ("CB", 17, 36),
        ("RB", 18, 50),
        ("LM", 35, 10),
        ("CM", 36, 25),
        ("CM", 36, 35),
        ("RM", 35, 50),
        ("ST", 54, 25),
        ("ST", 54, 38),
    ],
    "3-5-2": [
        ("GK", 5, 30),
        ("CB", 17, 20),
        ("CB", 16, 30),
        ("CB", 17, 40),
        ("LWB", 32, 8),
        ("CM", 35, 22),
        ("CM", 37, 30),
        ("CM", 35, 38),
        ("RWB", 32, 52),
        ("ST", 54, 25),
        ("ST", 54, 38),
    ],
    "5-3-2": [
        ("GK", 5, 30),
        ("LB", 17, 8),
        ("CB", 16, 21),
        ("CB", 15, 30),
        ("CB", 16, 39),
        ("RB", 17, 52),
        ("CM", 35, 22),
        ("CM", 36, 30),
        ("CM", 35, 40),
        ("ST", 54, 25),
        ("ST", 54, 38),
    ],
    "4-2-3-1": [
        ("GK", 5, 30),
        ("LB", 18, 10),
        ("CB", 17, 24),
        ("CB", 17, 36),
        ("RB", 18, 50),
        ("DM", 32, 24),
        ("DM", 32, 36),
        ("LW", 46, 10),
        ("AM", 47, 30),
        ("RW", 46, 50),
        ("ST", 55, 30),
    ],
}


def number(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def clamp(value, low, high):
    return max(low, min(high, value))


class FootballMatch:
    def __init__(self, config: dict[str, Any]):
        self.match_id = str(
            config.get("matchId")
            or config.get("id")
        )

        self.lock = threading.RLock()

        self.status = "created"

        self.minute = 0
        self.second = 0

        self.elapsed_real = 0.0

        self.score = {
            "home": 0,
            "away": 0,
        }

        self.home = self._create_team(
            config.get("home", {}),
            "home",
            True,
        )

        self.away = self._create_team(
            config.get("away", {}),
            "away",
            False,
        )

        self.ball = {
            "x": 50.0,
            "y": 30.0,
            "ownerId": None,
            "ownerSide": None,
            "state": "free",
            "targetId": None,
        }

        self.events: list[dict[str, Any]] = []

        self.stats = {
            "home": self._empty_stats(),
            "away": self._empty_stats(),
        }

        self.running = False
        self.thread = None
        self.finished = False

        self.last_action_time = 0.0
        self.last_event_time = 0.0

        self.halftime_done = False

        self._assign_initial_ball()

        self._event(
            0,
            "kickoff",
            "Kick-off",
            None,
        )

    # ---------------------------------------------------------
    # TEAM / PLAYER
    # ---------------------------------------------------------

    def _create_team(
        self,
        source: dict[str, Any],
        side: str,
        is_home: bool,
    ):
        source = source or {}

        raw_players = (
            source.get("players")
            or source.get("lineup")
            or source.get("squad")
            or []
        )

        raw_bench = (
            source.get("bench")
            or source.get("substitutes")
            or []
        )

        if not isinstance(raw_players, list):
            raw_players = []

        if not isinstance(raw_bench, list):
            raw_bench = []

        players = [
            self._create_player(
                player,
                i,
                side,
            )
            for i, player in enumerate(raw_players[:11])
        ]

        bench = [
            self._create_player(
                player,
                i + 11,
                side,
            )
            for i, player in enumerate(raw_bench[:9])
        ]

        if len(players) < 11:
            for i in range(len(players), 11):
                players.append(
                    self._create_player(
                        {},
                        i,
                        side,
                    )
                )

        formation = (
            source.get("formation")
            or "4-3-3"
        )

        if formation not in FORMATION_POSITIONS:
            formation = "4-3-3"

        self._apply_formation(
            players,
            formation,
            is_home,
        )

        return {
            "id": str(
                source.get("id")
                or source.get("clubId")
                or side
            ),
            "name": (
                source.get("name")
                or source.get("clubName")
                or (
                    "Home Team"
                    if is_home
                    else "Away Team"
                )
            ),
            "logo": (
                source.get("logo")
                or source.get("logoUrl")
                or source.get("image")
                or ""
            ),
            "formation": formation,
            "players": players,
            "bench": bench,
            "tactics": {
                "mentality": "balanced",
                "tempo": 65,
                "pressing": "medium",
                "defensiveLine": "medium",
                "width": 55,
            },
            "stats": self._empty_stats(),
            "substitutionsUsed": 0,
        }

    def _create_player(
        self,
        source: dict[str, Any],
        index: int,
        side: str,
    ):
        source = source or {}

        ratings = source.get("ratings") or {}

        pid = str(
            source.get("id")
            or source.get("playerId")
            or f"{side}-player-{index + 1}"
        )

        name = (
            source.get("name")
            or source.get("displayName")
            or source.get("fullName")
            or f"Player {index + 1}"
        )

        return {
            "id": pid,
            "name": name,
            "number": int(
                number(
                    source.get("number")
                    or source.get("shirtNumber")
                    or source.get("jerseyNumber")
                    or index + 1,
                    index + 1,
                )
            ),
            "position": (
                source.get("position")
                or source.get("role")
                or "CM"
            ),
            "role": (
                source.get("role")
                or source.get("position")
                or "CM"
            ),
            "pace": number(
                source.get("pace", ratings.get("pace", 70)),
                70,
            ),
            "passing": number(
                source.get(
                    "passing",
                    ratings.get("passing", 70),
                ),
                70,
            ),
            "shooting": number(
                source.get(
                    "shooting",
                    ratings.get("shooting", 65),
                ),
                65,
            ),
            "dribbling": number(
                source.get(
                    "dribbling",
                    ratings.get("dribbling", 68),
                ),
                68,
            ),
            "defending": number(
                source.get(
                    "defending",
                    ratings.get("defending", 65),
                ),
                65,
            ),
            "stamina": number(
                source.get(
                    "stamina",
                    ratings.get("stamina", 80),
                ),
                80,
            ),
            "strength": number(
                source.get(
                    "strength",
                    ratings.get("strength", 70),
                ),
                70,
            ),
            "vision": number(
                source.get(
                    "vision",
                    ratings.get("vision", 70),
                ),
                70,
            ),
            "goalkeeping": number(
                source.get(
                    "goalkeeping",
                    ratings.get("goalkeeping", 60),
                ),
                60,
            ),
            "x": 50.0,
            "y": 30.0,
            "targetX": 50.0,
            "targetY": 30.0,
            "staminaNow": 100.0,
            "hasBall": False,
            "lastAction": "positioning",
            "lastActionAt": 0.0,
            "goals": 0,
            "assists": 0,
            "shots": 0,
            "passes": 0,
            "completedPasses": 0,
            "tackles": 0,
            "interceptions": 0,
            "saves": 0,
            "yellow": False,
            "red": False,
        }

    def _apply_formation(
        self,
        players,
        formation,
        is_home,
    ):
        positions = FORMATION_POSITIONS[formation]

        for i, player in enumerate(players[:11]):
            role, x, y = positions[i]

            if not is_home:
                x = 100 - x

            player["position"] = role
            player["role"] = role
            player["x"] = float(x)
            player["y"] = float(y)
            player["targetX"] = float(x)
            player["targetY"] = float(y)

    # ---------------------------------------------------------
    # STATS
    # ---------------------------------------------------------

    def _empty_stats(self):
        return {
            "possession": 50,
            "shots": 0,
            "shotsOnTarget": 0,
            "passes": 0,
            "completedPasses": 0,
            "tackles": 0,
            "interceptions": 0,
            "corners": 0,
            "fouls": 0,
            "offsides": 0,
            "saves": 0,
        }

    # ---------------------------------------------------------
    # START / STOP
    # ---------------------------------------------------------

    def start(self):
        with self.lock:
            if self.finished:
                return self.snapshot()

            if self.status == "playing":
                return self.snapshot()

            self.status = "playing"
            self.running = True

            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(
                    target=self._run,
                    daemon=True,
                )
                self.thread.start()

            self._event(
                self.minute,
                "match",
                "Match is live",
                None,
            )

            return self.snapshot()

    def pause(self):
        with self.lock:
            self.running = False

            if not self.finished:
                self.status = "paused"

            return self.snapshot()

    def finish(self):
        with self.lock:
            self.running = False
            self.finished = True
            self.status = "finished"
            self.minute = 90
            self.second = 0

            self._event(
                90,
                "full_time",
                "Full time",
                None,
            )

            return self.snapshot()

    # ---------------------------------------------------------
    # ENGINE LOOP
    # ---------------------------------------------------------

    def _run(self):
        last = time.monotonic()

        while True:
            time.sleep(TICK_SECONDS)

            now = time.monotonic()
            dt = now - last
            last = now

            with self.lock:
                if not self.running:
                    continue

                if self.finished:
                    break

                self._advance(dt)

    def _advance(self, dt):
        self.elapsed_real += dt

        football_seconds = (
            self.elapsed_real
            * MATCH_MINUTES
            * 60
            / REAL_MATCH_SECONDS
        )

        total_seconds = int(
            football_seconds
        )

        if total_seconds >= 90 * 60:
            self.minute = 90
            self.second = 0
            self._finish_internal()
            return

        self.minute = total_seconds // 60
        self.second = total_seconds % 60

        if (
            self.minute >= 45
            and not self.halftime_done
        ):
            self._halftime()

        self._move_players(dt)

        self._run_ai()

        self._update_possession_stats()

    # ---------------------------------------------------------
    # HALFTIME
    # ---------------------------------------------------------

    def _halftime(self):
        self.halftime_done = True
        self.status = "halftime"
        self.running = False

        self._event(
            45,
            "halftime",
            "Half time",
            None,
        )

        self._swap_sides()

    def _swap_sides(self):
        for team in [
            self.home,
            self.away,
        ]:
            for p in team["players"]:
                p["x"] = 100 - p["x"]
                p["targetX"] = 100 - p["targetX"]

        self.ball["x"] = 100 - self.ball["x"]

    def _finish_internal(self):
        self.running = False
        self.finished = True
        self.status = "finished"

        self._event(
            90,
            "full_time",
            "Full time",
            None,
        )

    # ---------------------------------------------------------
    # AI
    # ---------------------------------------------------------

    def _run_ai(self):
        self._recover_ball_if_needed()

        owner = self._get_ball_owner()

        if owner is None:
            self._move_ball()
            return

        side = (
            self.ball["ownerSide"]
            or "home"
        )

        team = self.home if side == "home" else self.away
        opponent = self.away if side == "home" else self.home

        player = self._find_player(
            team,
            owner,
        )

        if not player:
            return

        player["hasBall"] = True

        now = time.monotonic()

        if (
            now - player["lastActionAt"]
            < random.uniform(0.7, 1.5)
        ):
            return

        player["lastActionAt"] = now

        distance_to_goal = self._goal_distance(
            player,
            side,
        )

        pressure = self._pressure(
            player,
            opponent,
        )

        # Shoot close to goal.
        if distance_to_goal < 24:
            if self._should_shoot(
                player,
                pressure,
            ):
                self._attempt_shot(
                    player,
                    team,
                    side,
                )
                return

        # Cross from wings.
        if (
            distance_to_goal < 35
            and player["y"] < 14
            or distance_to_goal < 35
            and player["y"] > 46
        ):
            if random.random() < 0.45:
                self._cross(
                    player,
                    team,
                    opponent,
                    side,
                )
                return

        # Dribble when space exists.
        if (
            pressure < 0.35
            and random.random() < 0.34
        ):
            self._dribble(
                player,
                side,
            )
            return

        # Attackers should progress.
        if (
            player["position"]
            in {
                "ST",
                "LW",
                "RW",
                "AM",
                "LM",
                "RM",
            }
        ):
            if random.random() < 0.62:
                self._advance_player(
                    player,
                    side,
                )
                return

        # Through ball.
        if random.random() < 0.20:
            if self._through_ball(
                player,
                team,
                opponent,
                side,
            ):
                return

        self._pass(
            player,
            team,
            opponent,
            side,
        )

    # ---------------------------------------------------------
    # MOVEMENT
    # ---------------------------------------------------------

    def _move_players(self, dt):
        owner_side = self.ball.get("ownerSide")

        for side, team in [
            ("home", self.home),
            ("away", self.away),
        ]:
            attacking = (
                owner_side == side
            )

            for player in team["players"]:
                if player["red"]:
                    continue

                speed = (
                    0.025
                    * (
                        0.65
                        + player["pace"] / 100
                    )
                )

                if attacking:
                    if player["position"] in {
                        "ST",
                        "LW",
                        "RW",
                        "AM",
                        "LM",
                        "RM",
                    }:
                        direction = (
                            1
                            if side == "home"
                            else -1
                        )

                        player["targetX"] += (
                            direction
                            * speed
                            * 2.0
                        )

                    self._make_attacking_run(
                        player,
                        side,
                    )
                else:
                    self._defensive_position(
                        player,
                        side,
                    )

                player["targetX"] = clamp(
                    player["targetX"],
                    2,
                    98,
                )

                player["targetY"] = clamp(
                    player["targetY"],
                    3,
                    57,
                )

                dx = (
                    player["targetX"]
                    - player["x"]
                )

                dy = (
                    player["targetY"]
                    - player["y"]
                )

                distance = (
                    dx * dx
                    + dy * dy
                ) ** 0.5

                if distance > 0.2:
                    step = min(
                        distance,
                        speed * dt * 8,
                    )

                    player["x"] += (
                        dx / distance
                    ) * step

                    player["y"] += (
                        dy / distance
                    ) * step

                player["staminaNow"] = clamp(
                    player["staminaNow"]
                    - (
                        0.0008
                        if attacking
                        else 0.00035
                    ),
                    20,
                    100,
                )

    def _make_attacking_run(
        self,
        player,
        side,
    ):
        if random.random() > 0.025:
            return

        direction = (
            1
            if side == "home"
            else -1
        )

        if player["position"] in {
            "ST",
            "LW",
            "RW",
            "AM",
        }:
            player["targetX"] += (
                direction
                * random.uniform(2, 7)
            )

            player["targetY"] += random.uniform(
                -5,
                5,
            )

    def _defensive_position(
        self,
        player,
        side,
    ):
        direction = (
            1
            if side == "home"
            else -1
        )

        ball_x = self.ball["x"]

        if player["position"] == "GK":
            player["targetX"] = (
                4 if side == "home"
                else 96
            )

            player["targetY"] = clamp(
                self.ball["y"],
                15,
                45,
            )
            return

        base = (
            player["x"]
            + (
                ball_x - player["x"]
            ) * 0.05
        )

        if player["position"] in {
            "CB",
            "LB",
            "RB",
        }:
            player["targetX"] = (
                base
                - direction * 1.5
            )

        elif player["position"] in {
            "CM",
            "DM",
        }:
            player["targetX"] = (
                base
                + direction * 2
            )

    # ---------------------------------------------------------
    # PASS
    # ---------------------------------------------------------

    def _pass(
        self,
        player,
        team,
        opponent,
        side,
    ):
        teammates = [
            p
            for p in team["players"]
            if p["id"] != player["id"]
            and not p["red"]
        ]

        if not teammates:
            return

        direction = (
            1
            if side == "home"
            else -1
        )

        candidates = []

        for target in teammates:
            dx = target["x"] - player["x"]
            dy = target["y"] - player["y"]

            distance = (
                dx * dx
                + dy * dy
            ) ** 0.5

            if distance > 35:
                continue

            progress = (
                dx * direction
            )

            score = (
                target["vision"] * 0.3
                + target["pace"] * 0.1
                + progress * 1.4
                - distance * 0.4
            )

            candidates.append(
                (score, target)
            )

        if not candidates:
            return

        candidates.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        target = candidates[0][1]

        success = (
            random.random()
            <
            clamp(
                (
                    player["passing"]
                    + player["vision"]
                    - self._pressure(
                        player,
                        opponent,
                    ) * 30
                )
                / 120,
                0.55,
                0.96,
            )
        )

        player["passes"] += 1
        self.stats[side]["passes"] += 1

        if success:
            player["completedPasses"] += 1
            self.stats[side][
                "completedPasses"
            ] += 1

            self.ball.update(
                {
                    "x": target["x"],
                    "y": target["y"],
                    "ownerId": target["id"],
                    "ownerSide": side,
                    "state": "pass",
                    "targetId": target["id"],
                }
            )

            player["hasBall"] = False
            target["hasBall"] = True
            target["lastAction"] = "received pass"

            self._event(
                self.minute,
                "pass",
                f"{player['name']} passed to {target['name']}",
                side,
                player["id"],
                target["id"],
            )

        else:
            self._event(
                self.minute,
                "missed_pass",
                f"{player['name']} misplaced the pass",
                side,
                player["id"],
            )

            self._free_ball(
                player["x"],
                player["y"],
            )

    # ---------------------------------------------------------
    # THROUGH BALL
    # ---------------------------------------------------------

    def _through_ball(
        self,
        player,
        team,
        opponent,
        side,
    ):
        attackers = [
            p
            for p in team["players"]
            if p["position"]
            in {
                "ST",
                "LW",
                "RW",
                "AM",
            }
            and p["id"] != player["id"]
        ]

        if not attackers:
            return False

        direction = (
            1
            if side == "home"
            else -1
        )

        candidates = []

        for target in attackers:
            progress = (
                target["x"] - player["x"]
            ) * direction

            if progress < 2:
                continue

            candidates.append(target)

        if not candidates:
            return False

        target = random.choice(
            candidates
        )

        chance = clamp(
            (
                player["passing"]
                + player["vision"]
            ) / 190,
            0.45,
            0.9,
        )

        if random.random() > chance:
            return False

        target["targetX"] += (
            direction
            * random.uniform(4, 9)
        )

        target["targetX"] = clamp(
            target["targetX"],
            3,
            97,
        )

        self.ball.update(
            {
                "x": target["x"],
                "y": target["y"],
                "ownerId": target["id"],
                "ownerSide": side,
                "state": "through_ball",
                "targetId": target["id"],
            }
        )

        player["hasBall"] = False
        target["hasBall"] = True

        self.stats[side]["passes"] += 1

        self._event(
            self.minute,
            "through_ball",
            f"{player['name']} played a through ball to {target['name']}",
            side,
            player["id"],
            target["id"],
        )

        return True

    # ---------------------------------------------------------
    # DRIBBLE
    # ---------------------------------------------------------

    def _dribble(
        self,
        player,
        side,
    ):
        direction = (
            1
            if side == "home"
            else -1
        )

        player["targetX"] += (
            direction
            * random.uniform(2, 6)
        )

        player["targetY"] += random.uniform(
            -3,
            3,
        )

        player["targetX"] = clamp(
            player["targetX"],
            2,
            98,
        )

        player["targetY"] = clamp(
            player["targetY"],
            3,
            57,
        )

        self.ball["x"] = player["x"]
        self.ball["y"] = player["y"]

        player["lastAction"] = "dribbling"

        self._event(
            self.minute,
            "dribble",
            f"{player['name']} is dribbling forward",
            side,
            player["id"],
        )

    # ---------------------------------------------------------
    # SHOT
    # ---------------------------------------------------------

    def _should_shoot(
        self,
        player,
        pressure,
    ):
        base = (
            player["shooting"]
            / 100
        )

        if pressure > 0.7:
            base -= 0.15

        return random.random() < clamp(
            base,
            0.20,
            0.90,
        )

    def _attempt_shot(
        self,
        player,
        team,
        side,
    ):
        opponent = (
            self.away
            if side == "home"
            else self.home
        )

        player["shots"] += 1
        self.stats[side]["shots"] += 1

        distance = self._goal_distance(
            player,
            side,
        )

        accuracy = clamp(
            (
                player["shooting"]
                * 0.65
                + player["vision"] * 0.15
                + player["dribbling"] * 0.1
            )
            / 100,
            0.35,
            0.94,
        )

        distance_penalty = clamp(
            distance / 100,
            0,
            0.45,
        )

        on_target_chance = clamp(
            accuracy - distance_penalty,
            0.25,
            0.90,
        )

        on_target = (
            random.random()
            < on_target_chance
        )

        player["hasBall"] = False

        if not on_target:
            self._event(
                self.minute,
                "shot",
                f"{player['name']} shot wide",
                side,
                player["id"],
            )

            self._free_ball(
                player["x"],
                player["y"],
            )

            return

        self.stats[side][
            "shotsOnTarget"
        ] += 1

        goalkeeper = self._goalkeeper(
            opponent
        )

        save_power = (
            goalkeeper["goalkeeping"]
            if goalkeeper
            else 65
        )

        goal_chance = clamp(
            (
                player["shooting"]
                - save_power * 0.55
                + random.uniform(-15, 15)
            ) / 100,
            0.08,
            0.72,
        )

        if random.random() < goal_chance:
            self._goal(
                player,
                side,
            )
        else:
            if goalkeeper:
                goalkeeper["saves"] += 1

                self.stats[
                    "away"
                    if side == "home"
                    else "home"
                ]["saves"] += 1

                self._event(
                    self.minute,
                    "save",
                    f"{goalkeeper['name']} saved a shot from {player['name']}",
                    "away"
                    if side == "home"
                    else "home",
                    goalkeeper["id"],
                    player["id"],
                )

            else:
                self._event(
                    self.minute,
                    "shot",
                    f"{player['name']} shot on target",
                    side,
                    player["id"],
                )

            self._free_ball(
                goalkeeper["x"]
                if goalkeeper
                else player["x"],
                goalkeeper["y"]
                if goalkeeper
                else player["y"],
            )

    # ---------------------------------------------------------
    # GOAL
    # ---------------------------------------------------------

    def _goal(
        self,
        player,
        side,
    ):
        self.score[side] += 1

        player["goals"] += 1

        self._event(
            self.minute,
            "goal",
            f"GOAL! {player['name']} scored for {self._team_name(side)}",
            side,
            player["id"],
        )

        self.ball.update(
            {
                "x": 50,
                "y": 30,
                "ownerId": None,
                "ownerSide": None,
                "state": "goal",
                "targetId": None,
            }
        )

        for team_side, team in [
            ("home", self.home),
            ("away", self.away),
        ]:
            for p in team["players"]:
                p["hasBall"] = False

        self._reset_after_goal()

    def _reset_after_goal(self):
        for side, team in [
            ("home", self.home),
            ("away", self.away),
        ]:
            self._apply_formation(
                team["players"],
                team["formation"],
                side == "home",
            )

        if self.score["home"] <= self.score["away"]:
            kickoff_side = "home"
        else:
            kickoff_side = "away"

        team = (
            self.home
            if kickoff_side == "home"
            else self.away
        )

        midfielders = [
            p
            for p in team["players"]
            if p["position"]
            in {
                "CM",
                "AM",
                "ST",
            }
        ]

        player = (
            random.choice(midfielders)
            if midfielders
            else team["players"][0]
        )

        self.ball.update(
            {
                "x": 50,
                "y": 30,
                "ownerId": player["id"],
                "ownerSide": kickoff_side,
                "state": "kickoff",
                "targetId": None,
            }
        )

        player["hasBall"] = True

    # ---------------------------------------------------------
    # CROSS
    # ---------------------------------------------------------

    def _cross(
        self,
        player,
        team,
        opponent,
        side,
    ):
        targets = [
            p
            for p in team["players"]
            if p["position"]
            in {
                "ST",
                "AM",
            }
            and p["id"] != player["id"]
        ]

        if not targets:
            return

        target = min(
            targets,
            key=lambda p: abs(
                p["x"]
                - (
                    82
                    if side == "home"
                    else 18
                )
            ),
        )

        self.stats[side]["passes"] += 1

        success = random.random() < 0.70

        if success:
            self.ball.update(
                {
                    "x": target["x"],
                    "y": target["y"],
                    "ownerId": target["id"],
                    "ownerSide": side,
                    "state": "cross",
                    "targetId": target["id"],
                }
            )

            player["hasBall"] = False
            target["hasBall"] = True

            self._event(
                self.minute,
                "cross",
                f"{player['name']} crossed into the box",
                side,
                player["id"],
                target["id"],
            )

        else:
            self._corner(
                side,
                player,
            )

    # ---------------------------------------------------------
    # CORNER
    # ---------------------------------------------------------

    def _corner(
        self,
        side,
        player=None,
    ):
        self.stats[side]["corners"] += 1

        name = (
            player["name"]
            if player
            else self._team_name(side)
        )

        self._event(
            self.minute,
            "corner",
            f"Corner for {self._team_name(side)}",
            side,
            player["id"]
            if player
            else None,
        )

        attacking = (
            self.home
            if side == "home"
            else self.away
        )

        attackers = [
            p
            for p in attacking["players"]
            if p["position"]
            in {
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

            self.ball.update(
                {
                    "x": (
                        88
                        if side == "home"
                        else 12
                    ),
                    "y": random.choice(
                        [3, 57]
                    ),
                    "ownerId": target["id"],
                    "ownerSide": side,
                    "state": "corner",
                    "targetId": target["id"],
                }
            )

    # ---------------------------------------------------------
    # DEFENDING
    # ---------------------------------------------------------

    def _pressure(
        self,
        player,
        opponent,
    ):
        defenders = [
            p
            for p in opponent["players"]
            if not p["red"]
        ]

        if not defenders:
            return 0

        nearest = min(
            defenders,
            key=lambda p: (
                (
                    p["x"] - player["x"]
                ) ** 2
                + (
                    p["y"] - player["y"]
                ) ** 2
            ),
        )

        distance = (
            (
                nearest["x"]
                - player["x"]
            ) ** 2
            + (
                nearest["y"]
                - player["y"]
            ) ** 2
        ) ** 0.5

        return clamp(
            1 - distance / 15,
            0,
            1,
        )

    def _recover_ball_if_needed(self):
        if self.ball["ownerId"]:
            return

        candidates = []

        for side, team in [
            ("home", self.home),
            ("away", self.away),
        ]:
            for player in team["players"]:
                distance = (
                    (
                        player["x"]
                        - self.ball["x"]
                    ) ** 2
                    + (
                        player["y"]
                        - self.ball["y"]
                    ) ** 2
                ) ** 0.5

                candidates.append(
                    (
                        distance,
                        side,
                        player,
                    )
                )

        if not candidates:
            return

        candidates.sort(
            key=lambda x: x[0]
        )

        distance, side, player = candidates[0]

        if distance < 7:
            self.ball["ownerId"] = player["id"]
            self.ball["ownerSide"] = side
            self.ball["state"] = "controlled"
            player["hasBall"] = True

            self._event(
                self.minute,
                "recovery",
                f"{player['name']} recovered the ball",
                side,
                player["id"],
            )

    def _free_ball(
        self,
        x,
        y,
    ):
        self.ball.update(
            {
                "x": clamp(x, 1, 99),
                "y": clamp(y, 1, 59),
                "ownerId": None,
                "ownerSide": None,
                "state": "free",
                "targetId": None,
            }
        )

    # ---------------------------------------------------------
    # BALL
    # ---------------------------------------------------------

    def _move_ball(self):
        owner = self._get_ball_owner()

        if owner:
            self.ball["x"] = owner["x"]
            self.ball["y"] = owner["y"]

    def _get_ball_owner(self):
        owner_id = self.ball.get(
            "ownerId"
        )

        if not owner_id:
            return None

        for team in [
            self.home,
            self.away,
        ]:
            for player in team["players"]:
                if player["id"] == owner_id:
                    return player

        return None

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------

    def _find_player(
        self,
        team,
        player_id,
    ):
        for player in team["players"]:
            if player["id"] == player_id:
                return player

        return None

    def _goalkeeper(self, team):
        for player in team["players"]:
            if player["position"] == "GK":
                return player

        return team["players"][0] if team["players"] else None

    def _goal_distance(
        self,
        player,
        side,
    ):
        goal_x = (
            100
            if side == "home"
            else 0
        )

        return (
            (
                goal_x
                - player["x"]
            ) ** 2
            + (
                30
                - player["y"]
            ) ** 2
        ) ** 0.5

    def _advance_player(
        self,
        player,
        side,
    ):
        direction = (
            1
            if side == "home"
            else -1
        )

        player["targetX"] += (
            direction
            * random.uniform(3, 8)
        )

        player["targetY"] += random.uniform(
            -4,
            4,
        )

        player["targetX"] = clamp(
            player["targetX"],
            2,
            98,
        )

        player["targetY"] = clamp(
            player["targetY"],
            3,
            57,
        )

        player["lastAction"] = "attacking run"

        self._event(
            self.minute,
            "run",
            f"{player['name']} made an attacking run",
            side,
            player["id"],
        )

    def _assign_initial_ball(self):
        player = self.home["players"][9]

        self.ball.update(
            {
                "x": player["x"],
                "y": player["y"],
                "ownerId": player["id"],
                "ownerSide": "home",
                "state": "kickoff",
                "targetId": None,
            }
        )

        player["hasBall"] = True

    def _team_name(self, side):
        return (
            self.home["name"]
            if side == "home"
            else self.away["name"]
        )

    # ---------------------------------------------------------
    # TACTICS
    # ---------------------------------------------------------

    def set_tactics(
        self,
        side,
        tactics,
    ):
        team = (
            self.home
            if side == "home"
            else self.away
        )

        team["tactics"].update(
            tactics or {}
        )

        return self.snapshot()

    def set_formation(
        self,
        side,
        formation,
    ):
        if formation not in FORMATION_POSITIONS:
            formation = "4-3-3"

        team = (
            self.home
            if side == "home"
            else self.away
        )

        team["formation"] = formation

        self._apply_formation(
            team["players"],
            formation,
            side == "home",
        )

        self._event(
            self.minute,
            "formation",
            f"{team['name']} changed formation to {formation}",
            side,
        )

        return self.snapshot()

    def substitute(
        self,
        side,
        outgoing_id,
        incoming_id,
    ):
        team = (
            self.home
            if side == "home"
            else self.away
        )

        if team["substitutionsUsed"] >= 5:
            return self.snapshot()

        outgoing = self._find_player(
            team,
            outgoing_id,
        )

        incoming = next(
            (
                p
                for p in team["bench"]
                if p["id"] == incoming_id
            ),
            None,
        )

        if not outgoing or not incoming:
            return self.snapshot()

        incoming["x"] = outgoing["x"]
        incoming["y"] = outgoing["y"]
        incoming["targetX"] = outgoing["targetX"]
        incoming["targetY"] = outgoing["targetY"]
        incoming["position"] = outgoing["position"]
        incoming["role"] = outgoing["role"]

        team["players"].remove(
            outgoing
        )

        team["players"].append(
            incoming
        )

        team["bench"].remove(
            incoming
        )

        team["bench"].append(
            outgoing
        )

        team["substitutionsUsed"] += 1

        self._event(
            self.minute,
            "substitution",
            f"{team['name']} made a substitution",
            side,
            outgoing["id"],
            incoming["id"],
        )

        return self.snapshot()

    # ---------------------------------------------------------
    # STATS
    # ---------------------------------------------------------

    def _update_possession_stats(self):
        side = self.ball.get(
            "ownerSide"
        )

        if side == "home":
            self.stats["home"]["possession"] = 51
            self.stats["away"]["possession"] = 49

        elif side == "away":
            self.stats["home"]["possession"] = 49
            self.stats["away"]["possession"] = 51

    # ---------------------------------------------------------
    # EVENTS
    # ---------------------------------------------------------

    def _event(
        self,
        minute,
        event_type,
        text,
        side=None,
        player_id=None,
        target_id=None,
    ):
        event = {
            "id": f"{self.match_id}-{len(self.events) + 1}",
            "minute": int(minute),
            "second": int(self.second),
            "type": event_type,
            "text": text,
            "side": side,
            "playerId": player_id,
            "targetId": target_id,
        }

        self.events.append(event)

        if len(self.events) > 300:
            self.events = self.events[-300:]

    # ---------------------------------------------------------
    # SNAPSHOT
    # ---------------------------------------------------------

    def snapshot(self):
        with self.lock:
            return {
                "matchId": self.match_id,
                "status": self.status,
                "minute": self.minute,
                "second": self.second,
                "score": dict(self.score),
                "home": self._team_snapshot(
                    self.home
                ),
                "away": self._team_snapshot(
                    self.away
                ),
                "ball": dict(self.ball),
                "events": list(self.events),
                "stats": {
                    "home": dict(
                        self.stats["home"]
                    ),
                    "away": dict(
                        self.stats["away"]
                    ),
                },
            }

    def _team_snapshot(self, team):
        return {
            "id": team["id"],
            "name": team["name"],
            "logo": team["logo"],
            "formation": team["formation"],
            "tactics": dict(
                team["tactics"]
            ),
            "substitutionsUsed": team[
                "substitutionsUsed"
            ],
            "stats": dict(
                team["stats"]
            ),
            "players": [
                dict(player)
                for player in team["players"]
            ],
            "bench": [
                dict(player)
                for player in team["bench"]
            ],
        }
