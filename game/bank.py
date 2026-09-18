"""Banking rules for the Monopoly game: deposits, interest and loans.

Interest settles once per lap — whenever a player passes GO — which mirrors
the classic board-game bank. Deposits earn ``DEPOSIT_RATE`` per lap; loans
accrue ``LOAN_RATE`` per lap, doubling to ``OVERDUE_RATE`` once a loan has
stayed outstanding for ``LOAN_OVERDUE_TURNS`` laps without any repayment.

A player may borrow up to ``LOAN_LIMIT`` in total. Purely logical — no GUI.
"""
from __future__ import annotations

DEPOSIT_RATE = 0.05   # 每圈（经过起点）存款利率 5%
LOAN_RATE = 0.10      # 每圈（经过起点）贷款利率 10%
OVERDUE_RATE = 0.20   # 逾期贷款利率（连续 LOAN_OVERDUE_TURNS 圈未还）
LOAN_OVERDUE_TURNS = 3
LOAN_LIMIT = 10000    # 单玩家贷款上限


def deposit_interest(deposit: int) -> int:
    """Interest earned on a deposit balance for one lap."""
    return int(deposit * DEPOSIT_RATE)


def loan_interest(loan: int, overdue: bool = False) -> int:
    """Interest accrued on a loan balance for one lap."""
    rate = OVERDUE_RATE if overdue else LOAN_RATE
    return int(loan * rate)
