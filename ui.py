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
from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QColor, QPainter, QFont, QAction

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
    """Paints the Monopoly board around a central game area."""

    CELL = 128

    def __init__(self, board: Board, parent=None):
        super().__init__(parent)
        self.board = board
        self.setMinimumSize(720, 600)
        self.setStyleSheet("background: #f4f7f2; border: 1px solid #cad6cc;")

    def _grid(self) -> dict:
        # Board always exposes ``grid`` (tile index -> (row, col)).
        return self.board.grid

    def sizeHint(self) -> QSize:
        return QSize(960, 760)

    def set_game(self, game):
        """Store a game reference so a player token can be drawn per tile."""
        self.board_game = game
        self.update()

    def paintEvent(self, _event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        grid = self._grid()
        cols = max((c for _, c in grid.values() if isinstance(c, int)), default=0)
        rows = max((r for r, _ in grid.values() if isinstance(r, int)), default=0)
        cell_x = self.width() / (cols + 1) if (cols + 1) else self.width()
        cell_y = self.height() / (rows + 1) if (rows + 1) else self.height()
        cell = min(cell_x, cell_y)
        grid_w = (cols + 1) * cell
        grid_h = (rows + 1) * cell
        ox = (self.width() - grid_w) / 2
        oy = (self.height() - grid_h) / 2
        def pos(c, r):
            return ox + c * cell, oy + r * cell
        board_game = getattr(self, "board_game", None)
        active_position = None
        if board_game is not None and board_game.players:
            active_position = board_game._current_player().position
        for tile in self.board.tiles:
            r, c = grid.get(tile.tile, (0, 0))
            if not isinstance(r, int) or not isinstance(c, int):
                r, c = 0, tile.tile % 3
            x, y = pos(c, r)
            rect = QRect(int(x), int(y), int(cell), int(cell))
            qp.fillRect(rect, QColor(_CATEGORY_COLORS.get(tile.category.name, "#ffffff")))
            qp.setPen(QColor("#9aaba0"))
            qp.drawRect(rect)
            if tile.group:
                qp.fillRect(rect.adjusted(3, 3, -3, -int(cell * 0.76)), QColor(_GROUP_COLORS.get(tile.group, "#888888")))
            if tile.tile == active_position:
                qp.setPen(QColor("#147d68"))
                qp.drawRect(rect.adjusted(2, 2, -2, -2))
            size = max(8, int(cell * 0.105))
            qp.setFont(QFont("Microsoft JhengHei", size, QFont.Bold))
            qp.setPen(QColor("#1e3027"))
            qp.drawText(rect.adjusted(4, int(cell * 0.04), -4, -int(cell * 0.36)), Qt.AlignCenter | Qt.TextWordWrap, tile.name)
            qp.setFont(QFont("Segoe UI", max(7, size - 2)))
            details = f"¥{tile.price}" if tile.price else tile.category.self_name
            if tile.owner:
                details = f"{tile.owner} · {details}"
            qp.setPen(QColor("#516158"))
            qp.drawText(rect.adjusted(4, int(cell * 0.42), -4, -4), Qt.AlignCenter | Qt.TextWordWrap, details)

        center = QRect(int(ox + cell), int(oy + cell), int(grid_w - 2 * cell), int(grid_h - 2 * cell))
        qp.fillRect(center, QColor("#e4eee5"))
        qp.setPen(QColor("#b4c7b8"))
        qp.drawRect(center)
        qp.setPen(QColor("#176d5b"))
        qp.setFont(QFont("Microsoft JhengHei", max(18, int(cell * 0.34)), QFont.Bold))
        qp.drawText(center.adjusted(12, 20, -12, -center.height() // 2), Qt.AlignCenter, "大富翁")
        qp.setFont(QFont("Segoe UI", max(10, int(cell * 0.14))))
        subtitle = "开始一局，争夺城市与交通网络"
        if board_game is not None and board_game.players:
            current = board_game._current_player()
            subtitle = f"第 {board_game.turn} 回合  |  当前：{current.name}"
        qp.setPen(QColor("#496257"))
        qp.drawText(center.adjusted(12, center.height() // 2 - 4, -12, -18), Qt.AlignCenter, subtitle)

        if board_game is not None:
            board_tiles = board_game.board.tiles
            pcolor = ["#e53935", "#1e88e5", "#43a047", "#8e24aa"]
            for idx, pl in enumerate(board_game.players):
                tile = board_tiles[pl.position]
                r, c = grid.get(tile.tile, (0, 0))
                if not isinstance(r, int) or not isinstance(c, int):
                    r, c = 0, tile.tile % 3
                xc, yc = pos(c, r)
                radius = max(7, int(cell * 0.15))
                off = (idx % 2) * radius * 2 - radius
                ep = QRect(int(xc + cell / 2 - radius + off),
                           int(yc + cell * 0.72 - radius + (idx // 2) * radius * 2),
                           int(radius * 2), int(radius * 2))
                qp.setPen(QColor(pcolor[idx % len(pcolor)]))
                qp.setBrush(QColor(pcolor[idx % len(pcolor)]))
                qp.drawEllipse(ep)
        qp.end()


class LogPane(QTextBrowser):
    def __init__(self, game=None, parent=None):
        super().__init__(parent)
        self.game = game
        self.setOpenExternalLinks(False)
        self.setStyleSheet("QTextBrowser { background: #fbfcfa; border: 1px solid #d7e0d7; padding: 8px; font-size: 12px; }")

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


class PlayerPanel(QWidget):
    """One player's card on the left: 姓名/现金/地产数量/地产明细."""

    def __init__(self, player: Player, board: Board, is_human: bool, parent=None):
        super().__init__(parent)
        self.player = player
        self.board = board
        self.is_human = is_human
        self.setMinimumHeight(104)
        self.setStyleSheet("PlayerPanel { background: #ffffff; border: 1px solid #d5e0d6; border-radius: 6px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        title = QLabel(
            f"{player.name}" + ("  (你)" if is_human else "  (AI)")
        )
        title.setStyleSheet("QLabel { font-weight: bold; font-size: 13px; }")
        color = "#0a7" if is_human else "#555"
        title.setStyleSheet(f"QLabel {{ font-weight: bold; font-size: 13px; color: {color}; }}")
        layout.addWidget(title)
        self.info = QLabel("现金 ¥0 · 地产 0 块")
        layout.addWidget(self.info)
        self.props = QLabel("（暂无）")
        self.props.setWordWrap(True)
        self.props.setStyleSheet("QLabel { color: #555; font-size: 11px; }")
        layout.addWidget(self.props)
        layout.addStretch()
        self._label_widget = title

    def refresh(self) -> None:
        """Only updates text; card lives in the grid as a widget."""
        p = self.player
        tag = "破产" if p.bankrupt else ("在狱" if p.in_prison else "")
        names = [self.board.tiles[i].name for i in p.properties]
        self.info.setText(f"cash ¥{p.money} · 地产 {len(p.properties)} · {tag}")
        self.props.setText(" / ".join(names) if names else "（暂无）")


class MainWindow(QMainWindow):
    """Top-level window hosting board + controls + log."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("大富翁 (Richman 风格, PyQt6)")
        self.resize(1100, 760)
        self.game: Optional[game_engine.Game] = None
        self.human_index: int = 0
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
        central.setStyleSheet("QMainWindow { background: #eef3ee; } QLabel { color: #23362b; } QPushButton { background: #176d5b; color: white; border: 0; border-radius: 5px; padding: 9px 12px; font-weight: bold; } QPushButton:hover { background: #0f5b4b; } QPushButton:disabled { background: #a8bbb0; }")
        box = QHBoxLayout(central)
        box.setContentsMargins(16, 16, 16, 16)
        box.setSpacing(12)

        left = QFrame(); left.setMaximumWidth(250)
        left.setFrameShape(QFrame.StyledPanel)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        players_title = QLabel("玩家资产")
        players_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #176d5b;")
        left_layout.addWidget(players_title)
        self.players_grid = QGridLayout(left)
        left_layout.addLayout(self.players_grid)
        left_layout.addStretch()
        box.addWidget(left)

        self.board_view = BoardView(Board(34))
        box.addWidget(self.board_view, 3)

        controls = QFrame(); controls.setMaximumWidth(280)
        controls.setFrameShape(QFrame.StyledPanel)
        cb = QVBoxLayout(controls)
        title = QLabel("回合控制")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #176d5b;")
        cb.addWidget(title)
        self.status = QLabel("状态：等待新局")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("background: #e1eee5; padding: 8px; border-radius: 4px;")
        cb.addWidget(self.status)
        b1 = QPushButton("开始新游戏"); b1.clicked.connect(self.new_game); cb.addWidget(b1)
        b2 = QPushButton("掷骰并行动"); b2.clicked.connect(self.step); cb.addWidget(b2)
        self.buy_button = QPushButton("购买当前地产")
        self.buy_button.clicked.connect(self.buy_pending_asset)
        self.buy_button.setEnabled(False)
        cb.addWidget(self.buy_button)
        self.skip_buy_button = QPushButton("暂不购买")
        self.skip_buy_button.clicked.connect(self.decline_pending_asset)
        self.skip_buy_button.setEnabled(False)
        cb.addWidget(self.skip_buy_button)
        b3 = QPushButton("运行至你的回合"); b3.clicked.connect(self.run_bots); cb.addWidget(b3)
        b4 = QPushButton("模拟 30 回合"); b4.clicked.connect(lambda: self.run_bots(limit=30)); cb.addWidget(b4)
        log_title = QLabel("事件记录")
        log_title.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 12px;")
        cb.addWidget(log_title)
        self.log_pane = LogPane()
        self.log_pane.setMinimumHeight(190)
        cb.addWidget(self.log_pane, 1)
        cb.addStretch()
        box.addWidget(controls)

    def new_game(self):
        names = ["玩家1", "玩家2", "玩家3", "玩家4"]
        # 玩家 1 是你（手动），其余 3 个是 AI
        players = [Player(name, holds=3) for name in names]
        for i in range(1, len(players)):
            players[i].is_bot = True
        self.human_index = 0
        self.game = game_engine.Game(players, seed=1, auto_buy=False)
        self.game.start()
        self._sync_players()
        self.board_view.set_game(self.game)
        self.log_pane.game = self.game
        self.log_pane.refresh()
        self.status.setText(f"游戏开始 · {len(players)} 名玩家")
        self._refresh_purchase_controls()

    def _sync_players(self):
        for p in self._player_panels:
            p.setParent(None)
        self._player_panels = []
        for i, player in enumerate(self.game.players):
            panel = PlayerPanel(player, self.game.board, i == self.human_index, self.players_grid.parentWidget())
            self.players_grid.addWidget(panel, i, 0, 1, -1)
            self._player_panels.append(panel)

    def _is_human_turn(self) -> bool:
        return self.game is not None and self.game._current_player() is self.game.players[self.human_index]

    def _remaining(self) -> int:
        return sum(1 for p in self.game.players if not p.bankrupt)

    def _act_current(self) -> None:
        """Advance exactly one active player (roll, move, resolve, draw)."""
        if self.game.is_won():
            return
        p = self.game._current_player()
        if p is None or p.bankrupt:
            return
        self.game.run_step()
        self.board_view.update()

    def step(self):
        if not self.game:
            self.status.setText("请先开始游戏"); return
        if self._remaining() == 0:
            return
        if self.game.pending_purchase is not None:
            self.status.setText("请先决定是否购买当前地产")
            return
        if not self._is_human_turn():
            self.status.setText("请先运行 AI 至你的回合")
            return
        self.status.setText("你正在行动")
        self._act_current()
        self._after_step()

    def buy_pending_asset(self) -> None:
        if self.game and self.game.buy_pending_asset(self.game.players[self.human_index]):
            self.status.setText("购买完成，选择运行 AI 或继续查看棋盘")
        self._after_step()

    def decline_pending_asset(self) -> None:
        if self.game and self.game.decline_pending_asset(self.game.players[self.human_index]):
            self.status.setText("已放弃购买，选择运行 AI 继续")
        self._after_step()

    def run_bots(self, limit: int = 10000) -> None:
        if not self.game:
            self.status.setText("请先开始游戏")
            return
        if self.game.pending_purchase is not None:
            self.status.setText("请先决定是否购买当前地产")
            return
        self.status.setText("AI 行动中…")
        for _ in range(limit):
            if self.game.is_won() or self._remaining() == 0:
                break
            self.game.next_turn()
            current = self.game._current_player()
            if self._is_human_turn():
                break
            self._act_current()
            if self.game.pending_purchase is not None:
                self.game.buy_pending_asset(current)
        self._after_step()

    def _after_step(self):
        self.log_pane.refresh()
        for panel in self._player_panels:
            panel.refresh()
        if self.game and self.game.is_won():
            self.status.setText("游戏结束 · " + (self.game.winner.name or "") + " 获胜!")
        elif self.game and self.game.pending_purchase is not None:
            _, tile = self.game.pending_purchase
            self.status.setText(f"你到达 {tile.name}，售价 ¥{tile.price}")
        else:
            self.status.setText("轮到你行动")
        self._refresh_purchase_controls()

    def _refresh_purchase_controls(self) -> None:
        pending_for_human = (
            self.game is not None
            and self.game.pending_purchase is not None
            and self.game.pending_purchase[0] is self.game.players[self.human_index]
        )
        self.buy_button.setEnabled(pending_for_human)
        self.skip_buy_button.setEnabled(pending_for_human)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
