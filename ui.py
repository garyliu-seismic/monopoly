"""PySide6 (PyQt6-compatible) frontend for the Monopoly game.

The UI is thin: all game logic lives in :mod:`monopoly.game.game.Game`,
which this window drives with ``start / next_turn / roll / advance``.

Widgets
-------
* ``BoardView``   : paints the 34-tile board + current positions
* ``LogPane``      : shows the ``(phase, text)`` log
* ``MainWindow``   : glues everything together with a menu + buttons
"""
from __future__ import annotations

import sys
from typing import List, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QTextBrowser, QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import Qt, QPoint, QSize, QRect
from PySide6.QtGui import QColor, QPainter, QBrush, QFont, QAction

from game import game as game_engine
from game.player import Player
from game.board import Board
from game.tile_types import TileType


# ------------------------------------------------------------------- styles
_CATEGORY_COLORS = {
    "GO": "#e8f5e9", "CHANCE": "#fff3e0", "COMMUNITY": "#fce4ec",
    "TAX": "#fbe9e7", "RAILROAD": "#efebe9", "UTILITY": "#e3f2fd",
    "PROPERTY": "#fffde7", "JAIL": "#eeeeee", "FREE": "#f1f8e9",
    "GANBANG": "#ede7f6", "PRISON": "#cfd8dc", "GO_JAIL": "#cfd8dc",
    "SPECIAL": "#fff8e1",
}
_GROUP_COLORS = {
    "brown": "#6d4c41", "lightblue": "#4fc3f7", "pink": "#ec407a",
    "orange": "#ffb300", "yellow": "#fdd835",
}


class BoardView(QWidget):
    """Paints the whole 3x12 board onto a single widget."""

    CELL = 128

    def __init__(self, board: Board, parent=None):
        super().__init__(parent)
        self.board = board

    def _grid(self) -> dict:
        if hasattr(self.board, "grid") and isinstance(self.board.grid, dict):
            return self.board.grid
        return self.board.tile_index  # fallback set in Game.setup

    def _fallback_grid(self) -> dict:
        return {t.tile: (t.tile // 3, t.tile % 3) for t in self.board.tiles}

    def sizeHint(self) -> QSize:
        cols = max((c for _, c in self._grid().values() if isinstance(c, int)), default=0)
        rows = max((r for r, _ in self._grid().values() if isinstance(r, int)), default=0)
        return QSize((cols + 1) * self.CELL, (rows + 1) * self.CELL)

    def paintEvent(self, _event):
        qp = QPainter(self)
        grid = self._grid()
        x_max = max((c for _, c in grid.values() if isinstance(grid.get(0), tuple and tuple)), default=0) if False else 3
        for tile in self.board.tiles:
            r, c = grid.get(tile.tile, (0, 0))
            if not isinstance(r, int) or not isinstance(c, int):
                r, c = 0, tile.tile % 3
            rx, ry = c * self.CELL, r * self.CELL
            rect = QRect(rx, ry, self.CELL, self.CELL)
            qp.fillRect(rect, QColor(_CATEGORY_COLORS.get(tile.category.name, "#ffffff")))
            qp.setPen(QColor("#333"))
            qp.drawRect(rect)
            qp.setFont(QFont("Segoe UI", 8))
            qp.drawText(rect, Qt.AlignCenter, f"{tile.name}\\n{tile.category.name}")
        qp.end()


class LogPane(QTextBrowser):
    def __init__(self, game=None, parent=None):
        super().__init__(parent)
        self.game = game

    def refresh(self):
        self.clear()
        if not self.game:
            return
        for phase, text in self.game.log:
            self.append(f"<b><font color={_phase_color(phase)}>[{phase}]</font></b> {text}")
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


def _phase_color(phase: str) -> str:
    palette = {
        "start": "#00897b", "roll": "#1e88e5", "起点": "#43a047",
        "buy": "#e53935", "tax": "#fb8c00", "rent": "#8e24aa",
    }
    return palette.get(phase, "#444444")


class PlayerPanel(QFrame):
    def __init__(self, player: Player, parent=None):
        super().__init__(parent)
        self.player = player
        self._label = QLabel(player.name + "  ¥ 0")
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)

    def refresh(self):
        p = self.player
        tag = "破产" if p.bankrupt else ("在狱" if p.in_prison else "")
        self._label.setText(f"{p.name}  ¥ {p.money} · 地产 {len(p.properties)} {tag}")


class MainWindow(QMainWindow):
    """Top-level window hosting board + controls + log."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("大富翁 (Richman 风格, PyQt6)")
        self.resize(1100, 760)
        self.game: Optional[game_engine.Game] = None
        self._player_panels: List[PlayerPanel] = []
        self._build_menu()
        self._build_body()

    def _build_menu(self):
        menubar = self.menuBar()
        menu = menubar.addMenu("游戏")
        a = QAction("新局", self); a.triggered.connect(self.new_game)
        menu.addAction(a)
        quit_action = QAction("退出", self); quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _build_body(self):
        central = QWidget(); self.setCentralWidget(central)
        box = QHBoxLayout(central)
        left = QWidget(); left.setMaximumWidth(240)
        self.players_grid = QGridLayout(left)
        box.addWidget(left)

        self.log_pane = LogPane()
        box.addWidget(self.log_pane, 1)

        self.board_view = BoardView(Board(34))
        box.addWidget(self.board_view, 1)

        controls = QWidget(); controls.setMaximumWidth(220)
        cb = QVBoxLayout(controls)
        self.status = QLabel("状态: 空闲"); cb.addWidget(self.status)
        b1 = QPushButton("开始游戏"); b1.clicked.connect(self.new_game); cb.addWidget(b1)
        b2 = QPushButton("执行一步"); b2.clicked.connect(self.step); cb.addWidget(b2)
        b3 = QPushButton("自动跑 30 步"); b3.clicked.connect(self.run_30); cb.addWidget(b3)
        cb.addStretch()
        box.addWidget(controls)

    def new_game(self):
        names = ["玩家1", "玩家2", "玩家3", "玩家4"]
        players = [Player(name, holds=3) for name in names]
        self.game = game_engine.Game(players, seed=1)
        self.game.start()
        self._sync_players()
        self.log_pane.game = self.game
        self.log_pane.refresh()
        self.status.setText(f"游戏开始 · {len(players)} 名玩家")

    def _sync_players(self):
        for p in self._player_panels:
            p.setParent(None)
        self._player_panels = []
        for player in self.game.players:
            panel = PlayerPanel(player)
            self.players_grid.addWidget(panel)
            self._player_panels.append(panel)

    def _run_step(self) -> bool:
        if self.game.is_won():
            return False
        self.game.next_turn()
        self.game.roll()
        p = self.game._current_player()
        total = sum(self.game._last_roll)
        self.game._land(p)
        self.game._check_bankrupt()
        self.game._detect_winner()
        return True

    def step(self):
        if not self.game:
            self.status.setText("请先开始游戏"); return
        if not self._run_step():
            return
        self._after_step()

    def run_30(self):
        if not self.game:
            self.status.setText("请先开始游戏"); return
        for _ in range(30):
            if not self._run_step():
                break
        self._after_step()

    def _after_step(self):
        self.log_pane.refresh()
        for panel in self._player_panels:
            panel.refresh()
        if self.game and self.game.is_won():
            self.status.setText("游戏结束 · " + (self.game.winner.name or "") + " 获胜!")
        else:
            self.status.setText("已完成一步")


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
