"""Player data model.

A Player holds up to ``holds`` parallel ``Wallet`` slots (sidecar wallets, a
富翁-flavoured detail), plus board position, owned properties, houses and
jail / bail state. Pure data — no GUI — so it's trivially serialisable and
unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .money import Wallet


def _new_wallets(held: int, start: int = 1_800) -> List[Wallet]:
    """Split ``start`` cash fairly across ``held`` wallets."""
    held = max(1, held)
    base, rem = divmod(start, held)
    return [Wallet(i, base + (rem if i == 0 else 0)) for i in range(held)]


@dataclass
class Player:
    name: str
    is_bot: bool = False
    holds: int = 2
    properties: List[int] = field(default_factory=list)
    houses: Dict[int, int] = field(default_factory=dict)
    bankrupt: bool = False
    bail: bool = False
    in_prison: bool = False
    jail_counter: int = 0
    jail_turn: int = 0
    position: int = 0
    wallets: List[Wallet] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.wallets) < self.holds:
            self.wallets = _new_wallets(self.holds)

    # --------------------------------------------------------------- money
    @property
    def money(self) -> int:
        """Total cash across all wallets."""
        return sum(w.money_value for w in self.wallets)

    @property
    def cash_balance(self) -> int:
        return self.money  # single alias in the MVP

    def first_wallet_with(self) -> Wallet | None:
        return next((w for w in self.wallets if w.money_value > 0), None)

    def add(self, amount: int) -> bool:
        """Add ``amount`` to the first wallet that has cash; fails if none do."""
        if amount <= 0:
            return False
        w = self.first_wallet_with()
        if w is None:
            return False
        w.add(amount)
        return True

    def pay(self, amount: int) -> int:
        """Deduct up to ``amount`` from cash; returns the amount actually paid."""
        return self.spend(amount)

    def spend(self, amount: int) -> int:
        """Pay up to ``amount`` using the 富翁 whole-wallet rule.

        Spends first wallet, then moves up the chain until the whole amount
        (or all available cash) is drained.
        """
        if amount <= 0:
            return 0
        remaining = amount
        for w in self.wallets:
            if w.money_value <= 0:
                continue
            paid = w.spend(remaining)
            remaining -= paid
            if remaining <= 0:
                break
        paid_total = amount - remaining
        return paid_total

    def transfer(self, target: "Player", amount: int) -> bool:
        """Move cash (whole wallets) from self to target."""
        if amount <= 0:
            return False
        w = self.first_wallet_with()
        if w is None:
            return False
        t = next((x for x in target.wallets if x.money_value > 0), None)
        if t is None:
            t = target.wallets[0]
        moved = w.transfer(amount, t)
        return moved > 0

    def net_wealth(self) -> int:
        """Cash + value of owned properties (property value ~ 0 in MVP)."""
        return self.money + sum(self.properties)

    def is_bankrupt(self) -> bool:
        return self.wallets and all(w.money_value == 0 for w in self.wallets)

    def _owns_group(self, engine, tile) -> bool:
        """True if *only* this player owns a colour group of ``tile``."""
        for other in engine.players:
            if other is self:
                continue
            for pid in other.properties:
                if (0 <= pid < len(engine.board.tiles)) and (board_tile := engine.board.tiles[pid]) is not None:
                    if board_tile.group == tile.group:
                        return False
        return len(self.properties) > 0


    def get_max_wallets(self) -> int:
        return len(self.wallets)

    def get_wallets(self) -> List[Wallet]:
        return self.wallets

    def get_wallet_ids(self) -> List[int]:
        return list(range(len(self.wallets)))


def player_from_dict(d: dict) -> "Player":
    return Player(
        name=d["name"],
        holds=d.get("holds", 2),
        properties=list(d.get("properties", [])),
        houses=dict(d.get("houses", {})),
        bail=d.get("bail", False),
        in_prison=d.get("in_prison", False),
        position=d.get("position", 0),
    )
