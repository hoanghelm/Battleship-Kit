# Battleship — AI Control API

Write a program that fights the computer on a **9×9** grid: rows **A–I** down the left,
columns **1–9** across the top, so the top-left cell is **A1**.

The game opens a TCP port at launch. Your program connects, reads the board, and sends
back three shots.

---

## Quick start

**1. Run the game**

```
Game\BattleshipTurn.exe
```

Leave it on screen. The control port opens on **11000** immediately — the bottom right
shows `CONTROL PORT 11000`, and `CONTROLLER LINKED` once your program connects.

**2. Run the sample bot** (Python 3.8+, no dependencies)

```bash
cd ai-client
python battleship_client.py
```

It starts a game, places a fleet, and plays to the end. Nothing to click.

**3. Make it yours**

Open `battleship_client.py` and edit `DeductionBot`. `choose(state)` is handed the board
and returns three `(row, column)` cells. Everything else is plumbing.

### How good is the sample bot?

Eight games per row, same build, measured not guessed:

| Opponent | Shooting at random | `DeductionBot` |
|---|---|---|
| Easy computer | 3/8 won, 25.2 turns | **8/8 won, 19.1 turns** |
| Hard computer | 1/8 won, 21.2 turns | **3/8 won, 15.8 turns** |

So it is well clear of random, and it still loses more often than it wins against the
hard computer — usually one cell short, 18 of 19. There is room to beat it.

Note that **who shoots first is decided by a coin toss**, and over a game that lasts
about sixteen turns a free turn is worth a lot. Judge a change over a run of games, not
over one.

---

## The rules that matter

This is not the Battleship you remember. Four things change how a bot must play.

**Three shots per turn, fired together.** A turn is exactly three cells — not one, not
two. You pick all three before you learn anything about any of them.

**Fixed shapes, fixed orientations.** Nineteen cells in six kinds of ship. The cruisers
and gunboats come in a horizontal *and* a vertical version, one of each, and they never
rotate — so there is no orientation to guess.

| Ship | Shape | Cells | How many |
|---|---|---|---|
| Admiral | `X·X` / `·X·` / `X·X` | 5 | 1 |
| Cruiser (vertical) | 1 wide, 3 tall | 3 | 1 |
| Cruiser (horizontal) | 3 wide, 1 tall | 3 | 1 |
| Gunboat (vertical) | 1 wide, 2 tall | 2 | 1 |
| Gunboat (horizontal) | 2 wide, 1 tall | 2 | 1 |
| Scout | single cell | 1 | 4 |

The Admiral is an **X**, not a line. Do not write a bot that only looks for straight hulls.

**Ships never touch**, not even diagonally — every ship sits inside a one-cell moat. Pin
a ship down and the whole ring around it is water for free.

**You are never told which shot hit.** The game reports how many enemy ship parts died on
each turn and *which kind of ship* they belonged to — not which of your three cells did
it. Three shots and one reported loss means one of those three hit, and you do not know
which. That last point is the whole game; see the strategy notes below.

Lose all nineteen of your own cells and you lose.

---

## Protocol

TCP, default port **11000**. Override with `BattleshipTurn.exe --ai-port 11001` to run
several copies side by side.

One request, one reply:

1. You send **one JSON object**.
2. The server replies with an **8-byte big-endian length**, then that many bytes of JSON.

| `Cmd` | Does | Fields |
|---|---|---|
| `185` | Read the board | — |
| `190` | Fire a turn | `Cells` `["C7","D2","E5"]`, or `Indexes` `[33,12,40]` |
| `191` | New game | `Level` 0 easy / 1 hard / −1 keep |
| `192` | Clock speed | `Rate` 0.1 to 20, 1 being normal |

```json
{ "Cmd": 190, "Cells": ["C7", "D2", "E5"] }
```

`185` answers from the last frame, so it is cheap to poll. `190` and `191` wait until the
game has actually applied them, so the reply already includes your shots.

`192` is there for testing: the computer's pause before it shoots is the only thing
between you and a few hundred games an hour. At `Rate` 15 a full game takes about two
seconds. Put it back to 1 before you watch.

### What a turn must look like

A fire command is rejected, with the reason in `lastError`, unless all of this holds:

- it is your turn (`canFire` is `1`)
- exactly `shotsPerTurn` cells — **three**
- every cell is on the board
- no cell is named twice
- no cell has been fired at before

Nothing is wasted silently: a rejected turn costs you nothing and the turn stays yours.

### Reply

