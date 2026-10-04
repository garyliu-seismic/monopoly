"""Regression: with several human players, Bank/Stock panels must follow the current player."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, monkeypatch):
    # Modal dialogs would block an offscreen run forever.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    import ui
    return ui.MainWindow()


@pytest.mark.parametrize("humans", [1, 2, 3, 5])
def test_panels_follow_current_human(window, humans):
    w = window
    w.human_count_combo.setCurrentIndex(w.human_count_combo.findData(humans))
    w.new_game()
    assert sum(1 for p in w.game.players if not p.is_bot) == humans
    assert len(w.game.players) == max(humans + 1, 4)

    seen = set()
    for _ in range(30):
        if w.game.is_won():
            break
        w.run_bots()
        if w.game.pending_purchase is not None:
            w.game.decline_pending_asset(w.game.pending_purchase[0])
            w._after_step()
        elif w._is_human_turn():
            w.step()
            i = w.game.players.index(w.game._current_player())
            assert not w.game.players[i].is_bot
            assert w.human_index == w.bank_panel.human_index == w.stock_panel.human_index == i
            seen.add(i)
    assert seen, "no human turn was reached"
