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
from PySide6.QtCore import Qt, QPoint, QSize, QRect, QTimer
from PySide6.QtGui import QColor, QPainter, QFont, QAction, QPen

from game import game as game_engine
from game.player import Player
from game.board import Board
from game.tile_types import TileType

import sound


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
PLAYER_COLORS = ["#e53935", "#1e88e5", "#43a047", "#8e24aa"]
PLAYER_AVATARS = ["🧑", "🤖", "👽", "👻"]


class BoardView(QWidget):
    """Paints the Monopoly board around a central game area."""

    CELL = 128

    def __init__(self, board: Board, parent=None):
        super().__init__(parent)
        self.board = board
        self.setMinimumSize(720, 600)
        self.setStyleSheet("background: #f4f7f2; border: 1px solid #cad6cc;")
        self._animation_queue = []
        self._active_animation = None
        self._display_positions = {}
        self._move_timer = QTimer(self)
        self._move_timer.setInterval(115)
        self._move_timer.timeout.connect(self._advance_animation)

    def _grid(self) -> dict:
        # Board always exposes ``grid`` (tile index -> (row, col)).
        return self.board.grid

    def sizeHint(self) -> QSize:
        return QSize(960, 760)

    def set_game(self, game):
        """Store a game reference so a player token can be drawn per tile."""
        self.board_game = game
        self._animation_queue.clear()
        self._active_animation = None
        self._display_positions.clear()
        self._move_timer.stop()
        self.update()

    def animate_move(self, player_index: int, before: int, after: int) -> None:
        """Show a token walking each board space while game state resolves immediately."""
        steps = (after - before) % len(self.board.tiles)
        if not steps:
            return
        path = [(before + offset) % len(self.board.tiles) for offset in range(1, steps + 1)]
        self._animation_queue.append((player_index, path))
        if self._active_animation is None:
            self._start_next_animation()

    def _start_next_animation(self) -> None:
        if not self._animation_queue:
            self._active_animation = None
            return
        player_index, path = self._animation_queue.pop(0)
        self._active_animation = (player_index, path, 0)
        self._move_timer.start()

    def _advance_animation(self) -> None:
        player_index, path, step = self._active_animation
        self._display_positions[player_index] = path[step]
        sound.play("move")
        self.update()
        if step + 1 == len(path):
            self._display_positions.pop(player_index, None)
            self._move_timer.stop()
            self._active_animation = None
            self._start_next_animation()
            return
        self._active_animation = (player_index, path, step + 1)

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
            if tile.house:
                band = rect.adjusted(3, 3, -3, -int(cell * 0.76))
                n = min(tile.house, 4)
                bw = band.width() / 5
                qp.setPen(Qt.NoPen)
                qp.setBrush(QColor("#ffffff"))
                for k in range(n):
                    qp.drawRect(
                        band.left() + int(bw * (k + 1)) - int(bw * 0.35),
                        band.top() + int(band.height() * 0.22),
                        int(bw * 0.7),
                        int(band.height() * 0.56),
                    )
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
            for idx, pl in enumerate(board_game.players):
                if pl.bankrupt:
                    continue
                display_position = self._display_positions.get(idx, pl.position)
                tile = board_tiles[display_position]
                r, c = grid.get(tile.tile, (0, 0))
                if not isinstance(r, int) or not isinstance(c, int):
                    r, c = 0, tile.tile % 3
                xc, yc = pos(c, r)
                token_r = max(9, int(cell * 0.14))
                cx = int(xc + cell * (0.28 + (idx % 2) * 0.30))
                cy = int(yc + cell * (0.60 + (idx // 2) * 0.18))
                color = QColor(PLAYER_COLORS[idx % len(PLAYER_COLORS)])
                qp.setBrush(color)
                qp.setPen(QPen(QColor("#ffffff"), 2))
                qp.drawEllipse(cx - token_r, cy - token_r, token_r * 2, token_r * 2)
                emoji = PLAYER_AVATARS[idx % len(PLAYER_AVATARS)]
                qp.setFont(QFont("Segoe UI Emoji", token_r))
                qp.drawText(
                    QRect(cx - token_r, cy - token_r, token_r * 2, token_r * 2),
                    Qt.AlignCenter,
                    emoji,
                )
        qp.end()


class DiceView(QWidget):
    """Shows the two dice with pips, refreshed after each roll."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = (1, 6)
        self.setFixedHeight(60)

    def set_values(self, values) -> None:
        self.values = tuple(values)
        self.update()

    def paintEvent(self, _event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        total_w = self.width()
        die = max(24, min(total_w // 2 - 10, 48))
        gap = 12
        start_x = (total_w - (die * 2 + gap)) // 2
        y = (self.height() - die) // 2
        for i, v in enumerate(self.values):
            rect = QRect(start_x + i * (die + gap), y, die, die)
            qp.setBrush(QColor("#ffffff"))
            qp.setPen(QPen(QColor("#176d5b"), 2))
            qp.drawRoundedRect(rect, 8, 8)
            self._draw_pips(qp, rect, v)
        qp.end()

    @staticmethod
    def _pip_layout(v):
        return {
            1: [(0.5, 0.5)],
            2: [(0.28, 0.28), (0.72, 0.72)],
            3: [(0.28, 0.28), (0.5, 0.5), (0.72, 0.72)],
            4: [(0.28, 0.28), (0.72, 0.28), (0.28, 0.72), (0.72, 0.72)],
            5: [(0.28, 0.28), (0.72, 0.28), (0.5, 0.5), (0.28, 0.72), (0.72, 0.72)],
            6: [(0.28, 0.28), (0.72, 0.28), (0.28, 0.5), (0.72, 0.5), (0.28, 0.72), (0.72, 0.72)],
        }[v]

    def _draw_pips(self, qp, rect, v):
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor("#176d5b"))
        r = max(2, rect.width() * 0.09)
        for fx, fy in self._pip_layout(v):
            cx = rect.left() + rect.width() * fx
            cy = rect.top() + rect.height() * fy
            qp.drawEllipse(QPoint(cx, cy), r, r)


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

    def __init__(self, player: Player, board: Board, is_human: bool, parent=None,
                 avatar: str = "🧑", color: str = "#555"):
        super().__init__(parent)
        self.player = player
        self.board = board
        self.is_human = is_human
        self.avatar = avatar
        self.setMinimumHeight(104)
        self.setStyleSheet("PlayerPanel { background: #ffffff; border: 1px solid #d5e0d6; border-radius: 6px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        title = QLabel(
            f"{avatar}  {player.name}" + ("  (你)" if is_human else "  (AI)")
        )
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
        self._played_log_count = 0
        self._build_menu()
        self._build_body()

    def _build_menu(self):
        menubar = self.menuBar()
        menu = menubar.addMenu("游戏")
        a = QAction("新局", self); a.triggered.connect(self.new_game)
        menu.addAction(a)
        self.sound_action = QAction("音效", self)
        self.sound_action.setCheckable(True)
        self.sound_action.setChecked(True)
        self.sound_action.toggled.connect(self._toggle_sound)
        menu.addAction(self.sound_action)
        quit_action = QAction("退出", self); quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _toggle_sound(self, enabled: bool) -> None:
        sound.set_enabled(enabled)

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
        self.players_grid = QGridLayout()
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
        self.dice_view = DiceView()
        cb.addWidget(self.dice_view)
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
        b3 = QPushButton("结束回合并运行 AI"); b3.clicked.connect(self.run_bots); cb.addWidget(b3)
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
        self._played_log_count = 0
        self.dice_view.set_values(self.game._last_roll)
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
            panel = PlayerPanel(
                player, self.game.board, i == self.human_index,
                self.players_grid.parentWidget(),
                avatar=PLAYER_AVATARS[i % len(PLAYER_AVATARS)],
                color=PLAYER_COLORS[i % len(PLAYER_COLORS)],
            )
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
        player_index = self.game.players.index(p)
        before = p.position
        self.game.run_step()
        self.board_view.animate_move(player_index, before, p.position)

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
        if self.game.pending_purchase is None and not self.game.is_won():
            QTimer.singleShot(0, lambda: self.run_bots(start_with_human=False))

    def buy_pending_asset(self) -> None:
        if self.game and self.game.buy_pending_asset(self.game.players[self.human_index]):
            self.status.setText("购买完成，AI 行动中…")
        self._after_step()
        if self.game and not self.game.is_won():
            QTimer.singleShot(0, lambda: self.run_bots(start_with_human=False))

    def decline_pending_asset(self) -> None:
        if self.game and self.game.decline_pending_asset(self.game.players[self.human_index]):
            self.status.setText("已放弃购买，AI 行动中…")
        self._after_step()
        if self.game and not self.game.is_won():
            QTimer.singleShot(0, lambda: self.run_bots(start_with_human=False))

    def run_bots(self, limit: int = 10000, start_with_human: bool = True) -> None:
        if not self.game:
            self.status.setText("请先开始游戏")
            return
        if self.game.pending_purchase is not None:
            self.status.setText("请先决定是否购买当前地产")
            return
        self.status.setText("AI 行动中…")
        if start_with_human and self._is_human_turn():
            self._act_current()
            if self.game.pending_purchase is not None or self.game.is_won():
                self._after_step()
                return
        for _ in range(limit):
            if self.game.is_won() or self._remaining() == 0:
                break
            self.game.next_turn()
            current = self.game._current_player()
            if self._is_human_turn():
                break
            self._act_current()
            self._play_sounds_for_new_logs()
        self._after_step()

    def _after_step(self):
        self.log_pane.refresh()
        if self.game is not None:
            self.dice_view.set_values(self.game._last_roll)
        for panel in self._player_panels:
            panel.refresh()
        self._play_sounds_for_new_logs()
        if self.game and self.game.is_won():
            self.status.setText("游戏结束 · " + (self.game.winner.name or "") + " 获胜!")
        elif self.game and self.game.pending_purchase is not None:
            _, tile = self.game.pending_purchase
            self.status.setText(f"你到达 {tile.name}，售价 ¥{tile.price}")
        else:
            self.status.setText("轮到你行动")
        self._refresh_purchase_controls()

    _PHASE_SOUNDS = {
        "roll": "roll",
        "buy": "buy",
        "build": "buy",
        "rent": "rent",
        "税收": "event",
        "坐牢": "jail",
        "牢房": "jail",
        "出狱": "event",
        "机会": "event",
        "社区": "event",
        "银行": "event",
        "起点奖金": "event",
        "结束": "win",
    }

    def _play_sounds_for_new_logs(self) -> None:
        if self.game is None:
            return
        new_logs = self.game.log[self._played_log_count:]
        self._played_log_count = len(self.game.log)
        for phase, _text in new_logs:
            name = self._PHASE_SOUNDS.get(phase)
            if name:
                sound.play(name)

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
    sound.init(enabled=True)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
