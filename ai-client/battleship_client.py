"""
Battle Ship - external control client.

Speaks the same wire protocol as the VCCRacing autonomous driver, so an existing
client is mostly a rename away: send one JSON object, read back an 8-byte
big-endian length followed by that many bytes of payload.

    python battleship_client.py              # connect to 127.0.0.1:11000 and play
    python battleship_client.py --port 11001
"""

import argparse
import json
import math
import socket
import struct
import time
from typing import Any, Dict, Optional

STATE_DATA = 185
RAW_IMAGE = 203
SEGMENTED_IMAGE = 31


class BattleShipClient:
    """Connects to the game and exchanges controls for telemetry."""

    def __init__(self, host: str = "127.0.0.1", port: int = 11000, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None

        # Current control intent, sent with every request.
        self.speed = 0.0      # -90 .. 90   (ahead / astern)
        self.angle = 0.0      # -25 .. 25   (rudder, + is starboard)
        self.turret: Optional[float] = None  # absolute degrees, None = auto-track nearest
        self.fire = 0         # 1 to pull the trigger this tick
        self._reset = 0       # 1 restarts the match on the next request
        self._ship = -1       # 0 corvette, 1 cruiser, 2 gunboat, -1 keep current

    # ---------------------------------------------------------------- connection

    def connect(self) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        self.socket.connect((self.host, self.port))
        print(f"Connected to Battle Ship at {self.host}:{self.port}")

    def close(self) -> None:
        if self.socket:
            try:
                self.socket.close()
            finally:
                self.socket = None

    def __enter__(self) -> "BattleShipClient":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ---------------------------------------------------------------- controls

    def set_control(self, speed: float, angle: float,
                    turret: Optional[float] = None, fire: bool = False) -> None:
        """Set the orders sent with the next request."""
        self.speed = float(speed)
        self.angle = float(angle)
        self.turret = None if turret is None else float(turret)
        self.fire = 1 if fire else 0

    def choose_ship(self, ship: int) -> None:
        """0 corvette, 1 cruiser, 2 gunboat. Applies to the next (re)start."""
        self._ship = int(ship)

    def reset(self) -> Dict[str, Any]:
        """
        Restart the match and return the first state of the new run.

        Needed for unattended play: a sunk controller cannot press R.
        """
        self._reset = 1
        try:
            return self.get_state()
        finally:
            self._reset = 0

    # ---------------------------------------------------------------- transport

    def _command(self, mode: int) -> bytes:
        cmd: Dict[str, Any] = {
            "Cmd": mode,
            "Speed": self.speed,
            "Angle": self.angle,
            "Fire": self.fire,
            "Reset": self._reset,
            "Ship": self._ship,
        }
        if self.turret is not None:
            cmd["Turret"] = self.turret
        return json.dumps(cmd).encode("utf-8")

    def _read_exactly(self, count: int) -> bytes:
        chunks = []
        remaining = count
        while remaining > 0:
            chunk = self.socket.recv(min(remaining, 65536))
            if not chunk:
                raise ConnectionError("Server closed the connection")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _request(self, mode: int) -> bytes:
        if not self.socket:
            raise ConnectionError("Not connected")
        self.socket.sendall(self._command(mode))
        header = self._read_exactly(8)
        (length,) = struct.unpack(">Q", header)
        return self._read_exactly(length) if length else b""

    def get_state(self) -> Dict[str, Any]:
        """Send the current controls and return the world state."""
        return json.loads(self._request(STATE_DATA).decode("utf-8"))

    def wait_for_match(self, timeout: float = 15.0) -> Dict[str, Any]:
        """
        Block until the arena is actually running.

        The first command is what pulls the game out of the menu, so the first few
        replies arrive before there is a world to describe. Without this you would be
        reading empty states and wondering why every field is None.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.get_state()
            if state.get("self", {}).get("healthMax", 0) > 0:
                return state
            time.sleep(0.05)
        raise TimeoutError("Match did not start within %.0fs" % timeout)

    def get_raw_image(self) -> bytes:
        """JPEG bytes of the current view, for vision-based control."""
        return self._request(RAW_IMAGE)


# -------------------------------------------------------------------- example AI


def choose_action(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    A deliberately simple strategy, meant to be replaced.

    Closes to a comfortable firing range on the nearest contact, keeps the guns on
    it, and shoots whenever reloaded.
    """
    me = state.get("self", {})
    enemies = state.get("enemies", [])

    if not enemies:
        return {"speed": 25, "angle": 0, "turret": None, "fire": False}

    target = min(enemies, key=lambda e: e.get("distance", 1e9))
    distance = target.get("distance", 0.0)
    bearing = target.get("bearing", 0.0)
    heading = me.get("heading", 0.0)

    # Smallest signed turn from our heading onto the target.
    error = (bearing - heading + 180.0) % 360.0 - 180.0

    # Hold a standoff band rather than ramming.
    if distance > 9.0:
        speed = 70
    elif distance < 5.0:
        speed = -30
    else:
        speed = 25

    angle = max(-25.0, min(25.0, error / 3.0))

    return {
        "speed": speed,
        "angle": angle,
        "turret": bearing,
        "fire": bool(me.get("reloaded", 0)) and distance < 12.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Battle Ship AI client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11000)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    with BattleShipClient(args.host, args.port) as client:
        # The first command pulls the game out of the menu; wait for a real world.
        state = client.wait_for_match()
        print("Match started.")

        tick = 0
        while True:
            if state.get("gameOver"):
                print(f"Game over - wave {state.get('wave')}, score {state.get('score')}")
                break

            action = choose_action(state)
            client.set_control(action["speed"], action["angle"],
                               action["turret"], action["fire"])

            tick += 1
            if not args.quiet and tick % 60 == 0:
                me = state.get("self", {})
                print(f"wave {state.get('wave')} "
                      f"score {state.get('score')} "
                      f"hull {me.get('health', 0):.0f}/{me.get('healthMax', 0):.0f} "
                      f"contacts {len(state.get('enemies', []))}")

            # Run at roughly frame rate. Without a pause this spins thousands of times a
            # second, which floods the socket and buys nothing: the game only advances
            # once per frame.
            time.sleep(1 / 60)
            state = client.get_state()


if __name__ == "__main__":
    main()
