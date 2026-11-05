# Battleship Royale

Every team's fleet shares one 40×40 sea. Each tick, every bot picks one of its
own ships and fires an arc: a compass bearing, an elevation and a power. You
never name a cell to shoot at. There's a wind, it's the same all battle, and
nobody tells you what it is, so working it out from where your shells actually
land is most of the game.

Download the repo, run `Game/Battleship.exe`, and you're playing. Write a bot in
anything that can open a TCP socket; there's a Python one in `PythonBot/` to
start from.

## Playing

Double-click `Game/Battleship.exe`. The start screen picks how many opponent bots to
play against (1 to 14), how good they are, and whether your own seat is played
by a built-in bot or by your program.

While a battle is running, `V` swaps between the tilted 3D sea and the flat 2D
grid, `Space` pauses, `.` steps a single tick, and the number keys set the
speed from 1× up to 10× on `0`. `F` goes full screen. `L` dumps the battle to a
JSON log and `P` plays the last one back.

Everything is also available from the command line, which is how you'd script a
batch of test battles:

```
Battleship.exe -extbot -bots 5 -hard -turbo -battles 50
```

| flag | what it does |
| --- | --- |
| `-bots 5` | number of opponents |
| `-easy` `-medium` `-hard` | how good they are |
| `-extbot` | your seat waits for an external bot |
| `-botport 8420` | port it listens on |
| `-armoury flare:2,cluster:2` | your Armory choice |
| `-seed 1234` | fix the seed |
| `-battles 50` | play a batch then quit |
| `-turbo` | run as fast as the bot answers |
| `-replay [file]` | watch a saved battle |
| `-speed 4` | playback speed |
| `-mode2d` `-fullscreen` `-autostart` | start-up state |

Not `-adapter` or `-port`, by the way. Unity reserves both and strips them
before the game sees them, which costs you an afternoon if you don't know.

## The protocol

Newline-delimited JSON over TCP on `127.0.0.1:8420`. The referee writes one
state per line as soon as the previous tick resolves; you write one action back.
Coordinates are always `[row, col]`, both counted from zero, with row 0 at the
top and rows growing downward.

Here's a real state, straight off the wire, trimmed only in the shot list:

```json
{
  "tick": 12,
  "seat": "F",
  "seats": ["A", "B", "C", "D", "E", "F"],
  "score": 0,
  "config": {
    "map": { "rows": 40, "cols": 40 },
    "physics": { "power_max": 5, "speed_per_power": 4, "gravity": 9.8 },
    "action_deadline_ms": 500,
    "tick_cap": 120
  },
  "you": {
    "ships": [
      { "ship": "carrier",    "cells": [[19,16],[20,16],[21,16],[22,16],[23,16]],
        "holed": [false,false,false,false,false], "sunk": false },
      { "ship": "battleship", "cells": [[0,20],[0,21],[0,22],[0,23]],
        "holed": [false,true,true,true], "sunk": false },
      { "ship": "cruiser",    "cells": [[0,9],[1,9],[2,9]],
        "holed": [false,false,false], "sunk": false },
      { "ship": "submarine",  "cells": [[17,7],[18,7],[19,7]],
        "holed": [false,false,false], "sunk": false },
      { "ship": "destroyer",  "cells": [[34,32],[34,33]],
        "holed": [false,false], "sunk": false }
    ]
  },
  "your_shots": [[38,35,"miss"], [12,4,"hit"], [-3,19,"off_the_sea"]],
  "incoming": [[0,23,"hit",2], [0,22,"hit",2], [0,21,"hit",4]],
  "boosters": { "flare": 2, "cluster": 2, "torpedo": 0, "teleport": 0 },
  "lit_cells": [],
  "last_action": { "fired": true, "landed": [38,35], "teleported": false }
}
```

And the action you send back:

```json
{ "ship": "carrier", "dir": 135.0, "elev": 45.0, "power": 4, "booster": "cluster" }
```

`ship` has to be one of yours that was afloat when the tick began, named as it
appears in `you.ships[].ship`. `dir` is a compass bearing from 0 to 360, where 0
points up the map, 90 right, 180 down. `elev` runs 0 to 90; at 0 the shell lands
on your own firing origin, which is rarely what you want. `power` is a whole
number from 1 to 5. `booster` is optional and is one of `flare`, `cluster`,
`torpedo`, `teleport`.

All four aim fields are required every tick, even when the booster you're firing
doesn't launch a shell.

