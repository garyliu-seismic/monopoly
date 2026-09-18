"""Stock market for the Monopoly game.

A tiny exchange with a handful of ticker symbols whose prices random-walk
each turn. Players buy/sell shares against cash; holdings are tracked on
the ``Player`` model. Everything here is pure logic and serialisable so it
round-trips through save/load.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional

from .serial import rng_from_json, rng_to_json


@dataclass
class Stock:
    code: str
    name: str
    price: int


class StockMarket:
    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.stocks: List[Stock] = [
            Stock("TECH", "科技股", 500),
            Stock("BANK", "银行股", 400),
            Stock("ENERGY", "能源股", 300),
            Stock("REAL", "地产股", 600),
        ]

    def get(self, code: str) -> Optional[Stock]:
        for s in self.stocks:
            if s.code == code:
                return s
        return None

    def tick(self) -> None:
        """Random-walk every price once per turn (floor at 5)."""
        for s in self.stocks:
            s.price = max(50, s.price + self.rng.randint(-50, 50))

    def to_dict(self) -> dict:
        return {
            "stocks": [
                {"code": s.code, "name": s.name, "price": s.price}
                for s in self.stocks
            ],
            "rng_state": rng_to_json(self.rng),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StockMarket":
        m = cls()
        m.stocks = [Stock(s["code"], s["name"], s["price"]) for s in data["stocks"]]
        rng_from_json(m.rng, data["rng_state"])
        return m