```json
{
  "size": 9,
  "shotsPerTurn": 3,
  "gap": 1,
  "difficulty": "easy",
  "controllers": 1,
  "speed": 1,

  "phase": "battle",        // menu | waiting | place | battle | result | leave
  "turn": "player",         // player | enemy | none
  "currentTurn": 7,
  "canFire": 1,
  "gameOver": 0,
  "winner": "",             // player | enemy once finished

  "yourShots":  [[-1,-1,3,...], ...],   // 9 rows, row A first
  "enemyShots": [[...], ...],           // 9 rows, row A first

  "enemyFleetHits": [1,3,-1, ...],      // 19 slots
  "yourFleetHits":  [-1,-1, ...],       // 19 slots

  "enemyPartsHit": 5,
  "yourPartsHit": 2,
  "partsPerFleet": 19,

  "fleet": [
    { "ship": "Admiral", "cells": 5, "count": 1, "slots": [0, 4],
      "shape": [[0,0],[2,0],[1,1],[0,2],[2,2]] }
  ],

  "lastError": ""
}
```

**`yourShots[row][column]`** — `row` 0 is **A**, `column` 0 is **column 1**. The value is
`-1` if you have never fired there, otherwise the turn number on which you did.
`enemyShots` is the same for the computer's shots on your board.

**`enemyFleetHits`** — nineteen slots, one per enemy ship cell, grouped by ship. `-1`
means that cell is still afloat; any other number is the turn it was lost on. `fleet`
tells you which slots belong to which ship: `"slots": [0, 4]` means slots 0 to 4 are the
Admiral's five cells. Slots fill in order within a group, so four filled slots in the
Scouts' range means four dead scouts, and three filled slots in the Admiral's range means
an Admiral with three holes in it.

**`shape`** — `[column offset, row offset]` from the ship's own corner, with rows counting
*downwards*, the same way they are lettered. So the Admiral's
`[[0,0],[2,0],[1,1],[0,2],[2,2]]` is the X drawn in the table above.

`Indexes`, if you prefer raw cell numbers: a cell is `(size - 1 - row) * size + column`.
`Cells` is easier and matches what is written on screen.

---

## The loop you are writing

```python
from battleship_client import BattleshipClient

with BattleshipClient(port=11000) as client:
    client.new_game(level=1)              # 1 = the hard computer
    state = client.wait_until_ready()

    while not state["gameOver"]:
        shots = choose_three(state)        # <- your part
        state = client.fire(shots)
        state = client.wait_until_ready()  # the computer thinks for about a second

    print("Win" if state["winner"] == "player" else "Loss")
```

`wait_until_ready()` matters: the computer takes about **1 second** over its turn, and a
fire command sent while it is thinking is rejected with `not your turn`.

---

## Four things that decide a good bot

**The ship kind is the real prize.** `enemyFleetHits` tells you *which type* of ship lost
a part on which turn, and five of the six types there is only one of. For those, the
report is an exact equation rather than a hint: **the number of that ship's cells among a
turn's three shots equals the number of parts it lost that turn.** Enumerate the ship's
positions, throw away every one that disagrees with that equation on any past turn, and
what is left is usually a handful — often one. That single idea is what separates the
sample bot from random shooting, and it is worth more than any amount of heat-mapping.

**Forget parity.** In ordinary Battleship the shortest ship is two cells, so every ship
must cross a cell where `row + column` is even and you can search half the board. Not
here — four of the ships are **single-cell Scouts**, and parity misses them completely.

**A turn with no losses is your best news.** It proves all three of its cells are water.
Most turns hand you that, and three confirmed empty cells cut down the possible positions
of every ship at once. A turn with three losses proves the opposite just as firmly.
Anything in between is suspicion, not knowledge — weight those cells, do not trust them.

**Spread while hunting, cluster once you are onto something.** Three misses in one corner
teach you almost nothing; three misses spread across the board rule out a great deal. But
once a ship is cornered into a few positions, put all three shots on the cells those
positions disagree about — that both kills it and settles where it was.

---

## Writing it in another language

Nothing here is Python-specific. Any language with a socket will do:

```
connect 127.0.0.1:11000
loop:
    send  {"Cmd":190,"Cells":["C7","D2","E5"]}
    read  8 bytes        -> payload length, big-endian uint64
    read  <length> bytes -> UTF-8 JSON
```

---

## Current limits

- **Fleets are placed at random** for both sides. Choosing your own layout is not exposed
  over the port yet, so you cannot play defence.
- **Your own ship positions are not in the feed.** You can see where the computer has
  fired at you and how much of your fleet is left, which is all a bot needs to know how
  the race is going.
- **No screenshot command.** The feed is complete for a turn-based game; there is nothing
  vision would add.
- **Windows x64 only.**
