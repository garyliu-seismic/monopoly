"""Money storage.

The player model uses *multiple* ``Wallet`` slots (sidecar wallets, as
requested). A player has up to ``holds`` parallel wallets; payment always
draws from the *first* (lowest ``wallet_id``) wallet that has cash. When a
wallet empties, cash cascades up the chain — a wallet is only vacated *whole*,
never partially (富翁 "整格钱包制").
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_MONEY = 2_000_000_000  # world ceiling per wallet; overflow never happens normally


@dataclass
class Wallet:
    wallet_id: int
    money_value: int = 0
    max_money_value: int = MAX_MONEY

    def has_funds(self) -> bool:
        return self.money_value > 0

    def set_money(self, value: int) -> None:
        """Set this wallet to ``value`` (used by tests / AI budget code)."""
        if value < 0:
            raise ValueError("money cannot be negative in a single wallet")
        self.money_value = value

    def add(self, n: int) -> None:
        if n < 0:
            raise ValueError("cannot add a negative amount")
        free = self.max_money_value - self.money_value
        self.money_value += min(n, free)

    def spend(self, amount: int) -> int:
        """Pay from this wallet; returns the amount actually paid (never > held)."""
        paid = min(amount, self.money_value)
        self.money_value -= paid
        return paid

    def transfer(self, amount: int, target: "Wallet") -> int:
        """Move *up to* ``amount`` from this wallet into ``target`` (whole-wallet friendly)."""
        if amount <= 0 or self.wallet_id == target.wallet_id:
            return 0
        move = min(amount, self.money_value)
        room = target.max_money_value - target.money_value
        if move <= room:
            self.money_value -= move
            target.money_value += move
        return move

    def can_pay(self, amount: int) -> bool:
        """True when this wallet holds at least ``amount`` cash."""
        return self.money_value >= amount

    def is_empty(self) -> bool:
        return self.money_value == 0

    # ------------------------------------------------------------ serialise
    def to_dict(self) -> dict:
        return {
            "wallet_id": self.wallet_id,
            "money_value": self.money_value,
            "max_money_value": self.max_money_value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        return cls(
            data["wallet_id"],
            data.get("money_value", 0),
            data.get("max_money_value", MAX_MONEY),
        )
