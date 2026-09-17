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


def _new_wallets(held: int, start: int = 15_000) -> List[Wallet]:
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
    stocks: Dict[str, int] = field(default_factory=dict)
    bankrupt: bool = False
    bail: bool = False
    in_prison: bool = False
    jail_counter: int = 0
    jail_turn: int = 0
    position: int = 0
    initial_money: int = 0
    bank: int = 0
    loan: int = 0
    loan_age: int = 0
    wallets: List[Wallet] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.wallets) < self.holds:
            self.wallets = _new_wallets(self.holds)
        if self.initial_money <= 0:
            self.initial_money = sum(w.money_value for w in self.wallets)

    # --------------------------------------------------------------- money
    @property
    def money(self) -> int:
        """Total cash across all wallets."""
        return sum(w.money_value for w in self.wallets)

    @property
    def cash_balance(self) -> int:
        return self.money  # single alias in the MVP

    def can_pay(self, amount: int) -> bool:
        """True when this player's cash covers ``amount``."""
        return self.money >= amount

    def set_money(self, amount: int) -> None:
        """Set total cash (spread across wallets); used by tests/AI."""
        if amount <= 0:
            for w in self.wallets:
                w.money_value = 0
            return
        base, rem = divmod(amount, len(self.wallets))
        for i, w in enumerate(self.wallets):
            w.money_value = base + (rem if i == 0 else 0)

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

    # ------------------------------------------------------------ serialise
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "is_bot": self.is_bot,
            "holds": self.holds,
            "properties": list(self.properties),
            "houses": {str(k): v for k, v in self.houses.items()},
            "stocks": dict(self.stocks),
            "bankrupt": self.bankrupt,
            "bail": self.bail,
            "in_prison": self.in_prison,
            "jail_counter": self.jail_counter,
            "jail_turn": self.jail_turn,
            "position": self.position,
            "initial_money": self.initial_money,
            "bank": self.bank,
            "loan": self.loan,
            "loan_age": self.loan_age,
            "wallets": [w.to_dict() for w in self.wallets],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        p = cls(
            name=data["name"],
            is_bot=data.get("is_bot", False),
            holds=data.get("holds", 2),
            properties=list(data.get("properties", [])),
            houses={int(k): v for k, v in data.get("houses", {}).items()},
            bankrupt=data.get("bankrupt", False),
            bail=data.get("bail", False),
            in_prison=data.get("in_prison", False),
            jail_counter=data.get("jail_counter", 0),
            jail_turn=data.get("jail_turn", 0),
            position=data.get("position", 0),
            initial_money=data.get("initial_money", 0),
        )
        p.stocks = {str(k): int(v) for k, v in data.get("stocks", {}).items()}
        p.wallets = [Wallet.from_dict(w) for w in data.get("wallets", [])]
        p.bank = int(data.get("bank", 0))
        p.loan = int(data.get("loan", 0))
        p.loan_age = int(data.get("loan_age", 0))
        if p.initial_money <= 0:
            p.initial_money = sum(w.money_value for w in p.wallets)
        return p


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
