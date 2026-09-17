"""Entry point to launch the PyQt6 / PySide6 (Qt6) Monopoly UI.

Run from the project root::

    python -m monopoly      # if ``monopoly/`` is a package
    or
    python monopoly/monopoly.py

If the GUI cannot start (e.g. no display), see ``python -m monopoly.cli``
which runs a text-only simulation.
"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from ui import main as gui_main  # local ui module
    except Exception as exc:  # pragma: no cover - display issues
        print(f"Failed to start GUI ({exc}). Fall back to headless run.",
              file=sys.stderr)
        return _headless()
    return gui_main()


def _headless(steps: int = 80) -> int:
    from game import game as game_engine
    from game.player import Player
    players = [Player(f"BOT{i+1}", holds=2) for i in range(4)]
    g = game_engine.Game(players, seed=42, max_turns=2000)
    g.start()
    g.run(steps)
    print("Winner:", g.winner)
    for p in players:
        print(f"  {p.name}: cash={p.money} properties={len(p.properties)} "
              f"position={p.position} bankrupt={p.bankrupt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
