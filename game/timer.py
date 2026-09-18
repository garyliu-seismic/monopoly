"""Per-round turn timer (pure logic, testable without a QApplication).

Kept here so the "a turn that exceeds its time limit auto-runs" rule can be
unit-tested in isolation; the UI maps the timer onto a ``QProgressBar`` in a
richman-style turn countdown.

Counts tenths of a second internally to avoid float drift; exposes seconds to
humans.
"""
from __future__ import annotations


class TurnTimer:
    """A single-countdown timer for one player's turn.

    Parameters
    ----------
    name:
        Label shown in the UI (usually the active player's name).
    base_seconds:
        The full budget for a turn, e.g. ``20``.
    """

    def __init__(self, name: str = "", base_seconds: int = 20) -> None:
        self.name = name
        self.base_seconds = max(1, int(base_seconds))
        self._tenths = 0  # seconds * 10
        self.active = False

    # -------------------------------------------------------------- helpers
    def _base_tenths(self) -> int:
        return self.base_seconds * 10

    # ----------------------------------------------------------- lifecycle
    def start(self) -> "TurnTimer":
        """(Re)arm for a fresh turn."""
        self._tenths = 0
        self.active = True
        return self

    def stop(self) -> "TurnTimer":
        """Pause or end the countdown (e.g. turn passed to the next player)."""
        self.active = False
        return self

    def reset(self) -> "TurnTimer":
        self.stop()
        self._tenths = 0
        return self

    # ------------------------------------------------------------- clock
    def tick(self, dt_ms: int) -> None:
        """Advance the clock by ``dt_ms``; clamps at the base and de-arms."""
        if not self.active or dt_ms <= 0:
            return
        self._tenths = min(self._base_tenths(), self._tenths + int(dt_ms / 100))
        if self._tenths >= self._base_tenths():
            self.active = False

    def passed(self) -> bool:
        """True once the whole base budget has been consumed."""
        return self.active is False and self._tenths >= self._base_tenths()

    def remaining_ms(self) -> int:
        """Milliseconds left (never negative)."""
        base = self._base_tenths() * 100
        return max(0, base - self._tenths * 100)

    def to_seconds(self) -> int:
        """Elapsed whole seconds (clamped at the base)."""
        return max(0, min(self.base_seconds, self._tenths // 10))
