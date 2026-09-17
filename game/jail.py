"""Jail (牢房 / 监狱) rules.

Pure rule logic so it stays unit-testable without the engine. The engine
(``game.game``) owns the RNG, logging and money movement; this module only
decides *transitions* of jail state.

Rules (大富翁-flavoured)::

    * Rolling doubles frees you immediately and, like any doubles, lets you
      re-roll the same turn for a free move.
    * Each consecutive turn spent in jail with no doubles adds one day.
    * After 3 days (without having freed yourself) you are forced to pay a
      bail fee (``BAIL_COST``) to leave. Paying out this way costs the fee but
      does **not** award the GO bonus.
    * If you cannot afford the bail fee you simply wait one more day.
"""
from __future__ import annotations

from typing import Tuple


BAIL_COST = 1000
JAIL_MAX_TURNS = 3


def is_double(values: Tuple[int, int]) -> bool:
    """Return True only for a genuine pair of dice (e.g. ``(6, 6)``)."""
    return len(values) == 2 and values[0] == values[1]
