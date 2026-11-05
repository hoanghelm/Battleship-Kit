# Briefing for an AI assistant editing this bot

Read this before changing anything in this folder.

Claude Code picks this file up automatically. For another assistant, paste it in
or tell it to read `CLAUDE.md` first.

## What this is

This bot plays one seat in Battleship against a Unity referee. A team talks to
you in plain words; you are the only one who edits the code.

Three files, and **only one of them is yours to change**:

| File | Edit it? | What it is |
|---|---|---|
| `strategy.py` | **yes, this one** | `choose(sea) -> order`. The whole bot. |
| `bot_api.py` | no | Turns orders into bearings, elevations and powers. Wind maths. |
| `me_bot.py` | no | Socket transport. |

Make the change in `strategy.py`. If you think you need to touch the other two,
you have almost certainly misread the task — say so rather than editing them.

## The one function

```python
def choose(sea):
    return sea.fire_at((20, 21), skill="cluster")
```

`sea` carries everything known this turn. Orders are built by `sea.fire_at`,
`sea.torpedo_toward`, `sea.teleport`, `sea.fire_somewhere` and `sea.stand_down`.

**Never compute a bearing, elevation, power or wind correction in `strategy.py`.**
That is what `bot_api` is for. A strategy says *where* and *which skill*.

`sea.fire_at` returns `None` when the cell is out of range — always fall back to
`sea.fire_somewhere()`.

## Feedback from last turn

`sea.last_shot` answers "did that work?":

```
.aimed_at  .landed_at  .on_target  .drift
.results   .hit  .sank  .wasted
.skill_requested  .skill_fired  .skill_was_spent
```

`on_target` being False early is normal — the wind is still unknown. It should
become mostly True once `sea.wind_confidence` is past a dozen shots. If it never
does, the bot is firing shots too short to measure the wind from.

## The game, in one paragraph

Every fleet shares one 40×40 sea. You do **not** place your fleet and you do
**not** name a cell to fire at. You name one of your own ships, a compass
bearing, an elevation and a power, and a shell flies a parabola. **A hidden wind
pushes every shell**, it is the same all battle, and nobody tells you what it is.
Working it out from where your shells actually land is most of the game.

## Hard rules — breaking these fails the submission check

- Imports: Python standard library, NumPy, SciPy, NetworkX, sortedcontainers,
  the event's bot library, and your own files beside this one. **Nothing else.**
- No `secrets`, no OS random bytes. Use the random source the bot already has.
- No `eval`, no `exec`, no loading code at runtime.
- Do not shadow a library file name with your own module.
- 256 KB of code, total.
- Answer within `state["config"]["action_deadline_ms"]` (500 ms). A crash, a
  timeout, or a malformed action is a **silent tick**: it fires nothing. Three
  silent ticks in a row after the first five and the seat is disconnected.

**Nothing is repaired.** `dir` must be 0–360, `elev` 0–90, `power` a whole
number 1–5. `365` is not read as `5`. Power `6` is not cut to `5`. Either is an
invalid action, which fires nothing.

All four aim parts are required on every action, including one that fires a
booster which fires no shell.

## Four traps that have already bitten this code

Do not reintroduce these.

**Do not target the nearest untried cell.** The nearest water is the ring around
your own hull, so the bot spends the battle shelling the sea beside itself. The
search deliberately sweeps the middle of the sea first.

**Short lobs tell you nothing about the wind.** A one-cell shot is airborne about
0.4 s, the wind moves it under half a cell, and rounding erases it — average
those in and the estimate sits at zero. `WindEstimate.observe` ignores samples
with `t < 0.8`.

**A torpedo does not fly and a teleport fires nothing.** Their reported `landed`
is a stop cell, not a ballistic landing, and would poison the wind estimate.
`bot_api` guards this -- which is one reason to use `sea.torpedo_toward` rather
than hand-building an order.

**Aiming is backwards from what you want.** You know the cell you want to hit;
you need bearing, elevation and power that land there with the wind allowed for.
`sea.fire_at` does that for you. Do not reimplement it.

## The skills (boosters)

Bought before the battle, never by the bot. You fire one by naming it:
`"flare"`, `"cluster"`, `"torpedo"`, `"teleport"`. `state["boosters"]` says how
many are left. Asking for one you do not hold is still a **valid** action — it
goes off as a plain shell and nothing is spent — so spend them on judgement, not
on fear of an error.

- **Flare** — flies like a shell, lights a 7×7 square, reveals enemy cells that
  were unhit. Not a shot, never wasted. Its landing still measures the wind.
- **Cluster** — flies like a shell, then strikes up to 3 orthogonal neighbours.
- **Torpedo** — runs along the surface, no wind, sinks the first ship in line
  whole. It passes your own firing ship but stops on **any** other ship,
  including your own, which then shields everything beyond.
- **Teleport** — moves the named ship somewhere random and legal. Fires nothing.

## Changing behaviour

Most requests land in one of these:

| They want | Change |
|---|---|
| better searching | `_search` |
| better follow-up after a hit | `_next_to_a_hit` |
| when to spend a skill | `_booster` |
| better accuracy | `WindEstimate`, `aim_at` |
| which ship fires | `_ship` |

Leave `main`, `connect` and the socket handling alone unless asked — that is
transport, not strategy.

## How to check your change worked

```
Battleship.exe -extbot -bots 5 -medium -autostart
python -u me_bot.py
```

Watch the bot's own output. **Score should climb and the wind estimate should
converge** — the referee prints the true wind in the panel at the bottom right,
so you can compare directly:

```
tick  30  score   3  wind≈(+1.18, -0.83)  samples 13
tick  50  score  10  wind≈(+1.15, -0.78)  samples 33
```

A score stuck at 0 past tick 40, or a wind estimate stuck at `(0.00, 0.00)`,
means the bot is firing somewhere useless. Check what it is aiming at before
changing anything else.

The game's **SKILLS LEFT** panel shows whether the bot connected at all.
