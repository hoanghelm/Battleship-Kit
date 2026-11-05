"""The part you do not edit.

This turns the referee's raw state into something you can give orders to in
plain terms. You say *where* to fire and *which skill* to spend; this works out
the bearing, the elevation, the power and the wind correction, and tells you
afterwards whether the shell went where you sent it.

Everything a strategy needs is on `Sea`. Everything a strategy returns is built
by `sea.fire_at(...)`, `sea.torpedo_toward(...)` or `sea.teleport(...)`.

Edit `strategy.py`, not this file.
"""

import math

NEIGHBOURS = ((-1, 0), (0, 1), (1, 0), (0, -1))

# A shell this slow tells you nothing about the wind: it is airborne under a
# second, the wind moves it less than half a cell, and the rounded landing
# throws that away.
MIN_USEFUL_FLIGHT = 0.8

# Boosters whose reported landing is not a ballistic one. A torpedo runs along
# the surface and reports where it stopped; a teleport fires nothing at all.
NOT_A_FLIGHT = ("torpedo", "teleport")


class ShotReport:
    """What happened to the shell you fired last turn.

    `on_target` is the question worth asking: did the shell land on the cell you
    aimed at? Early on it usually did not, because the wind is still unknown.
    `drift` is how far off it was, in cells.
    """

    def __init__(self, aimed_at=None, landed_at=None, results=None,
                 skill_requested=None, skill_fired=None, teleported=False):
        self.aimed_at = aimed_at
        self.landed_at = landed_at
        self.results = results or []          # e.g. ["hit"] or ["miss", "hit"]
        self.skill_requested = skill_requested
        self.skill_fired = skill_fired
        self.teleported = teleported

    @property
    def fired(self):
        return self.landed_at is not None

    @property
    def on_target(self):
        return self.aimed_at is not None and tuple(self.aimed_at) == tuple(self.landed_at or ())

    @property
    def drift(self):
        """How many cells off the aim point the shell landed, as (row, col)."""
        if self.aimed_at is None or self.landed_at is None:
            return None
        return (self.landed_at[0] - self.aimed_at[0], self.landed_at[1] - self.aimed_at[1])

    @property
    def hit(self):
        return any(r in ("hit", "sunk") for r in self.results)

    @property
    def sank(self):
        return "sunk" in self.results

    @property
    def wasted(self):
        return bool(self.results) and all(
            r in ("miss", "wreck", "off_the_sea", "self_hit") for r in self.results)

    @property
    def skill_was_spent(self):
        """False when you asked for a skill you did not hold -- it fired as a plain shell."""
        return self.skill_fired is not None

    def __repr__(self):
        if not self.fired:
            return "ShotReport(nothing fired)"
        return (f"ShotReport(aimed={self.aimed_at} landed={self.landed_at} "
                f"{'ON TARGET' if self.on_target else f'drift={self.drift}'} "
                f"results={self.results} skill={self.skill_fired})")


class Order:
    """One turn's action. Build these with the `sea.*` helpers."""

    def __init__(self, ship, direction, elevation, power, skill=None, aimed_at=None):
        self.ship = ship
        self.direction = direction
        self.elevation = elevation
        self.power = power
        self.skill = skill
        self.aimed_at = aimed_at

    def to_wire(self):
        action = {
            "ship": self.ship,
            "dir": float(self.direction),
            "elev": float(self.elevation),
            "power": int(self.power),
        }
        if self.skill:
            action["booster"] = self.skill
        return action


class _WindEstimate:
    """The wind, worked out from where our own shells actually landed."""

    def __init__(self):
        self.row = 0.0
        self.col = 0.0
        self.samples = 0
        self._pending = None

    @property
    def value(self):
        if self.samples == 0:
            return (0.0, 0.0)
        return (self.row / self.samples, self.col / self.samples)

    def predict(self, origin, bearing, elevation, power, physics):
        self._pending = (origin, bearing, elevation, power, physics)

    def forget(self):
        self._pending = None

    def observe(self, landed):
        if self._pending is None or landed is None:
            return
        origin, bearing, elevation, power, physics = self._pending
        self._pending = None

        v0 = power * physics["speed_per_power"]
        t = 2.0 * v0 * math.sin(math.radians(elevation)) / physics["gravity"]
        if t < MIN_USEFUL_FLIGHT:
            return

        h = v0 * math.cos(math.radians(elevation))
        want_row = origin[0] + (-h * math.cos(math.radians(bearing))) * t
        want_col = origin[1] + (h * math.sin(math.radians(bearing))) * t

        self.row += (landed[0] - want_row) / t
        self.col += (landed[1] - want_col) / t
        self.samples += 1


