# Battleship — AI Hackathon Kits

Two games, two very different problems to write a program for. Both run as a server on
**TCP port 11000**: your program connects, reads the state, and sends back orders. Both
ship with a working Python client and a sample bot you can gut and replace.

Pick whichever suits the team — they are independent, and nothing is shared between them.

| | [**turn-based**](turn-based/) | [**arcade**](arcade/) |
|---|---|---|
| What you write | where to shoot | how to fly and when to fire |
| Pace | one turn at a time, think as long as you like | 60 decisions a second |
| The hard part | working out where ships are from almost no feedback | leading a moving target, dodging what is coming back |
| Good for | search, deduction, probability | control loops, geometry, reflexes |

---

## [turn-based/](turn-based/) — Battleship on a 9×9 grid

Rows **A–I** down the side, columns **1–9** across the top. Three shots a turn, nineteen
cells to sink, against a computer opponent that is genuinely hard to beat.

What makes it interesting: **the game never tells you which of your three shots hit.** It
reports how many ship parts died that turn and *which kind of ship* they belonged to. For
the five one-of-a-kind ships that is an exact equation rather than a hint, so a good bot
deletes impossible positions instead of guessing.

```
turn-based\Game\BattleshipTurn.exe
cd turn-based\ai-client && python battleship_client.py
```

The sample bot wins 8/8 against the easy computer and 3/8 against the hard one, where
shooting at random wins 3/8 and 1/8. There is room to beat it.

Full API and strategy notes: **[turn-based/ai-client/README.md](turn-based/ai-client/README.md)**

---

## [arcade/](arcade/) — real-time naval combat

You command one warship with a throttle, a rudder and a turret, against waves of
attackers. Shells travel at a finite speed, so you have to aim where the target is going
to be, and so does everything shooting at you.

```
arcade\Game\BattleShip.exe
cd arcade\ai-client && python battleship_client.py
```

Full API and strategy notes: **[arcade/ai-client/README.md](arcade/ai-client/README.md)**

---

## Both work the same way

```
connect 127.0.0.1:11000
loop:
    send  one JSON object
    read  8 bytes        -> payload length, big-endian uint64
    read  <length> bytes -> UTF-8 JSON
```

Nothing is Python-specific; any language with a socket will do. Run several copies side
by side with `--ai-port 11001`.

Windows x64. Licences for the code and art each kit builds on are in its own
`THIRD-PARTY-NOTICES.md`.
