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


def roll(n: int = 2) -> Dice:
    """Standard d6 distribution for ``n`` dice."""
    return Dice(tuple(random.randint(1, 6) for _ in range(n)))


def roll_pair() -> Dice:
    return roll(2)