class Sea:
    """Everything you know, and every order you can give.

    A fresh one is built each turn, except for what has to be remembered between
    turns (the wind estimate and the cells we have aimed at), which the runner
    carries over.
    """

    def __init__(self, state, memory):
        self._state = state
        self._memory = memory
        self.last_shot = memory.last_shot

    # ------------------------------------------------------------ what we know

    @property
    def tick(self):
        return self._state["tick"]

    @property
    def score(self):
        return self._state.get("score", 0)

    @property
    def tick_cap(self):
        """How many ticks the battle lasts at most."""
        return self._state["config"].get("tick_cap", 120)

    @property
    def rows(self):
        return self._state["config"]["map"]["rows"]

    @property
    def cols(self):
        return self._state["config"]["map"]["cols"]

    @property
    def my_ships(self):
        """Each as {"ship", "cells", "holed", "sunk"}. cells[0] is its firing origin."""
        return self._state["you"]["ships"]

    @property
    def my_afloat(self):
        return [s for s in self.my_ships if not s["sunk"]]

    @property
    def skills(self):
        """How many of each skill are left: {"flare": 1, "cluster": 6, ...}."""
        return self._state.get("boosters") or {}

    def has_skill(self, name):
        return self.skills.get(name, 0) > 0

    @property
    def shots(self):
        """Every shot we have fired: [(row, col, result), ...]."""
        return [tuple(s) for s in self._state["your_shots"]]

    @property
    def hits(self):
        """Cells we have hit that have not been reported sunk yet."""
        return [(r, c) for r, c, result in self.shots if result == "hit"]

    @property
    def incoming(self):
        """Shells that holed our own cells: [(row, col, result, tick), ...].

        The only sense we have of another seat. We are never told who fired, but
        two holes in one of our ships within a few ticks means somebody has found
        it and is working down it.
        """
        return [tuple(s) for s in (self._state.get("incoming") or [])]

    @property
    def lit_cells(self):
        """Enemy cells our flares revealed and that are still unhit."""
        return [tuple(c) for c in (self._state.get("lit_cells") or [])]

    @property
    def tried(self):
        """Cells already shot at or aimed at -- do not waste another shell here.

        Aim points count as well as landings: the wind pushes a shell off its
        target, so a cell we aimed at and missed never appears in `shots`, and a
        bot that only remembers landings fires at the same square forever.
        """
        return {(r, c) for r, c, _ in self.shots} | self._memory.aimed

    @property
    def my_cells(self):
        return {tuple(c) for s in self.my_ships for c in s["cells"]}

    @property
    def wind(self):
        """Our current estimate, as (row, col). Zero until we have fired a few."""
        return self._memory.wind.value

    @property
    def wind_confidence(self):
        """How many usable samples the estimate rests on."""
        return self._memory.wind.samples

    @property
    def max_reach(self):
        physics = self._state["config"]["physics"]
        v0 = physics["power_max"] * physics["speed_per_power"]
        return v0 * v0 / physics["gravity"]

    def in_bounds(self, cell):
        return 0 <= cell[0] < self.rows and 0 <= cell[1] < self.cols

    def can_reach(self, cell, ship=None):
        origin = (ship or self.my_afloat[0])["cells"][0]
        return math.hypot(cell[0] - origin[0], cell[1] - origin[1]) <= self.max_reach

    def cells_in_reach(self, ship=None):
        """Every cell we could land a shell on, nearest first."""
        origin = (ship or self.my_afloat[0])["cells"][0]
        cells = [
            (row, col)
            for row in range(self.rows)
            for col in range(self.cols)
            if math.hypot(row - origin[0], col - origin[1]) <= self.max_reach
        ]
        cells.sort(key=lambda c: math.hypot(c[0] - origin[0], c[1] - origin[1]))
        return cells

    def neighbours(self, cell):
        return [(cell[0] + dr, cell[1] + dc) for dr, dc in NEIGHBOURS
                if self.in_bounds((cell[0] + dr, cell[1] + dc))]

    # -------------------------------------------------------------- the orders

    def fire_at(self, cell, skill=None, ship=None):
        """Put a shell on `cell`, allowing for the wind. Optionally spend a skill.

        `skill` may be "flare" or "cluster", both of which fly like a shell. For
        a torpedo use `torpedo_toward`; a teleport fires nothing, so use
        `teleport`.

        Returns None when the cell is out of range from that ship -- check for
        it, or use `fire_somewhere()` as a fallback.
        """
        ship = ship or (self.my_afloat[0] if self.my_afloat else None)
        if ship is None:
            return self.stand_down()

        origin = ship["cells"][0]
        physics = self._state["config"]["physics"]
        aim = _solve(origin, cell, physics, self.wind)
        if aim is None:
            return None

        self._memory.aimed.add(tuple(cell))
        self._memory.wind.predict(origin, aim[0], aim[1], aim[2], physics)
        return Order(ship["ship"], aim[0], aim[1], aim[2], skill, aimed_at=tuple(cell))

    def torpedo_toward(self, cell, ship=None):
        """Run a torpedo along the surface toward `cell`.

        It does not fly, so there is no wind to allow for: it takes the true
        bearing and stops at the first ship in line, whoever owns it.
        """
        ship = ship or (self.my_afloat[0] if self.my_afloat else None)
        if ship is None:
            return self.stand_down()

        origin = ship["cells"][0]
        bearing = math.degrees(math.atan2(cell[1] - origin[1], -(cell[0] - origin[0]))) % 360.0
        self._memory.wind.forget()
        return Order(ship["ship"], bearing, 45.0, 1, "torpedo", aimed_at=None)

    def teleport(self, ship=None):
        """Move one of our ships somewhere random and legal. Fires nothing."""
        ship = ship or (self.my_afloat[0] if self.my_afloat else None)
        if ship is None:
            return self.stand_down()

        self._memory.wind.forget()
        return Order(ship["ship"], 0.0, 45.0, 1, "teleport", aimed_at=None)

    def fire_somewhere(self, ship=None):
        """A short shot when nothing useful is in range. A turn has to do something."""
        ship = ship or (self.my_afloat[0] if self.my_afloat else None)
        if ship is None:
            return self.stand_down()
        self._memory.wind.forget()
        return Order(ship["ship"], 45.0, 20.0, 1, None, aimed_at=None)

    def stand_down(self):
        """Our whole fleet is sunk. Nothing useful is left to do."""
        return Order("", 0.0, 0.0, 1, None, aimed_at=None)


