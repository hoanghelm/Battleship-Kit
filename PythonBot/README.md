# Driving the "me" seat from Python

The game plays one seat called **me**. By default a built-in bot plays it. Turn on
**EXTERNAL BOT (PYTHON)** on the start screen (or pass `-adapter`) and that seat
waits for your program instead.

## Running it

```
Battleship.exe -extbot -bots 5 -hard
python me_bot.py
```

Start the game first — it opens the socket — then the bot. The **SKILLS LEFT**
panel shows `waiting for python bot on :8420` until you connect, then
`python bot connected`.

Useful flags:

| Flag | Meaning |
|---|---|
| `-extbot` | the "me" seat waits for a Python bot |
| `-botport 8420` | which port to listen on |
| `-bots 5` | how many opponent bots (1–14) |
| `-easy` `-medium` `-hard` | opponent difficulty |
| `-mode2d` | open in the grid view |
| `-fullscreen` | open full screen |
| `-autostart` | skip the start screen |
| `-speed 4` | playback speed, 1 to 10 |
| `-replay` | watch the newest saved battle |
| `-replay path.json` | watch that saved battle |

The flags are deliberately not called `-adapter` and `-port`: Unity reserves both
as engine arguments and strips them before the game sees them.

## The three files

Only one of them is yours.

| File | Yours? | What it is |
|---|---|---|
| `strategy.py` | **yes** | `choose(sea)` — the whole bot, in plain terms |
| `bot_api.py` | no | works out bearings, elevations, powers and the wind |
| `me_bot.py` | no | connects to the game |

A strategy says *where* to fire and *which skill* to spend. It never computes an
angle:

```python
def choose(sea):
    if sea.hits:
        return sea.fire_at(sea.neighbours(sea.hits[-1])[0], skill="cluster")
    return sea.fire_at((20, 21)) or sea.fire_somewhere()
```

And it can see what happened last turn:

```python
sea.last_shot.on_target   # did the shell land where we sent it?
sea.last_shot.drift       # if not, how far off, as (row, col)
sea.last_shot.hit         # did it hit a ship?
sea.last_shot.sank        # did it sink one?
sea.last_shot.skill_fired # which skill actually went off
```

`strategy.py` lists everything available at the top of the file.

## Asking an AI to edit the bot

You are not expected to write the Python. Describe the behaviour you want and
let an assistant make the change — that is how the event is meant to run.

**Point it at this folder first.** `CLAUDE.md` here is a briefing: which file to
edit, the submission rules it must not break, and the four traps this code has already
fallen into. Claude Code reads it automatically; for anything else, tell it to
read `CLAUDE.md` before changing anything.

**Describe behaviour, not code.** You know the game; the assistant knows Python.
Say what the bot should *do* and why, and leave the implementation to it.

| Ask this | Not this |
|---|---|
| "After a hit, finish that ship before searching again — right now it wanders off after two shots." | "Add a while loop in `_next_to_a_hit`." |
| "Stop wasting clusters early. Only fire one when we already have a confirmed hit next to the target." | "Change line 118." |
| "We keep shelling the same empty corner. Spread the search over the whole sea." | "Fix the search." |
| "Save a teleport for when a ship is one hit from sinking, not half-holed." | "Make teleport better." |

**Give it the evidence.** The bot prints a line every ten ticks and the game
shows the true wind. Paste what you saw:

> "Score was still 0 at tick 60 and the wind estimate stayed near zero. Here's
> the output: `tick 60 score 0 wind≈(+0.02, -0.01) samples 51`"

That tells an assistant far more than "it plays badly", and it is usually enough
to find the cause without guessing.

**Say what not to break.** Worth repeating in the prompt when you ask for
something big:

> "Only change `strategy.py`, stay inside the import rules, and keep it
> answering within the 500 ms deadline."

**Check it before you trust it.** Run a practice battle and watch two numbers:
the score should climb, and the wind estimate should converge towards the wind
shown in the game's bottom-right panel. If either is flat, the change did not
work — say so and give the assistant the numbers.

One habit worth keeping: **change one thing at a time**. Two changes in one go
and a worse score tells you nothing about which caused it.

## Battle logs

Every battle is written out as JSON when it ends, into `logs/` beside the game.
Press **[L]** to save one mid-battle.

It holds every fleet's starting positions, the wind, and for each tick what
every ship did -- what it fired, from where, where the shell landed, every cell
it struck and what each one found:

