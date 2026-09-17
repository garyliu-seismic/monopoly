"""Event registry for the board.

An *event* is simply a named rule the engine knows how to execute. The board
lays them down (CHANCE/COMMUNITY/GANBANG tiles) as stacks of names; the
engine pulls one when a player lands and dispatches by name. Keeping the
registry tiny keeps the core decoupled and trivially testable.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# A "draw token" is (owner_tile_index, name). When any draw happens we pull a
# random token that belongs to that tile.
Event = None

# --- The named events + their short description strings --------------------
def _bank_lotto(e, p) -> List[Tuple[str, str]]:
    amt = 500
    p.add(amt)
    return [("银行", f"{p.name} 收到红包 +{amt}")]


def _tax_pay(e, p) -> List[Tuple[str, str]]:
    amt = 300
    p.spend(amt)
    return [("税收", f"{p.name} 缴纳税收 -{amt}")]


def _jail_go(e, p) -> List[Tuple[str, str]]:
    p.in_prison = True
    p.jail_counter = 0
    p.jail_turn = -1
    return [("牢房", f"{p.name} 被关进监狱, 停留一轮")]


def _money_get(e, p) -> List[Tuple[str, str]]:
    amt = 400
    p.add(amt)
    return [("机会", f"{p.name} 机会卡: 获得 +{amt}")]


# name -> handler(engine, player)
EVENTS: Dict[str, object] = {}


def _register(name: str, fn):
    EVENTS[name] = fn


_register("bank_lotto", _bank_lotto)
_register("tax_pay", _tax_pay)
_register("jail_go", _jail_go)
_register("money_get", _money_get)