def _solve(origin, target, physics, wind):
    """Bearing, elevation and power that land on `target` with `wind` allowed for.

    The flight, from the rules:

        v0  = power * speed_per_power
        t   = 2 * v0 * sin(elev) / gravity
        row = origin_row + (-v0 * cos(elev) * cos(dir) + wind_row) * t
        col = origin_col + ( v0 * cos(elev) * sin(dir) + wind_col) * t

    The wind displaces the shell by wind * t, but t depends on the elevation,
    which depends on the distance we are solving for -- so solve, correct the aim
    point, solve again. Three passes is past the point where it stops moving.
    """
    aim_row, aim_col = target[0], target[1]
    solved = None

    for _ in range(3):
        want_row = aim_row - origin[0]
        want_col = aim_col - origin[1]
        distance = math.hypot(want_row, want_col)

        solved = None
        for power in range(1, int(physics["power_max"]) + 1):
            v0 = power * physics["speed_per_power"]
            ratio = distance * physics["gravity"] / (v0 * v0)
            if ratio <= 1.0:
                elevation = math.degrees(math.asin(ratio)) / 2
                bearing = math.degrees(math.atan2(want_col, -want_row)) % 360.0
                solved = (bearing, elevation, power)
                break

        if solved is None:
            return None

        t = 2.0 * solved[2] * physics["speed_per_power"] \
            * math.sin(math.radians(solved[1])) / physics["gravity"]
        aim_row = target[0] - wind[0] * t
        aim_col = target[1] - wind[1] * t

    return solved


class Memory:
    """What carries over between turns. The runner owns one of these."""

    def __init__(self):
        self.wind = _WindEstimate()
        self.aimed = set()
        self.last_shot = ShotReport()
        self._shots_seen = 0
        self._last_order = None
        self.had_a_turn = False

    def before_turn(self, state):
        """Read the referee's report on our previous order into `last_shot`."""
        previous = state.get("last_action") or {}
        landed = previous.get("landed")
        skill_fired = previous.get("booster_fired")

        if skill_fired not in NOT_A_FLIGHT:
            self.wind.observe(landed)
        else:
            self.wind.forget()

        shots = state.get("your_shots") or []
        fresh = shots[self._shots_seen:]
        self._shots_seen = len(shots)

        self.last_shot = ShotReport(
            aimed_at=self._last_order.aimed_at if self._last_order else None,
            landed_at=tuple(landed) if landed else None,
            results=[s[2] for s in fresh],
            skill_requested=previous.get("booster_requested"),
            skill_fired=skill_fired,
            teleported=bool(previous.get("teleported")),
        )

    def after_turn(self, order):
        self._last_order = order
        self.had_a_turn = True
