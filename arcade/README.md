# Battle Ship — AI Hackathon Kit

Write a program that commands a warship in real time.

The game runs as a server. Your program connects over TCP, reads the state of the battle,
and sends back orders: throttle, rudder, where to point the guns, when to fire.

```
BattleShip-AI-Kit/
├── Game/                     the game (Windows x64)
│   └── BattleShip.exe
└── ai-client/
    ├── battleship_client.py  working Python client + sample bot
    └── README.md             full API reference
```

---

## Get something driving in two minutes

**1. Start the game**

```
Game\BattleShip.exe
```

Leave it on the menu. The control port opens on **11000** as soon as the game launches.

**2. Run the sample bot** (needs Python 3.8+, no dependencies)

```bash
cd ai-client
python battleship_client.py
```

The game jumps straight into the arena and the ship starts moving and shooting. The HUD
shows **CONTROLLER LINKED** while your program is connected.

You never have to touch the menu: the first command your program sends enters the arena
and starts the match, which is what makes unattended tournament runs possible.

**3. Make it yours**

Open `ai-client/battleship_client.py` and edit `choose_action()`. That function receives
the world and returns what to do. Everything else is plumbing.

---

## The loop you are writing

```python
from battleship_client import BattleShipClient

with BattleShipClient(port=11000) as c:
    while True:
        state = c.get_state()              # sends last orders, returns the world

        if state["gameOver"]:
            state = c.reset()              # start another run
            continue

        me = state["self"]
        contacts = state["enemies"]
        if not contacts:
            c.set_control(speed=25, angle=0)
            continue

        target = min(contacts, key=lambda e: e["distance"])

        # Smallest signed turn from our heading onto the target.
        error = (target["bearing"] - me["heading"] + 180) % 360 - 180

        c.set_control(
            speed = 70 if target["distance"] > 9 else 0,   # -90..90
            angle = max(-25, min(25, error / 3)),          # -25..25
            turret = target["bearing"],                    # omit = auto-track nearest
            fire = bool(me["reloaded"]),
        )
```

---

## What you get back each tick

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

- Angles are degrees, `0` along +X, counter-clockwise, wrapped to -180…180.
- `bearing` is measured **from your ship** to the contact.
- `id` stays the same while that ship is afloat, so you can track a contact between
  frames. A contact missing from `enemies` has been sunk.
- `hostile: 1` on a shell means it is coming at you — enough to dodge.

---

## Three things that decide whether your bot is good

**Lead your shots.** Shells take time to arrive. Firing at where an enemy *is* will miss
a moving target; aim where it *will be*:

```python
flight = target["distance"] / 15.0          # your shell speed
aim_x = target["x"] + target_vx * flight
aim_y = target["y"] + target_vy * flight
```

(You can get a contact's velocity from its `heading` and `speed`.)

**A stopped ship cannot turn.** The rudder only bites when the hull has way on. If you
cut the throttle to line up a shot, you also lose your ability to steer.

**Dodge.** The `shells` array tells you what is in the air and whether it is aimed at
you. Most entries will ignore this. The ones that do not will last longer.

---

## Choosing a hull

| | Hull | Speed | Damage | Reload | Character |
|---|---|---|---|---|---|
| `0` | **Corvette** | 110 | 8.0 | 9 | 0.30s | Fast and fragile; wins by not being there |
| `1` | **Cruiser** | 170 | 6.4 | 14 | 0.40s | Balanced; the honest default |
| `2` | **Gunboat** | 260 | 4.9 | 24 | 0.62s | Soaks damage, hits hard, slow on the rudder |

```python
client.choose_ship(2)   # gunboat
client.reset()          # applies on the restart
```

---

## Not using Python?

Nothing here is Python-specific. Any language with a socket works:

```
connect 127.0.0.1:11000
loop:
    send  {"Cmd":185,"Speed":70,"Angle":0,"Fire":1}
    read  8 bytes       -> payload length, big-endian uint64
    read  <length> bytes -> UTF-8 JSON
```

Full field reference: [`ai-client/README.md`](ai-client/README.md).

---

## Running several at once

Each instance needs its own port:

```
Game\BattleShip.exe --ai-port 11001
Game\BattleShip.exe --ai-port 11002
```

Skip the menu entirely by preselecting a hull:

```
Game\BattleShip.exe --ship gunboat
```

---

## Playing it yourself

Useful for feeling out the game before you automate it.

| | Keyboard | Gamepad |
|---|---|---|
| Move | `↑` `↓` `←` `→` or `W` `A` `S` `D` | Left stick |
| Diagonal | hold two, e.g. `↑`+`→` goes north-east | — |
| Aim | Mouse, or `Q`/`E` to turn the turret | Right stick |
| Fire | Click, `Space` or `Enter` | Right trigger / `A` |
| Restart / menu | `R` / `Esc` | `A` / `B` |

Movement is **absolute**: `→` goes east, not "turn starboard". Diagonals are normalised,
so `↑`+`→` is no faster than `↑` alone. The bow swings round to face your course.

When nothing is aiming, the guns follow the bow.

> **The keyboard and the API steer differently on purpose.** The keyboard is direct
> 8-way, because fighting the boat is the wrong thing to be hard in an arcade game.
> Programs use `Speed` + `Angle` (throttle and rudder), which is a harder but more
> interesting control problem — leading shots while managing a turning circle. Say the
> word if you would rather the API were 8-way too.

A connected program takes over the helm; disconnect it and the keyboard works again.

---

## Known limits

- **Commands apply on the next frame** (~16 ms at 60 fps). The server answers from the
  snapshot the game last published, which is what keeps the socket off Unity's main
  thread. No control loop should notice.
- **`Cmd: 203` images are published at ~10 Hz**, not per frame, and `Cmd: 31`
  (segmented) currently returns the same picture — there is no segmentation pass yet.
- **Windows x64 only** in this build.
