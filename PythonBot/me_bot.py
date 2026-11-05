"""The runner. You do not need to change this file.

It connects to the Unity referee, hands each turn to `strategy.choose`, and
sends back the order. Your strategy lives in `strategy.py`; the helpers it
calls live in `bot_api.py`.

    Battleship.exe -extbot -bots 5 -medium
    python -u me_bot.py
"""

import json
import socket
import sys
import time

import bot_api
import strategy

HOST = "127.0.0.1"
PORT = 8420


def connect(host, port, timeout=60.0):
    """Wait for the referee to open its socket.

    Unity takes a few seconds to start, so connecting straight away loses a race
    that has nothing to do with your bot. Retry quietly until it is there.
    """
    deadline = time.time() + timeout
    while True:
        try:
            return socket.create_connection((host, port), timeout=5.0)
        except OSError:
            if time.time() >= deadline:
                raise
            time.sleep(0.5)


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT

    memory = bot_api.Memory()
    print(f"waiting for the referee on {host}:{port} ...")

    with connect(host, port) as connection:
        print(f"connected to the referee at {host}:{port}")

        try:
            with connection.makefile("rw", encoding="utf-8", newline="\n") as stream:
                for line in stream:
                    line = line.strip()
                    if not line:
                        continue

                    state = json.loads(line)

                    # A batch run plays several battles down one connection.
                    # Tick 1 means a new sea: forget the old wind and shots.
                    if state.get("tick", 0) <= 1 and memory.had_a_turn:
                        print(f"--- new battle ---")
                        memory = bot_api.Memory()

                    memory.before_turn(state)
                    sea = bot_api.Sea(state, memory)

                    try:
                        order = strategy.choose(sea)
                    except Exception as error:
                        # A crash is a silent tick, not a reason to drop the
                        # connection: say nothing this turn, try again next one.
                        print(f"tick {sea.tick}: strategy raised {error!r}")
                        continue

                    if order is None:
                        print(f"tick {sea.tick}: strategy returned nothing")
                        continue

                    memory.after_turn(order)
                    stream.write(json.dumps(order.to_wire()) + "\n")
                    stream.flush()

                    _report(sea)
        except (OSError, ValueError):
            # The game was closed. Not an error worth a traceback.
            pass

    print("referee closed the connection")


def _report(sea):
    """A line every ten ticks, and a word whenever something lands."""
    shot = sea.last_shot
    if shot.fired and shot.results:
        if shot.sank:
            print(f"tick {sea.tick:>3}  SUNK at {shot.landed_at}")
        elif shot.hit:
            print(f"tick {sea.tick:>3}  hit at {shot.landed_at}")

    if sea.tick % 10 == 0:
        wind = sea.wind
        aim = "on target" if shot.on_target else f"drift {shot.drift}"
        print(f"tick {sea.tick:>3}  score {sea.score:>3}"
              f"  wind~({wind[0]:+.2f}, {wind[1]:+.2f}) from {sea.wind_confidence} shots"
              f"  last: {aim}")


if __name__ == "__main__":
    main()
