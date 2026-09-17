"""Event registry for the board.

An *event* is simply a named rule the engine knows how to execute. The board
lays them down (CHANCE/COMMUNITY/GANBANG tiles) as stacks of names; the
engine pulls one when a player lands and dispatches by name. Keeping the
registry tiny keeps the core decoupled and trivially testable.

Handlers receive ``(engine, player)`` and return a list of ``(phase, text)``
log entries (or ``None``).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# --- The named events + their short description strings --------------------
def _bank_lotto(e, p) -> List[Tuple[str, str]]:
    amt = 500
    p.add(amt)
    return [("银行", f"{p.name} 收到红包 +{amt}")]


def _tax_pay(e, p) -> List[Tuple[str, str]]:
    amt = 300
    paid = p.spend(amt)
    return [("税收", f"{p.name} 缴纳税收 -{paid}")]


def _jail_go(e, p) -> List[Tuple[str, str]]:
    p.in_prison = True
    p.jail_counter = 0
    p.jail_turn = -1
    return [("牢房", f"{p.name} 被关进监狱, 停留一轮")]


def _money_get(e, p) -> List[Tuple[str, str]]:
    amt = 400
    p.add(amt)
    return [("机会", f"{p.name} 机会卡: 获得 +{amt}")]


def _windfall(e, p) -> List[Tuple[str, str]]:
    amt = 800
    p.add(amt)
    return [("机会", f"{p.name} 意外之财，获得 +{amt}")]


def _house_fire(e, p) -> List[Tuple[str, str]]:
    amt = 600
    paid = p.spend(amt)
    return [("社区", f"{p.name} 房子失火，维修费 -{paid}")]


def _collect_all(e, p) -> List[Tuple[str, str]]:
    amt = 200
    entries: List[Tuple[str, str]] = []
    total = 0
    for other in e.players:
        if other is p or other.bankrupt:
            continue
        paid = other.spend(amt)
        if paid:
            p.add(paid)
            total += paid
    entries.append(("机会", f"{p.name} 向每位玩家收取 {amt}，共 +{total}"))
    return entries


def _pay_each(e, p) -> List[Tuple[str, str]]:
    amt = 200
    entries: List[Tuple[str, str]] = []
    total = 0
    for other in e.players:
        if other is p or other.bankrupt:
            continue
        paid = p.spend(amt)
        if paid:
            other.add(paid)
            total += paid
    entries.append(("社区", f"{p.name} 请客每位玩家 {amt}，共 -{total}"))
    return entries


# name -> handler(engine, player)
EVENTS: Dict[str, object] = {}


def _register(name: str, fn):
    EVENTS[name] = fn


_register("bank_lotto", _bank_lotto)
_register("tax_pay", _tax_pay)
_register("jail_go", _jail_go)
_register("money_get", _money_get)
_register("windfall", _windfall)
_register("house_fire", _house_fire)
_register("collect_all", _collect_all)
_register("pay_each", _pay_each)