```json
{
  "tick": 41,
  "actions": [
    {
      "seat": "D", "team": "me", "ship": "carrier",
      "fired_from": [10, 10],
      "dir": 135.0, "elev": 45.0, "power": 4,
      "skill_requested": "cluster", "skill_fired": "cluster",
      "landed": [29, 28],
      "shots": [
        {"cell": [29, 28], "result": "hit"},
        {"cell": [29, 29], "result": "miss"}
      ],
      "points": 1
    }
  ],
  "sunk": [{"seat": "B", "ship": "destroyer"}]
}
```

### Watching a battle back

Press **[P]** after a battle, or **WATCH LAST BATTLE** on the start screen, or
launch with `-replay`. The playback bar runs along the bottom: click the track to
jump, **[Space]** to pause, **[.]** to step one tick, **[<]** and **[>]** to skip
ten, and 1x to 10x on the speed buttons or the number keys.

The replay re-runs the battle from the seed and the recorded actions rather than
playing back a recording, which is why it can show you things the log does not
store -- where a teleported ship went, which cells a cluster happened to strike --
and why you can scrub backwards at all.

A silent tick is logged too, with why -- usually the most useful line in the
file when a bot is misbehaving:

```json
{"seat": "D", "team": "me", "silent": true, "reason": "OutOfRange: elev 94.2"}
```

The wind is in the log even though no bot ever saw it: a result cannot be
re-checked without it.

## The protocol

Newline-delimited JSON over TCP on `127.0.0.1`. The referee writes one **state**
object per line; you write one **action** object per line.

The field names are the ones the rulebook's starter bot already reads, so a bot
written against `arena_sdk` only needs its transport swapped, not its logic.

State (trimmed):

```json
{
  "tick": 41,
  "seat": "C",
  "seats": ["A","B","C","D","E","F"],
  "score": 18,
  "config": {
    "map": {"rows": 40, "cols": 40},
    "physics": {"power_max": 5, "speed_per_power": 4, "gravity": 9.8},
    "action_deadline_ms": 500,
    "tick_cap": 120
  },
  "you": {"ships": [
    {"ship": "carrier", "cells": [[10,10],[10,11],[10,12],[10,13],[10,14]],
     "holed": [false,false,true,false,false], "sunk": false}
  ]},
  "your_shots": [[29,28,"hit"], [12,4,"miss"], [-3,19,"off_the_sea"]],
  "incoming":   [[10,12,"hit"]],
  "boosters":   {"flare": 1, "cluster": 6, "torpedo": 0, "teleport": 0},
  "lit_cells":  [[20,21],[20,22]],
  "last_action": {"fired": true, "landed": [29,28], "teleported": false}
}
```

Action:

```json
{"ship": "carrier", "dir": 135.0, "elev": 45.0, "power": 4, "booster": "cluster"}
```

- `ship` — one of your own ships, afloat when the tick began. `cells[0]` is its
  firing origin.
- `dir` — compass bearing 0–360. 0 is up the map, 90 right, 180 down.
- `elev` — 0–90. At 0 the shell lands on your own firing origin.
- `power` — whole number 1–5.
- `booster` — optional: `flare`, `cluster`, `torpedo`, `teleport`. Asking for one
  you do not hold is still valid; it goes off as a plain shell.

All four aim parts are required on every action, even one firing a booster that
fires no shell.

## Things that will bite you

**Nothing is repaired.** `365` is not read as `5`, and power `6` is not cut to
`5`. A missing, malformed, out-of-range, late or crashed action is a *silent
tick*: it fires nothing, and the referee never substitutes an action. Three
silent ticks in a row after the first five and the seat is disconnected.

**The deadline is real.** You get `config.action_deadline_ms` from when the state
is sent. The state goes out as soon as the previous tick resolves, so you have
the whole tick interval in wall-clock terms, but an answer later than the
deadline is dropped and counted as late.

**The wind is the game.** It is constant all battle and nobody tells you what it
is. `last_action.landed` gives the cell your previous shell actually reached;
compare it with the no-wind prediction, divide by the time in the air, and you
have it. `me_bot.py` does this in `WindEstimate` — about fifteen lines.

**You never name a target cell.** You name a ship, a bearing, an elevation and a
power. Working backwards from "I want to hit (20, 21)" to those four numbers is
`aim_at`, and allowing for the wind while doing it is the whole problem.

**Off-the-sea landings are reported** with their real out-of-bounds coordinates,
which is useful: they still measure the wind. Check bounds yourself.
