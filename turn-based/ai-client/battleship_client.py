"""
Battleship (turn-based) - external control client and a sample bot.

Framing: send one JSON object, read back an 8-byte big-endian length followed by
that many bytes of UTF-8 JSON.

    python battleship_client.py                 # play one game and report
    python battleship_client.py --games 5       # play five
    python battleship_client.py --level 1       # against the hard computer
    python battleship_client.py --speed 10      # run the clock fast while testing
    python battleship_client.py --port 11001
"""

import argparse
import json
import socket
import struct
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

STATE = 185
FIRE = 190
NEW_GAME = 191
SPEED = 192

Cell = Tuple[int, int]  # (row, column), row 0 is A and column 0 is column 1


def cell_name(cell: Cell) -> str:
    """(2, 6) -> 'C7'. Rows are letters from the top, columns are numbers from the left."""
    row, column = cell
    return chr(ord("A") + row) + str(column + 1)


def parse_cell(text: str) -> Cell:
    text = text.strip().upper()
    return ord(text[0]) - ord("A"), int(text[1:]) - 1


class BattleshipClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 11000, timeout: float = 5.0):
        self.host, self.port, self.timeout = host, port, timeout
        self.socket: Optional[socket.socket] = None

    # ---------------------------------------------------------------- connection

    def connect(self) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        self.socket.connect((self.host, self.port))

    def close(self) -> None:
        if self.socket:
            try:
                self.socket.close()
            finally:
                self.socket = None

    def __enter__(self) -> "BattleshipClient":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ---------------------------------------------------------------- transport

    def _read_exactly(self, count: int) -> bytes:
        chunks, remaining = [], count
        while remaining > 0:
            chunk = self.socket.recv(min(remaining, 65536))
            if not chunk:
                raise ConnectionError("Server closed the connection")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.socket:
            raise ConnectionError("Not connected")
        self.socket.sendall(json.dumps(payload).encode("utf-8"))
        (length,) = struct.unpack(">Q", self._read_exactly(8))
        return json.loads(self._read_exactly(length).decode("utf-8")) if length else {}

    # ---------------------------------------------------------------- commands

    def get_state(self) -> Dict[str, Any]:
        return self._request({"Cmd": STATE})

    def fire(self, cells: Sequence[Cell]) -> Dict[str, Any]:
        """Fire one turn's worth of shots. Returns the state once they have landed."""
        return self._request({"Cmd": FIRE, "Cells": [cell_name(c) for c in cells]})

    def new_game(self, level: int = -1) -> Dict[str, Any]:
        """Start a fresh game. level: 0 easy, 1 hard, -1 keep the current setting."""
        return self._request({"Cmd": NEW_GAME, "Level": level})

    def set_speed(self, rate: float) -> Dict[str, Any]:
        """Run the game clock faster while testing. 1 is normal, 20 the most it allows."""
        return self._request({"Cmd": SPEED, "Rate": rate})

    def wait_until_ready(self, timeout: float = 30.0) -> Dict[str, Any]:
        """Block until we may fire, or the game is over."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.get_state()
            if state.get("canFire") or state.get("gameOver"):
                return state
            time.sleep(0.05)
        raise TimeoutError("Timed out waiting for our turn")


# ------------------------------------------------------------------ sample bot


class DeductionBot:
    """Works out where each ship can still be, then shoots the likeliest cells.

    The one thing this feed gives you that ordinary Battleship does not is *which kind*
    of ship lost a part on which turn. For a ship there is only one of, that is an exact
    statement rather than a hint: the number of its cells among a turn's three shots
    equals the number of parts it lost that turn. Every position that disagrees with that
    is impossible, and what survives is usually a short list - often a single square.
    """

    def __init__(self, passes: int = 3):
        # How many times to fold newly pinned ships back into the deduction: pinning one
        # ship hands over its moat as water, which can pin the next.
        self.passes = passes

    def choose(self, state: Dict[str, Any]) -> List[Cell]:
        size = state["size"]
        want = state["shotsPerTurn"]
        turns = self._turns_we_fired(state)
        losses = self._losses_by_turn(state)
        singles, scouts_alive = self._fleet(state)

        water: Set[Cell] = set()
        viable: Dict[str, List[List[Cell]]] = {}

        for _ in range(self.passes):
            for name, shape, _alive in singles:
                viable[name] = [
                    cells for cells in self._positions(size, shape)
                    if not any(cell in water for cell in cells)
                    and all(len(set(cells) & group) == losses.get(turn, {}).get(name, 0)
                            for turn, group in turns.items())
                ]

            grew = False
            for name, _shape, _alive in singles:
                if len(viable.get(name, [])) == 1:
                    ring = self._moat(viable[name][0], size)
                    if not ring <= water:
                        water |= ring
                        grew = True
            if not grew:
                break

        score = {cell: 0.0 for cell in self._unshot(state)}

        # Each surviving ship spreads one ship's worth of probability over its own
        # candidates, so a ship cornered into two places outvotes one that could still
        # be anywhere.
        for name, _shape, alive in singles:
            places = viable.get(name) or []
            if not alive or not places:
                continue
            share = 1.0 / len(places)
            for cells in places:
                for cell in cells:
                    if cell in score:
                        score[cell] += share

        # The scouts are single cells with no shape to give them away, so they are flat
        # probability over whatever is left: enough to break ties, never enough to
        # outvote a cornered hull.
        candidates = [cell for cell in score if cell not in water]
        if scouts_alive and candidates:
            flat = scouts_alive / len(candidates)
            for cell in candidates:
                score[cell] += flat

        ranked = sorted(score, key=lambda cell: -score[cell])
        if not ranked:
            return []

        average = sum(score.values()) / len(score)
        if score[ranked[0]] > average * 1.25:
            return ranked[:want]

        # Nothing to chase yet. Keep the three shots apart: three misses in one corner
        # rule out far less of the board than three spread across it.
        return self._spread(ranked, want)

    # ---------------------------------------------------------------- reading the feed

    @staticmethod
    def _unshot(state: Dict[str, Any]) -> List[Cell]:
        size = state["size"]
        return [(r, c) for r in range(size) for c in range(size)
                if state["yourShots"][r][c] == -1]

    @staticmethod
    def _turns_we_fired(state: Dict[str, Any]) -> Dict[int, Set[Cell]]:
        """Turn number -> the three cells we fired on it."""
        size = state["size"]
        turns: Dict[int, Set[Cell]] = {}
        for row in range(size):
            for column in range(size):
                turn = state["yourShots"][row][column]
                if turn != -1:
                    turns.setdefault(turn, set()).add((row, column))
        return turns

    @staticmethod
    def _losses_by_turn(state: Dict[str, Any]) -> Dict[int, Dict[str, int]]:
        """Turn number -> how many parts each kind of ship lost on it."""
        slots = state["enemyFleetHits"]
        losses: Dict[int, Dict[str, int]] = {}
        for ship in state["fleet"]:
            first, last = ship["slots"]
            for turn in slots[first:last + 1]:
                if turn != -1:
                    per_turn = losses.setdefault(turn, {})
                    per_turn[ship["ship"]] = per_turn.get(ship["ship"], 0) + 1
        return losses

    @staticmethod
    def _fleet(state: Dict[str, Any]) -> Tuple[List[Tuple[str, List[Cell], bool]], int]:
        """The one-of-a-kind ships with their shapes, plus how many scouts are left."""
        singles: List[Tuple[str, List[Cell], bool]] = []
        scouts_alive = 0
        for ship in state["fleet"]:
            first, last = ship["slots"]
            filled = sum(1 for turn in state["enemyFleetHits"][first:last + 1] if turn != -1)
            alive = ship["count"] - filled // ship["cells"]
            # The feed gives shapes as [column, row]; cells here are (row, column).
            shape = [(dy, dx) for dx, dy in ship["shape"]]
            if ship["count"] == 1:
                singles.append((ship["ship"], shape, alive > 0))
            else:
                scouts_alive = alive
        return singles, scouts_alive

    # ---------------------------------------------------------------- geometry

    @staticmethod
    def _positions(size: int, shape: List[Cell]) -> List[List[Cell]]:
        """Every place this shape fits on the board."""
        places = []
        for row in range(size):
            for column in range(size):
                cells = [(row + dr, column + dc) for dr, dc in shape]
                if all(0 <= r < size and 0 <= c < size for r, c in cells):
                    places.append(cells)
        return places

    @staticmethod
    def _moat(cells: List[Cell], size: int) -> Set[Cell]:
        """The ring of water a ship is guaranteed to sit in."""
        ring = set()
        for row, column in cells:
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    r, c = row + dr, column + dc
                    if 0 <= r < size and 0 <= c < size:
                        ring.add((r, c))
        return ring - set(cells)

    @staticmethod
    def _spread(ranked: List[Cell], want: int) -> List[Cell]:
        chosen: List[Cell] = []
        for cell in ranked:
            if len(chosen) == want:
                break
            if any(max(abs(cell[0] - r), abs(cell[1] - c)) < 3 for r, c in chosen):
                continue
            chosen.append(cell)
        for cell in ranked:
            if len(chosen) == want:
                break
            if cell not in chosen:
                chosen.append(cell)
        return chosen


# ------------------------------------------------------------------ driver


def play(client: BattleshipClient, level: int, quiet: bool) -> Tuple[bool, int]:
    client.new_game(level)
    state = client.wait_until_ready(timeout=60)
    bot = DeductionBot()
    turns = 0

    while not state.get("gameOver"):
        shots = bot.choose(state)
        state = client.fire(shots)

        if state.get("lastError"):
            raise RuntimeError(f"Rejected {[cell_name(c) for c in shots]}: {state['lastError']}")

        turns += 1
        if not quiet:
            print(f"  {turns:3}  {' '.join(cell_name(c) for c in shots)}"
                  f"   enemy {state['enemyPartsHit']}/{state['partsPerFleet']}"
                  f"   us {state['yourPartsHit']}/{state['partsPerFleet']}")

        state = client.wait_until_ready(timeout=60)

    return state.get("winner") == "player", turns


def main() -> None:
    parser = argparse.ArgumentParser(description="Battleship turn-based AI client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11000)
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--level", type=int, default=-1, help="0 easy, 1 hard, -1 keep")
    parser.add_argument("--speed", type=float, default=1.0, help="game clock, 1 is normal")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    with BattleshipClient(args.host, args.port, timeout=20) as client:
        if args.speed != 1.0:
            client.set_speed(args.speed)

        wins, total = 0, 0
        for game in range(args.games):
            won, turns = play(client, args.level, args.quiet)
            wins += int(won)
            total += turns
            print(f"Game {game + 1}: {'WIN' if won else 'LOSS'} in {turns} turns")

        print(f"Result: won {wins}/{args.games}, "
              f"{total / max(1, args.games):.1f} turns on average")


if __name__ == "__main__":
    main()
