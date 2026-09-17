"""Money storage.

The player model uses *multiple* ``Wallet`` slots (sidecar wallets, as
requested). A player has up to ``holds`` parallel wallets. Payment always
draws from the *first* (lowest wallet_id) wallet that has cash; a wallet is
only moved *whole* up the chain. The default ``max_money_value`` is the
world cap so overflow never happens in a normal game.
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_MONEY = 2_000_000_000  # world ceiling per wallet


@dataclass
class Wallet:
    wallet_id: int
    money_value: int = 0
    max_money_value: int = MAX_MONEY

    def has_funds(self) -> bool:
        return self.money_value > 0

    def set_money(self, value: int) -> None:
        if value < 0:
            raise ValueError("money cannot be negative in a single wallet")
        self.money_value = value

    def add(self, n: int) -> None:
        if n < 0:
            raise ValueError("cannot add a negative amount")
        free = self.max_money_value - self.money_value
        self.money_value += min(n, free)

    def spend(self, amount: int) -> int:
        """Return the amount actually paid from this wallet (no negative)."""
        paid = min(amount, self.money_value)
        self.money_value -= paid
        return paid

    def transfer(self, amount: int, target: "Wallet") -> int:
        """Move up to ``amount`` into ``target`` (whole-wallet friendly)."""
        if amount <= 0 or self.wallet_id == target.wallet_id:
            return 0
        move = min(amount, self.money_value)
        room = target.max_money_value - target.money_value
        if move <= room:
            self.money_value -= move
            target.money_value += move
        return move

    def is_empty(self) -> bool:
        return self.money_value == 0
