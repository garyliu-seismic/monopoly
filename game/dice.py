"""Dice.

A standard pair of d6 giving a proper (2..12) triangular distribution, plus
the ``Dice`` return type the engine consumes.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Dice:
    values: tuple[int, ...]

    @property
    def total(self) -> int:
        return sum(self.values)


def roll(n: int = 2, rng=None) -> Dice:
    """Standard d6 distribution for ``n`` dice (uses ``rng`` when given)."""
    rng = rng or random
    return Dice(tuple(rng.randint(1, 6) for _ in range(n)))


def roll_pair(rng=None) -> Dice:
    return roll(2, rng)
