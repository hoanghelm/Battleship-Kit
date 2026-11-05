"""The only file you change.

    def choose(sea) -> order

`sea` is everything you know this turn; orders come from `sea.fire_at(...)`,
`sea.torpedo_toward(...)`, `sea.teleport()` and `sea.fire_somewhere()`.

To add a tactic: write a method that returns a cell or None, and put it in the
list in `decide()` above the default.

Each turn runs down a list of named tactics. Every tactic says whether this
turn is its case; the first one that answers yes picks the target. If none
does, the default -- probability-density search -- takes the turn. Nothing can
ever fail to produce an order.

    1  FINISH_LINE      two or more hits in a row: the axis is known
    2  PROBE_HIT        one lonely hit: which neighbour, by exact counting
    3  FOLLOW_FLARE     a flare revealed enemy cells: shoot what we can see
    4  CLOSE_OUT        few turns left: a wounded ship beats a fresh search
    5  CALIBRATE        early and the wind is still unknown: take a long shot
    6  DENSITY_SEARCH   the default, and the one that runs most of the time

Two kinds of counting hold it up, and both are exact rather than heuristic.

GLOBAL DP -- for every cell, how many ways could any remaining ship still cover
it? A sliding window with a prefix sum finds each run of free cells in constant
time, and a difference array pays the count back across the run, so the whole
40x40 board costs two passes per ship length rather than one pass per window.

SEGMENT DP -- once there are hits on a line, enumerate every placement of every
remaining length that covers all of them and fits the known water. Each
uncovered cell in a surviving placement scores one. That is the exact answer to
"which end of this ship is longer", not a guess.
"""

import math

import numpy as np

FLEET_LENGTHS = (5, 4, 3, 3, 2)
MAX_SHIP = 5

# Measured in lab/evaluate.py: giving up early is the expensive mistake.
ABANDON_AFTER = 12

# A shell under this many seconds in the air drifts less than half a cell, so
# the rounded landing teaches nothing about the wind.
MIN_USEFUL_FLIGHT = 0.8

# Below this many wind samples the aim is still visibly off.
WIND_SETTLED = 12

# Spend early turns on deliberately long shots to pin the wind down sooner?
#
# It sounds right and measured worse. With six seats eating 102 ship cells, the
# turns it costs early are worth more than the accuracy it buys: an ordinary
# density shot is usually far enough to teach the wind anyway, so the dedicated
# phase mostly just delays the search.
CALIBRATE_FIRST = False

# Weight the search by what a ship is worth rather than treating every length
# alike. See `density`.
VALUE_WEIGHTED = True

# How hard to steer away from water another seat has already worked over.
# 0 ignores it; 1 writes those cells off entirely. See `_consumed_penalty`.
CONSUMED_PENALTY = 0.6

# How far the penalty reaches from a wreck, in cells.
CONSUMED_REACH = 3

# A ship taking this many hits inside this many ticks is being hunted, not
# unlucky. Two holes close together is somebody walking down the hull.
UNDER_HUNT_HITS = 2
UNDER_HUNT_WINDOW = 10


def choose(sea):
    if not sea.my_afloat:
        return sea.stand_down()

    board = Board(sea)

    # Defence first. Everything below is about scoring; this is about not being
    # scored off, which for a *placing* is worth the same. A ship about to go
    # down hands its hunter the length as a bonus -- moving it denies that, and
    # keeps our own reach and firepower on the board.
    hunted = board.ship_under_hunt()
    if hunted is not None:
        board.last_tactic = "EVADE"
        return sea.teleport(ship=hunted)

    tactic, target = board.decide()
    board.last_tactic = tactic

    if target is None:
        return sea.fire_somewhere()

    ship = board.best_ship_for(target)
    skill = board.skill_for(target, ship, tactic)

    if skill == "teleport":
        return sea.teleport(ship=ship)
    if skill == "torpedo":
        return sea.torpedo_toward(target, ship=ship)
    return sea.fire_at(target, skill=skill, ship=ship) or sea.fire_somewhere()


