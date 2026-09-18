"""Save / load the full game state as a human-readable JSON file.

The heavy lifting lives in ``Game.to_dict`` / ``Game.from_dict`` (in
``game.game``); this module only handles file I/O plus the deferred import
so it never creates a circular dependency with the engine.
"""
from __future__ import annotations

import json
import os


def save_game(game, path: str) -> str:
    """Serialise ``game`` to ``path`` (UTF-8 JSON) and return the path."""
    data = game.to_dict()
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_game(path: str):
    """Load a previously saved game back into a ``Game`` object."""
    from game.game import Game  # deferred import to avoid a cycle

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Game.from_dict(data)
