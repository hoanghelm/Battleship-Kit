# Battle Ship — AI Control API

Write a program that commands a warship. The game exposes a TCP port; your code sends
orders and reads back the state of the battle.

The protocol is the same shape as the VCCRacing autonomous driver, so an existing client
is mostly a rename away.

---

## Quick start

1. Launch the game. The control port opens on 11000 at startup, before any menu:

   ```
   BattleShip.exe
   ```

   The HUD shows `CONTROLLER LINKED` once your program connects.

2. Run the sample bot:

   ```bash
   python battleship_client.py
   ```

That is it. The first command your program sends enters the arena and starts the match,
so there is nothing to click and unattended runs work.

---

## The rules

You command one ship in an open arena. Enemies arrive in waves that grow each round.
Sink them; do not get sunk.

- Shells travel at a finite speed, so **lead your target** — aim where it is going.
- The rudder only bites when the hull has way on. A stopped ship cannot turn.
- Your gun has a reload time. `self.reloaded` tells you when it is ready.

> Note: a program steers with throttle (`Speed`) and rudder (`Angle`), so your ship has a
> turning circle. A human at the keyboard gets direct 8-way movement instead. The two
> deliberately differ — do not be surprised when playing feels different from driving.

---

## Protocol

TCP, default port **11000**. Override with `BattleShip.exe --ai-port 11001` to run
several instances side by side.

Each exchange is one request, one reply:

1. You send **one JSON object**.
2. The server replies with an **8-byte big-endian length**, then that many bytes.

### Request

```json
{ "Cmd": 185, "Speed": 70, "Angle": 12, "Turret": 45.0, "Fire": 1, "Reset": 0, "Ship": -1 }
```

| Field | Range | Meaning |
|---|---|---|
| `Cmd` | `185` / `203` / `31` | state / raw JPEG / segmented image |
| `Speed` | -90 … 90 | throttle; negative is astern |
| `Angle` | -25 … 25 | rudder; positive turns to starboard |
| `Turret` | degrees | absolute bearing. **Omit it and the guns auto-track the nearest enemy** |
| `Fire` | 0 / 1 | pull the trigger this tick (still subject to reload) |
| `Reset` | 0 / 1 | restart the match — needed for unattended runs |
| `Ship` | 0 / 1 / 2 / -1 | hull for the next start: corvette / cruiser / gunboat / keep |

`Cmd` is the only required field.

### Reply (`Cmd: 185`)

```json
{
  "time": 12.4, "wave": 2, "score": 300, "enemiesLeft": 3, "gameOver": 0,
  "arenaHalfWidth": 19.0, "arenaHalfHeight": 12.0,

  "self": { "x": 1.2, "y": -3.4, "heading": 27.5, "speed": 5.1,
            "health": 142, "healthMax": 170, "turret": 63.0, "reloaded": 1 },

  "enemies": [ { "id": 4, "x": 9.1, "y": 2.2, "heading": -140.0, "speed": 3.6,
                 "health": 38, "distance": 10.4, "bearing": 36.2 } ],

  "shells":  [ { "x": 4.0, "y": 1.0, "vx": -9.2, "vy": 3.1, "hostile": 1 } ]
}
```

Angles are degrees, `0` along world +X, counter-clockwise, wrapped to -180…180.
`bearing` is measured from your ship to the contact, so steering onto a target is:

```python
error = (bearing - heading + 180) % 360 - 180
```

`id` is stable for as long as that ship is afloat, so you can track a contact between
frames. A contact that disappears from `enemies` has been sunk.

`hostile: 1` on a shell means it was fired at you — enough information to dodge.

---

## Choosing a hull

| | Hull | Speed | Damage | Reload | Character |
|---|---|---|---|---|---|
| `0` | **Corvette** | 110 | 8.0 | 9 | 0.30s | Fast and fragile; wins by never being where the shells are |
| `1` | **Cruiser** | 170 | 6.4 | 14 | 0.40s | Balanced; the honest default |
| `2` | **Gunboat** | 260 | 4.9 | 24 | 0.62s | Soaks damage and hits hard; slow to answer the rudder |

```python
client.choose_ship(2)   # gunboat
client.reset()          # takes effect on the restart
```

---

## Python client

```python
from battleship_client import BattleShipClient

with BattleShipClient(port=11000) as c:
    while True:
        state = c.get_state()          # sends your orders, returns the world
        if state["gameOver"]:
            state = c.reset()          # start another run
            continue

        me = state["self"]
        contacts = state["enemies"]
        if not contacts:
            c.set_control(speed=25, angle=0)
            continue

        target = min(contacts, key=lambda e: e["distance"])
        error = (target["bearing"] - me["heading"] + 180) % 360 - 180

        c.set_control(
            speed=70 if target["distance"] > 9 else 0,
            angle=max(-25, min(25, error / 3)),
            turret=target["bearing"],
            fire=bool(me["reloaded"]),
        )
```

### Methods

| Call | Does |
|---|---|
| `get_state()` | Send current orders, return the world state |
| `set_control(speed, angle, turret=None, fire=False)` | Set the orders for the next request |
| `choose_ship(0\|1\|2)` | Pick the hull for the next start |
| `reset()` | Restart the match, return the first state of the new run |
| `get_raw_image()` | JPEG bytes of the current view, for vision-based control |

---

## Writing in another language

Nothing here is Python-specific. Any language that can open a socket works:

```
connect to 127.0.0.1:11000
loop:
    send  {"Cmd":185,"Speed":70,"Angle":0,"Fire":1}
    read  8 bytes  -> length (big-endian uint64)
    read  length bytes -> UTF-8 JSON
```

---

## Notes and limits

- **Commands apply on the next frame.** The server answers from the snapshot the game
  published, so there is up to one frame of latency. At 60 fps that is well inside the
  tolerance of any control loop, and it is what keeps the socket off Unity's main thread.
- **Images are published at about 10 Hz**, not per frame — reading the backbuffer stalls
  the GPU, and no control loop needs 60 fps vision. `Cmd: 31` currently returns the same
  image as `203`; there is no segmentation pass yet.
- **A human can still play** while nothing is connected. The moment a command arrives the
  external controller takes over the helm.