### The fields worth explaining

`you.ships[].cells[0]` is the ship's firing origin, the cell every shell leaves
from. Cells are always listed top to bottom or left to right, so index 0 is
genuinely the end you fire from.

`your_shots` is every shot you've fired as `[row, col, result]`, where the
coordinates are where the shell actually came down, not where you aimed. Shots
that went off the board are in there too, with their real out-of-bounds
coordinates, because those still tell you about the wind.

`incoming` is the shells that holed cells of *your* ships, as
`[row, col, result, tick]`. You're never told who fired. The tick is there so
you can tell "somebody is working down this hull right now" from "I got hit once
ten turns ago".

`lit_cells` is enemy cells your flares revealed and that are still unhit.

`last_action.landed` is where your previous shell came down. Compare it against
where the no-wind formula says it should have gone, divide by the time in the
air, and that's the wind. It's the only way to get it.

### Results

Six of them, and a shot is exactly one: `hit`, `sunk`, `miss`, `wreck`,
`off_the_sea`, `self_hit`. A `wreck` means the cell was already holed before
your shell arrived, so someone else is working that ship. When a ship goes down,
your earlier `hit` entries on it turn into `sunk`, which is how you find out a
ship you'd been chasing is gone.

### Things that will catch you out

Nothing gets repaired. `365` is not read as `5`, and power `6` is not clamped to
`5`. A missing field, a value out of range, a late answer or a crash all mean
the same thing: your seat fires nothing that tick. Three of those in a row and
you're disconnected for the rest of the battle.

The deadline is `config.action_deadline_ms` from when the state was sent, not
from when you got round to reading it.

A torpedo doesn't fly and a teleport doesn't fire, so `last_action.landed` for
those is a stop cell or nothing at all. Feed either into a wind estimate and
you'll poison it.

## The Python starting point

`PythonBot/` has a bot that already plays a whole battle, so you can run it
before changing anything and watch it work.

You only edit `strategy.py`, which is one function. `bot_api.py` works out the
bearings, elevations, powers and wind correction for you, and `me_bot.py` is
just the socket. Say where you want to fire and which skill to spend; don't
compute angles.

```python
def choose(sea):
    if sea.hits:
        return sea.fire_at(sea.neighbours(sea.hits[-1])[0], skill="cluster")
    return sea.fire_at((20, 21)) or sea.fire_somewhere()
```

Start the game with `-extbot` and it opens a socket and waits, then run the
bot. The panel on the left says whether you're connected.

```
Game\Battleship.exe -extbot -bots 5 -medium
python PythonBot\me_bot.py
```

## Getting an AI to write your strategy

This is the intended way to work: describe the behaviour you want, let an
assistant write the Python.

Point it at `PythonBot/` first. `CLAUDE.md` in there is a briefing covering the
contract, the rules a bot has to stay inside, and the traps this code has
already fallen into. Claude Code picks it up on its own; anything else, tell it
to read `CLAUDE.md` before touching `strategy.py`.

Then describe behaviour, not code:

> After a hit, finish that ship before searching again. Right now it wanders
> off after two shots.

> Stop wasting clusters early. Only fire one when we already have a confirmed
> hit next to the target.

Rather than "add a while loop in `_finish_line`". You know the game; it knows
Python.

Give it the evidence when something is wrong. The bot prints a line every ten
ticks and the game shows the real wind, so paste what you saw:

> Score was still 0 at tick 60 and the wind estimate stayed near zero. Here is
> the output: `tick 60 score 0 wind~(+0.02, -0.01) samples 51`

That finds the cause far faster than "it plays badly".

Then check it before you trust it. Run a battle and watch two numbers: the score
should climb, and the wind estimate should converge towards the wind in the
game's panel. If either is flat the change did not work, and saying so is more
useful than accepting it.

One habit worth keeping: change one thing at a time. Two changes and a worse
score tells you nothing about which caused it.

## Logs and replay

Each battle writes a JSON file into `logs/` when it finishes: where every fleet
started, what the wind was, and for each tick what every ship fired, from where,
where the shell came down, which cells it struck and what each one found. Silent
ticks get logged with the reason, which is usually the first thing you want when
a bot is misbehaving.

Replay re-runs the battle from its seed and the recorded actions rather than
replaying a recording. Slower to write, but it reproduces things the log doesn't
store, like where a teleported ship ended up or which cells a cluster happened
to catch, and it means you can scrub backwards.