class Board:
    """What we know, and the decision table over it."""

    last_tactic = None

    def __init__(self, sea):
        self.sea = sea
        self.rows, self.cols = sea.rows, sea.cols
        self.tried = set(sea.tried)
        self.mine = set(sea.my_cells)

        self.water = set()
        self.ship_cells = set()
        self.sunk_cells = set()
        self.open_hits = []
        self.wrecks = []
        self.wrecks = []

        for row, col, result in sea.shots:
            cell = (row, col)
            if result in ("miss", "off_the_sea"):
                self.water.add(cell)
            elif result in ("hit", "sunk", "wreck", "self_hit"):
                self.ship_cells.add(cell)
                if result == "sunk":
                    self.sunk_cells.add(cell)
                elif result == "hit":
                    self.open_hits.append(cell)
                elif result == "wreck":
                    self.wrecks.append(cell)
                elif result == "wreck":
                    self.wrecks.append(cell)

        self._infer_water()
        self._density = None

    # ------------------------------------------------------- what we deduce

    def _infer_water(self):
        """Water we never had to fire at.

        No ship touches another, diagonals included. So every cell diagonally
        adjacent to a ship cell is water, always. And once a sunk ship's run is
        closed at both ends by water or the edge, we know the whole ship, so its
        entire surrounding ring is water too.
        """
        for row, col in self.ship_cells:
            for dr, dc in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                cell = (row + dr, col + dc)
                if self._on_sea(cell) and cell not in self.ship_cells:
                    self.water.add(cell)

        for run, axis in self._closed_sunk_runs():
            for row, col in run:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        cell = (row + dr, col + dc)
                        if self._on_sea(cell) and cell not in self.ship_cells:
                            self.water.add(cell)

    def _closed_sunk_runs(self):
        """Runs of sunk cells whose both ends are water or the sea's edge."""
        runs = []
        seen = set()

        for cell in self.sunk_cells:
            for axis, (dr, dc) in enumerate(((0, 1), (1, 0))):
                if (cell, axis) in seen:
                    continue

                run = [cell]
                forward = cell
                while (forward[0] + dr, forward[1] + dc) in self.sunk_cells:
                    forward = (forward[0] + dr, forward[1] + dc)
                    run.append(forward)
                backward = cell
                while (backward[0] - dr, backward[1] - dc) in self.sunk_cells:
                    backward = (backward[0] - dr, backward[1] - dc)
                    run.append(backward)

                for c in run:
                    seen.add((c, axis))

                beyond_a = (forward[0] + dr, forward[1] + dc)
                beyond_b = (backward[0] - dr, backward[1] - dc)
                closed_a = not self._on_sea(beyond_a) or beyond_a in self.water
                closed_b = not self._on_sea(beyond_b) or beyond_b in self.water
                if len(run) >= 2 and closed_a and closed_b:
                    runs.append((run, axis))

        return runs

    def _on_sea(self, cell):
        return 0 <= cell[0] < self.rows and 0 <= cell[1] < self.cols

    def _possible(self, cell):
        return (self._on_sea(cell)
                and cell not in self.water
                and cell not in self.mine
                and cell not in self.sunk_cells)

    def _is_candidate(self, cell):
        return (self._possible(cell)
                and cell not in self.tried
                and cell not in self.ship_cells
                and self._reachable(cell))

    def _reachable(self, cell):
        return any(self.sea.can_reach(cell, ship) for ship in self.sea.my_afloat)

    # ------------------------------------------------------------- defence

    def ship_under_hunt(self):
        """One of ours that somebody is actively working down, if we can move it.

        `incoming` lists the shells that holed our cells, with the tick. We are
        never told who fired, and do not need to be: two holes in one hull
        within a few ticks is not bad luck, it is a hunt, and the next shell
        finishes it.

        Moving the ship denies that seat the sinking bonus -- the ship's whole
        length -- and keeps our own gun and its reach on the board. For a
        *placing*, points we deny count the same as points we score.
        """
        sea = self.sea
        if not sea.has_skill("teleport"):
            return None

        recent = [c for c in sea.incoming
                  if len(c) > 3 and sea.tick - c[3] <= UNDER_HUNT_WINDOW]
        if not recent:
            return None

        for ship in sea.my_afloat:
            cells = {tuple(c) for c in ship["cells"]}
            hits = sum(1 for c in recent if (c[0], c[1]) in cells)
            unhit = sum(1 for h in ship.get("holed", []) if not h)
            if hits >= UNDER_HUNT_HITS and unhit >= 1:
                return ship

        return None


    # --------------------------------------------------- the decision table

    def decide(self):
        for name, tactic in (
            ("FINISH_LINE", self._finish_line),
            # A lit cell is a *known* enemy cell. A probe beside a single hit is
            # a guess at better-than-even odds. Certainty goes first.
            ("FOLLOW_FLARE", self._follow_flare),
            ("PROBE_HIT", self._probe_hit),
            ("FLARE_SCOUT", self._flare_scout),
            ("CLOSE_OUT", self._close_out),
            ("CALIBRATE", self._calibrate),
        ):
            target = tactic()
            if target is not None:
                return name, target

        return "DENSITY_SEARCH", self._density_search()

    # 1 --------------------------------------------------------------------
    def _finish_line(self):
        """Two or more hits in a row fix the axis. Shoot the likelier end."""
        for hit in reversed(self.open_hits):
            if self._follow_ups(hit) >= ABANDON_AFTER:
                continue

            for axis, (dr, dc) in enumerate(((0, 1), (1, 0))):
                run = self._run_through(hit, dr, dc)
                if len(run) < 2:
                    continue

                scores = self._segment_scores(run, dr, dc)
                best = self._best_scored(scores)
                if best is not None:
                    return best
        return None

    # 2 --------------------------------------------------------------------
    def _probe_hit(self):
        """A single hit. Exact counting says which neighbour is likeliest."""
        for hit in reversed(self.open_hits):
            if self._follow_ups(hit) >= ABANDON_AFTER:
                continue

            scores = {}
            for dr, dc in ((0, 1), (1, 0)):
                for cell, score in self._segment_scores([hit], dr, dc).items():
                    scores[cell] = scores.get(cell, 0) + score

            best = self._best_scored(scores)
            if best is not None:
                return best
        return None

    # 3 --------------------------------------------------------------------
    def _follow_flare(self):
        """A lit cell is a known enemy cell. Nothing beats being told."""
        for cell in self.sea.lit_cells:
            if self._is_candidate(cell):
                return cell
        return None

    # 5 --------------------------------------------------------------------
    def _close_out(self):
        """Near the end, a wounded ship is worth more than a fresh search.

        Finishing a hit ship pays its length as a bonus and needs one or two
        shells. Starting a new search this late will not reach a sinking.
        """
        remaining = self.sea.tick_cap - self.sea.tick
        if remaining > 12 or not self.open_hits:
            return None

        for hit in reversed(self.open_hits):
            for cell in self._orthogonal(hit):
                if self._is_candidate(cell):
                    return cell
        return None

    def _flare_scout(self):
        """Fire a flare at the richest 7x7 block, not at the richest cell.

        One shell tells you about one cell. A flare lights forty-nine and costs
        the same turn, which makes it far the most informative thing on the
        board -- but only if it is aimed at a *square* worth lighting. Aiming it
        where a single cell happens to peak wastes most of the square, since the
        cells next to a peak are usually ruled out by the same evidence that
        made it peak.

        So score every 7x7 window by the density inside it and light the best.
        """
        if not self.sea.has_skill("flare") or self.open_hits:
            return None

        grid = self._scored_grid().astype(np.int64)
        grid[grid < 0] = 0

        side = 7
        reach = side // 2
        if self.rows < side or self.cols < side:
            return None

        # Summed-area table: every window total in constant time.
        area = np.zeros((self.rows + 1, self.cols + 1), dtype=np.int64)
        area[1:, 1:] = grid.cumsum(axis=0).cumsum(axis=1)
        totals = (area[side:, side:] - area[:-side, side:]
                  - area[side:, :-side] + area[:-side, :-side])

        if totals.size == 0 or totals.max() <= 0:
            return None

        top, left = np.unravel_index(int(totals.argmax()), totals.shape)
        centre = (int(top) + reach, int(left) + reach)
        return centre if self._reachable(centre) else None

    # 6 --------------------------------------------------------------------
    def _calibrate(self):
        """Early on, buy wind knowledge with a shot that is long enough to show it.

        A short lob drifts under half a cell and the rounding erases it, so it
        teaches nothing. Aim far and in the middle, where ships are anyway.
        """
        if not CALIBRATE_FIRST:
            return None
        if self.sea.wind_confidence >= WIND_SETTLED or self.sea.tick > 25:
            return None

        grid = self._scored_grid()
        far = self._far_mask()
        grid = np.where(far, grid, -1)
        return self._peak(grid)

    # 7 --------------------------------------------------------------------
    def _density_search(self):
        return self._peak(self._scored_grid())

    # ----------------------------------------------------------- the counting

    @property
    def density(self):
        """Global DP: ways a remaining ship could cover each cell."""
        if self._density is not None:
            return self._density

        possible = np.ones((self.rows, self.cols), dtype=bool)
        for row, col in self.water | self.mine | self.sunk_cells:
            if self._on_sea((row, col)):
                possible[row, col] = False

        # Weighted by what the ship is worth, not just by whether one fits.
        # Holing a cell pays 1; sinking the ship pays its length on top. A cell
        # where a carrier could lie is worth more than one only a destroyer
        # fits, so the search should prefer it when the odds are otherwise
        # equal -- we are maximising expected points, not probability of a hit.
        total = np.zeros((self.rows, self.cols), dtype=np.int32)
        for length in FLEET_LENGTHS:
            weight = (1 + length) if VALUE_WEIGHTED else 1
            total += weight * _runs_covering(possible, length)
            total += weight * _runs_covering(possible.T, length).T

        total = self._discount_consumed(total)
        self._density = total
        return total

    def _discount_consumed(self, grid):
        """Steer away from sea another seat has already eaten.

        A wreck is a cell that was holed before we got there, so some other seat
        is working that ship and has probably holed its neighbours too. Our
        density model cannot see their shots, so it keeps rating that patch as
        though it held an untouched ship.

        This is the mirror of a tactic that did *not* work: hunting around
        wrecks to join somebody else's kill scored worse, because by the time
        the shell lands those cells are already holed. If hunting there is bad,
        avoiding there should be good -- so the same evidence is used the other
        way round.
        """
        if CONSUMED_PENALTY <= 0 or not self.wrecks:
            return grid

        scale = np.ones((self.rows, self.cols), dtype=np.float32)
        for row, col in self.wrecks:
            r0, r1 = max(0, row - CONSUMED_REACH), min(self.rows, row + CONSUMED_REACH + 1)
            c0, c1 = max(0, col - CONSUMED_REACH), min(self.cols, col + CONSUMED_REACH + 1)
            scale[r0:r1, c0:c1] *= (1.0 - CONSUMED_PENALTY)

        return (grid * scale).astype(np.int32)

    def _segment_scores(self, known, dr, dc):
        """Segment DP: every placement covering `known`, scored per free cell.

        Enumerates each remaining ship length and each offset that covers all
        the known hits, discards any that crosses water or our own hull, and
        gives one point to each of its cells we have not already struck. The
        result is the exact count of surviving ways the ship could extend.
        """
        known = sorted(known)
        head, tail = known[0], known[-1]
        scores = {}

        for length in FLEET_LENGTHS:
            span = len(known)
            if length < span:
                continue

            for back in range(length - span + 1):
                start = (head[0] - dr * back, head[1] - dc * back)
                cells = [(start[0] + dr * i, start[1] + dc * i) for i in range(length)]

                if not all(self._possible(c) or c in self.ship_cells for c in cells):
                    continue
                if not all(k in cells for k in known):
                    continue
                # The cell just past each end must not be another hit, or this
                # placement is too short for the run it sits in.
                before = (cells[0][0] - dr, cells[0][1] - dc)
                after = (cells[-1][0] + dr, cells[-1][1] + dc)
                if before in self.ship_cells or after in self.ship_cells:
                    continue

                for cell in cells:
                    if self._is_candidate(cell):
                        scores[cell] = scores.get(cell, 0) + 1

        return scores

    def _best_scored(self, scores):
        usable = {c: s for c, s in scores.items() if self._is_candidate(c)}
        if not usable:
            return None
        best = max(usable.values())
        # Break ties by global density: the cell that is likelier in general.
        return max((c for c, s in usable.items() if s == best),
                   key=lambda c: int(self.density[c[0], c[1]]))

    def _scored_grid(self):
        grid = self.density.astype(np.int32).copy()
        for row, col in self.tried | self.water | self.mine | self.ship_cells:
            if self._on_sea((row, col)):
                grid[row, col] = -1
        return np.where(self._reach_mask(), grid, -1)

    def _peak(self, grid):
        best = int(grid.max())
        if best <= 0:
            return None
        spots = np.argwhere(grid == best)
        centre = np.array([(self.rows - 1) / 2, (self.cols - 1) / 2])
        pick = min(spots, key=lambda s: float(np.hypot(*(s - centre))))
        return (int(pick[0]), int(pick[1]))

    def _reach_mask(self):
        mask = np.zeros((self.rows, self.cols), dtype=bool)
        rr, cc = np.indices((self.rows, self.cols))
        for ship in self.sea.my_afloat:
            origin = ship["cells"][0]
            mask |= np.hypot(rr - origin[0], cc - origin[1]) <= self.sea.max_reach
        return mask

    def _far_mask(self):
        """Cells far enough away that the shell is airborne long enough to measure."""
        mask = np.zeros((self.rows, self.cols), dtype=bool)
        rr, cc = np.indices((self.rows, self.cols))
        # Flight time rises with range; a third of maximum reach is comfortably
        # past the point where the drift survives rounding.
        floor = self.sea.max_reach * 0.33
        for ship in self.sea.my_afloat:
            origin = ship["cells"][0]
            distance = np.hypot(rr - origin[0], cc - origin[1])
            mask |= (distance >= floor) & (distance <= self.sea.max_reach)
        return mask

    # ------------------------------------------------------------- plumbing

    def _run_through(self, cell, dr, dc):
        run = [cell]
        forward = cell
        while (forward[0] + dr, forward[1] + dc) in self.ship_cells:
            forward = (forward[0] + dr, forward[1] + dc)
            run.append(forward)
        backward = cell
        while (backward[0] - dr, backward[1] - dc) in self.ship_cells:
            backward = (backward[0] - dr, backward[1] - dc)
            run.append(backward)
        return sorted(run)

    def _orthogonal(self, cell):
        return [(cell[0] - 1, cell[1]), (cell[0], cell[1] + 1),
                (cell[0] + 1, cell[1]), (cell[0], cell[1] - 1)]

    def _follow_ups(self, hit):
        """Only genuine follow-ups: the eight neighbours and the two axes."""
        count = 0
        for cell in self.tried:
            dr, dc = cell[0] - hit[0], cell[1] - hit[1]
            if abs(dr) <= 1 and abs(dc) <= 1:
                count += 1
            elif dr == 0 and abs(dc) <= MAX_SHIP - 1:
                count += 1
            elif dc == 0 and abs(dr) <= MAX_SHIP - 1:
                count += 1
        return count

    def best_ship_for(self, target):
        best, closest = None, None
        for ship in self.sea.my_afloat:
            origin = ship["cells"][0]
            distance = math.hypot(target[0] - origin[0], target[1] - origin[1])
            if distance > self.sea.max_reach:
                continue
            if closest is None or distance < closest:
                best, closest = ship, distance
        return best or self.sea.my_afloat[0]

    def skill_for(self, target, ship, tactic):
        """Skills follow the tactic rather than the other way round."""
        sea = self.sea
        if tactic == "FLARE_SCOUT":
            return "flare"

        hunting = tactic in ("FINISH_LINE", "PROBE_HIT", "FOLLOW_FLARE", "CLOSE_OUT")

        # A torpedo sinks the first ship in line whole. Only worth its 7 points
        # on a ship we have already found.
        if hunting and sea.has_skill("torpedo"):
            return "torpedo"

        # A cluster's three extra cells are near-worthless on open sea and very
        # good beside a known hit.
        if hunting and sea.has_skill("cluster"):
            return "cluster"

        # No teleport here any more: `ship_under_hunt` moves a ship while it
        # still has hull left, which is strictly better than waiting until half
        # of it is gone.

        return None


def _runs_covering(possible, length):
    """For each cell, how many horizontal runs of `length` free cells cover it."""
    rows, cols = possible.shape
    if length > cols:
        return np.zeros((rows, cols), dtype=np.int32)

    blocked = (~possible).astype(np.int32)
    prefix = np.zeros((rows, cols + 1), dtype=np.int32)
    prefix[:, 1:] = np.cumsum(blocked, axis=1)

    usable = (prefix[:, length:] - prefix[:, :cols - length + 1]) == 0

    diff = np.zeros((rows, cols + 1), dtype=np.int32)
    starts = np.arange(cols - length + 1)
    diff[:, starts] += usable
    diff[:, starts + length] -= usable
    return np.cumsum(diff[:, :cols], axis=1).astype(np.int32)
