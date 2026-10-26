# Third-Party Notices

## Battleship (muk)

This game is a fork of the open-source **Battleship** project by *muk*
(<https://github.com/mehmetukut/Battleship>, also published as "Amiral" on itch.io). Its
client code, tile art, scene structure and computer opponent are the basis of this build.

Licensed under the MIT License, reproduced in full below.

```
MIT License

Copyright (c) 2021 muk

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### What this fork changed

- An external control port (`Assets/Scripts/AI/AiServer.cs`, `AiBridge.cs`,
  `AiCommand.cs`) so a program can play the game over TCP.
- Coordinate labels around the boards (`Assets/Scripts/UI/GridCoordinateLabels.cs`).
- Three fixes to the original code: the computer opponent stopped taking turns in any
  game after the first, its hard setting could leave a match waiting forever on a move
  it never made, and a turn it returned short of three shots was discarded in silence.

## Colyseus

Networking uses [Colyseus 0.13](https://github.com/colyseus/colyseus), MIT licensed.
`Assets/Plugins/FossilDelta/` carries its own LICENSE file.

## Space UI Pack

`Assets/Sprites/uipackSpace_sheet.png` — see `Assets/Sprites/uipackSpace_license.txt`
for its terms.

## TextMesh Pro

Bundled with Unity. The Bangers and Roboto fonts under `Assets/TextMesh Pro/` carry
their own licence files alongside them.
