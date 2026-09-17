"""Banking rules for the Monopoly game: deposits, interest and loans.

Every turn (each ``next_turn``) the engine settles interest:
* deposits earn ``DEPOSIT_RATE`` per turn (1%)
* loans accrue ``LOAN_RATE`` per turn (2%), rolled into the balance

A player may borrow up to ``LOAN_LIMIT`` in total. Purely logical — no GUI.
"""
from __future__ import annotations

DEPOSIT_RATE = 0.01   # 每回合存款利率 1%
LOAN_RATE = 0.02      # 每回合贷款利率 2%
LOAN_LIMIT = 10000    # 单玩家贷款上限


def deposit_interest(deposit: int) -> int:
    """Interest earned on a deposit balance for one turn."""
    return int(deposit * DEPOSIT_RATE)


def loan_interest(loan: int) -> int:
    """Interest accrued on a loan balance for one turn."""
    return int(loan * LOAN_RATE)
