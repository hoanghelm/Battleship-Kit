# Battleship — AI Hackathon Kit (turn-based)

Write a program that fights the computer on a grid: rows **A–I** down the side, columns
**1–9** across the top. Three shots a turn, nineteen cells to sink.

The game runs as a server. Your program connects over TCP, reads the board, and sends
back where to shoot.

```
Battleship-Turn-Kit/
├── Game/                     the game (Windows x64)
│   └── BattleshipTurn.exe
└── ai-client/
    ├── battleship_client.py  working Python client + sample bot
    └── README.md             full API reference
```

---

## Get something playing in two minutes

**1. Start the game**

```
Game\BattleshipTurn.exe
```

Leave it on the menu. The control port opens on **11000** as soon as the game launches —
the top right of the screen shows `CONTROL PORT 11000`.

**2. Run the sample bot** (needs Python 3.8+, no dependencies)

```bash
cd ai-client
python battleship_client.py
```

The game starts a match, places a fleet, and plays it out. The corner reads
**CONTROLLER LINKED** while your program is connected.

You never have to touch a menu or a button: your program's first command starts the game
and lays out the fleet, which is what makes unattended tournament runs possible.

**3. Make it yours**

Open `ai-client/battleship_client.py` and edit `DeductionBot`. Its `choose(state)` is
handed the board and returns three cells. Everything else is plumbing.

---

## Playing it yourself

The port does not get in the way of the mouse. Click **SINGLE PLAYER**, drag ships onto
the board or press **RANDOM**, then **CONTINUE**, and in battle click three cells and
press **FIRE**. Escape backs out.

A program and a person can watch the same game: run the bot and the board fills in on
screen as it plays, which is the quickest way to see whether a strategy is doing anything
sensible.

---

## What your program can do

| `Cmd` | Does |
|---|---|
| `185` | Read the board |
| `190` | Fire three shots |
| `191` | Start a new game, easy or hard |
| `192` | Speed the clock up, for testing |

Full field-by-field reference, the rules of this variant, and the strategy notes that
matter are in **[ai-client/README.md](ai-client/README.md)**.

---

Third-party code and art, and their licences, are listed in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
