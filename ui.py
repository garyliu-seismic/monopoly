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
from itertools import count
from typing import Callable, List, Optional, Iterable

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QTextBrowser, QPushButton, QLabel, QFrame,
    QDialog, QProgressBar, QComboBox, QSpinBox, QFileDialog, QMessageBox, QToolTip,
    QScrollArea, QSizePolicy,
)
from PySide6.QtCore import (
    Qt, QPoint, QSize, QRect, QTimer, QObject, QPropertyAnimation, QAbstractAnimation,
)
from PySide6.QtGui import QColor, QPainter, QFont, QAction, QPen, QCursor, QPolygon, QLinearGradient

from game import game as game_engine
from game.player import Player
from game.board import Board, build_map
from game.maps import by_key, available_maps
from game.tile_types import TileType
from game.bank import LOAN_OVERDUE_TURNS
from game.prompt import card_event_display, card_event_index, CARD_KIND, CARD_ICON
from game.timer import TurnTimer

import sound
import save


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
    "orange": "#ffb300", "red": "#e53935", "yellow": "#fdd835",
    "green": "#43a047", "darkblue": "#1e3a8a",
}
# category -> (fill, accent, emoji) for non-property tiles
_TILE_STYLE = {
    "GO": ("#d8f3dc", "#2d9d4f", "🏁"), "CHANCE": ("#ffe8c7", "#f08c00", "❓"),
    "COMMUNITY": ("#ffd9e4", "#d6336c", "🎁"), "TAX": ("#ffe0d6", "#e8590c", "💰"),
    "RAILROAD": ("#e8e2dc", "#5c4a3d", "🚉"), "UTILITY": ("#d6ecff", "#1c7ed6", "💡"),
    "JAIL": ("#e3e7ea", "#495057", "🔒"), "FREE": ("#e6f7d4", "#5c940d", "🅿️"),
    "GANBANG": ("#e5dbff", "#6741d9", "🦹"), "PRISON": ("#e3e7ea", "#495057", "🔒"),
    "GO_JAIL": ("#ffd6d6", "#c92a2a", "🚓"), "SPECIAL": ("#fff3bf", "#e67700", "⭐"),
}
PLAYER_COLORS = ["#e53935", "#1e88e5", "#43a047", "#8e24aa"]
PLAYER_AVATARS = ["🧑", "🤖", "👽", "👻"]


class BoardView(QWidget):
    """Paints the Monopoly board around a central game area."""

    CELL = 128

    def __init__(self, board: Board, parent=None):
        super().__init__(parent)
        self.board = board
        self.setMinimumSize(360, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setStyleSheet("background: #12372a; border: 0;")
        self._animation_queue = []
        self._active_animation = None
        self._display_positions = {}
        self._active_player_index = -1
        self._win_cells: List[QPoint] = []
        self._win_flash = 0
        self._hover_tile = None
        self._move_timer = QTimer(self)
        self._move_timer.setInterval(115)
        self._move_timer.timeout.connect(self._advance_animation)

    def set_active_highlight(self, index: int) -> None:
        """Highlight the token of player ``index`` (``-1`` clears it)."""
        self._active_player_index = index
        self.update()

    def _grid(self) -> dict:
        # Board always exposes ``grid`` (tile index -> (row, col)).
        return self.board.grid

    def _tile_at(self, point: QPoint):
        """Return the board tile rendered at ``point``, if any."""
        grid = self._grid()
        cols = max((c for _, c in grid.values() if isinstance(c, int)), default=0)
        rows = max((r for r, _ in grid.values() if isinstance(r, int)), default=0)
        cell = min(self.width() / (cols + 1), self.height() / (rows + 1))
        ox = (self.width() - (cols + 1) * cell) / 2
        oy = (self.height() - (rows + 1) * cell) / 2
        for tile in self.board.tiles:
            row, column = grid.get(tile.tile, (0, 0))
            if not isinstance(row, int) or not isinstance(column, int):
                row, column = 0, tile.tile % 3
            rect = QRect(
                int(ox + column * cell),
                int(oy + row * cell),
                int(cell),
                int(cell),
            )
            if rect.contains(point):
                return tile
        return None

    @staticmethod
    def _house_tooltip(tile) -> str:
        level = "酒店" if tile.house >= 4 else f"{tile.house} 级房屋"
        rent = tile.price // 20 * (1 + 2 * tile.house)
        return f"{tile.name}\n{level}\n当前租金: ¥{rent:,}"

    def mouseMoveEvent(self, event) -> None:
        tile = self._tile_at(event.position().toPoint())
        if tile is not self._hover_tile:
            self._hover_tile = tile
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover_tile is not None:
            self._hover_tile = None
            self.update()
        super().leaveEvent(event)

    @staticmethod
    def _rent_ladder(tile) -> List[tuple]:
        """(label, rent) rows for a property: land, 1-3 houses, hotel."""
        labels = ["地皮", "1 级房屋", "2 级房屋", "3 级房屋", "酒店"]
        return [
            (labels[level], game_engine.Game.property_rent(
                type("T", (), {"price": tile.price, "house": level})()))
            for level in range(5)
        ]

    def _draw_detail_card(self, qp: QPainter, center: QRect, tile, cell: float) -> None:
        """Draw a property detail card (header, price, rent ladder) in the board centre."""
        card_w = min(center.width() - 24, int(cell * 3.2))
        card_h = min(center.height() - 24, int(cell * 3.4))
        card = QRect(
            center.center().x() - card_w // 2,
            center.center().y() - card_h // 2,
            card_w, card_h,
        )
        qp.setPen(QPen(QColor("#c5d2c8"), 1))
        qp.setBrush(QColor("#ffffff"))
        qp.drawRoundedRect(card, 8, 8)

        header_h = max(28, int(card_h * 0.17))
        header = QRect(card.left(), card.top(), card.width(), header_h)
        header_color = QColor(_GROUP_COLORS.get(tile.group, "#176d5b"))
        qp.setPen(Qt.NoPen)
        qp.setBrush(header_color)
        qp.drawRoundedRect(header.adjusted(0, 0, 0, 8), 8, 8)
        qp.drawRect(header.adjusted(0, header_h - 8, 0, 0))
        light_header = header_color.lightness() > 150
        qp.setPen(QColor("#1e3027") if light_header else QColor("#ffffff"))
        title_size = max(10, min(int(cell * 0.17), header_h // 2))
        qp.setFont(QFont("Microsoft JhengHei", title_size, QFont.Bold))
        qp.drawText(header.adjusted(6, 0, -6, 0), Qt.AlignCenter | Qt.TextWordWrap, tile.name)

        body = card.adjusted(14, header_h + 8, -14, -8)
        text_size = max(8, int(cell * 0.11))
        qp.setFont(QFont("Segoe UI", text_size))
        row_h = max(text_size + 8, int(text_size * 2.1))

        def row(y: int, left: str, right: str, bold: bool = False, color: str = "#23362b") -> None:
            font = QFont("Microsoft JhengHei", text_size)
            font.setBold(bold)
            qp.setFont(font)
            qp.setPen(QColor(color))
            r = QRect(body.left(), y, body.width(), row_h)
            qp.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, left)
            qp.drawText(r, Qt.AlignRight | Qt.AlignVCenter, right)

        y = body.top()
        owner = tile.owner or "无人"
        row(y, "类型", tile.category.self_name, color="#516158"); y += row_h
        if tile.price:
            row(y, "价格", f"¥{tile.price:,}", bold=True); y += row_h
        row(y, "所有者", owner, color="#516158" if tile.owner else "#d99700"); y += row_h

        if tile.category == TileType.PROPERTY and tile.price:
            qp.setPen(QColor("#d5e0d6"))
            qp.drawLine(body.left(), y + 2, body.right(), y + 2)
            y += 6
            for level, (label, rent) in enumerate(self._rent_ladder(tile)):
                current = level == min(tile.house, 4)
                if current:
                    qp.fillRect(QRect(body.left() - 6, y, body.width() + 12, row_h), QColor("#e4f2ec"))
                row(y, label, f"¥{rent:,}", bold=current, color="#176d5b" if current else "#23362b")
                y += row_h
            row(y, "建造费用", f"¥{tile.price // 2:,} / 级", color="#516158")
        elif tile.category == TileType.RAILROAD:
            row(y, "租金", "¥200 × 持有数量", color="#516158")
        elif tile.category == TileType.UTILITY:
            row(y, "租金", "按持有数量结算", color="#516158")

    def sizeHint(self) -> QSize:
        return QSize(640, 640)

    def set_game(self, game):
        """Store a game reference so a player token can be drawn per tile."""
        self.board_game = game
        self.board = game.board
        self._animation_queue.clear()
        self._active_animation = None
        self._display_positions.clear()
        self._move_timer.stop()
        self.update()

    @staticmethod
    def _draw_building(qp, band: QRect, level: int) -> None:
        """Draw houses for levels 1-3 and a hotel for the maximum level."""
        if level >= 4:
            hotel = QRect(
                band.left() + band.width() // 5,
                band.top() + band.height() // 5,
                band.width() * 3 // 5,
                band.height() * 3 // 5,
            )
            qp.setPen(QPen(QColor("#8f2f22"), 1))
            qp.setBrush(QColor("#e76f51"))
            qp.drawRect(hotel)
            qp.setBrush(QColor("#fff3d1"))
            window_size = max(2, hotel.width() // 6)
            for row in range(2):
                for column in range(3):
                    qp.drawRect(
                        hotel.left() + hotel.width() * (column + 1) // 4 - window_size // 2,
                        hotel.top() + hotel.height() * (row + 1) // 3 - window_size // 2,
                        window_size,
                        window_size,
                    )
            return

        count = max(1, min(level, 3))
        width = max(6, band.width() // (count * 2))
        height = max(7, band.height() * 3 // 5)
        gap = max(2, (band.width() - count * width) // (count + 1))
        for index in range(count):
            left = band.left() + gap * (index + 1) + width * index
            top = band.bottom() - height
            body = QRect(left, top + height // 3, width, height * 2 // 3)
            qp.setPen(QPen(QColor("#1e6b4a"), 1))
            qp.setBrush(QColor("#68b984"))
            qp.drawRect(body)
            qp.setBrush(QColor("#f9e6a1"))
            qp.drawPolygon(QPolygon([
                QPoint(left - 1, top + height // 3),
                QPoint(left + width // 2, top),
                QPoint(left + width + 1, top + height // 3),
            ]))
            window_size = max(2, width // 4)
            qp.setBrush(QColor("#d9f0ff"))
            qp.drawRect(left + width // 2 - window_size // 2, top + height // 2, window_size, window_size)

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
        # board frame + soft felt backdrop
        frame = QRect(int(ox) - 6, int(oy) - 6, int(grid_w) + 12, int(grid_h) + 12)
        felt = QLinearGradient(frame.topLeft(), frame.bottomRight())
        felt.setColorAt(0, QColor("#1c5a43"))
        felt.setColorAt(1, QColor("#0e2f23"))
        qp.setPen(Qt.NoPen)
        qp.setBrush(felt)
        qp.drawRoundedRect(frame, 14, 14)
        owners = {pl.name: i for i, pl in enumerate(board_game.players)} if board_game is not None else {}
        for tile in self.board.tiles:
            r, c = grid.get(tile.tile, (0, 0))
            if not isinstance(r, int) or not isinstance(c, int):
                r, c = 0, tile.tile % 3
            x, y = pos(c, r)
            rect = QRect(int(x), int(y), int(cell), int(cell)).adjusted(2, 2, -2, -2)
            is_property = tile.category == TileType.PROPERTY
            fill, accent, icon = _TILE_STYLE.get(tile.category.name, ("#ffffff", "#516158", ""))
            qp.setPen(QPen(QColor("#00000030"), 1))
            qp.setBrush(QColor("#fffdf6") if is_property else QColor(fill))
            qp.drawRoundedRect(rect, 7, 7)
            size = max(8, int(cell * 0.105))
            band_h = int(cell * 0.24)
            if is_property:
                band = QRect(rect.left(), rect.top(), rect.width(), band_h)
                color = QColor(_GROUP_COLORS.get(tile.group, "#888888"))
                qp.setPen(Qt.NoPen)
                qp.setBrush(color)
                qp.drawRoundedRect(band.adjusted(0, 0, 0, 7), 7, 7)
                qp.drawRect(band.adjusted(0, band_h - 7, 0, 0))
                if tile.house:
                    self._draw_building(qp, band.adjusted(3, 3, -3, -3), tile.house)
                text_top = rect.top() + band_h + 5
            else:
                qp.setFont(QFont("Segoe UI Emoji", max(9, int(cell * 0.20))))
                qp.setPen(QColor(accent))
                qp.drawText(rect.adjusted(0, int(cell * 0.04), 0, 0),
                            Qt.AlignHCenter | Qt.AlignTop, icon)
                text_top = rect.top() + int(cell * 0.46)
            qp.setFont(QFont("Microsoft JhengHei", size, QFont.Bold))
            qp.setPen(QColor("#1e3027") if is_property else QColor(accent).darker(140))
            qp.drawText(
                QRect(rect.left() + 3, text_top, rect.width() - 6, int(cell * 0.30)),
                Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, tile.name,
            )
            if tile.price and tile.category in (TileType.PROPERTY, TileType.RAILROAD, TileType.UTILITY, TileType.TAX):
                foot = QRect(rect.left() + 3, rect.bottom() - int(cell * 0.24), rect.width() - 6, int(cell * 0.22))
                if tile.owner:
                    owner_color = QColor(PLAYER_COLORS[owners.get(tile.owner, 0) % len(PLAYER_COLORS)])
                    qp.setPen(Qt.NoPen)
                    qp.setBrush(owner_color)
                    qp.drawRoundedRect(foot, 5, 5)
                    qp.setPen(QColor("#ffffff"))
                    label = tile.owner
                else:
                    qp.setPen(QColor("#516158"))
                    label = f"¥{tile.price:,}"
                qp.setFont(QFont("Segoe UI", max(7, size - 1), QFont.Bold))
                qp.drawText(foot, Qt.AlignCenter, label)
            if tile.mortgaged:
                qp.setPen(Qt.NoPen)
                qp.setBrush(QColor(60, 60, 60, 150))
                qp.drawRoundedRect(rect, 7, 7)
                qp.setPen(QColor("#ffffff"))
                qp.setFont(QFont("Microsoft JhengHei", max(9, size), QFont.Bold))
                qp.drawText(rect, Qt.AlignCenter, "已抵押")
            if tile.tile == active_position:
                qp.setBrush(Qt.NoBrush)
                qp.setPen(QPen(QColor("#ffd43b"), 3))
                qp.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 7, 7)

        center = QRect(int(ox + cell), int(oy + cell), int(grid_w - 2 * cell), int(grid_h - 2 * cell))
        centre_fill = QLinearGradient(center.topLeft(), center.bottomRight())
        centre_fill.setColorAt(0, QColor("#f4fbf6"))
        centre_fill.setColorAt(1, QColor("#cfe8d8"))
        qp.setPen(QColor("#b4c7b8"))
        qp.setBrush(centre_fill)
        qp.drawRoundedRect(center.adjusted(2, 2, -2, -2), 10, 10)
        if self._hover_tile is not None and self._hover_tile.category in (
            TileType.PROPERTY, TileType.RAILROAD, TileType.UTILITY,
        ):
            self._draw_detail_card(qp, center, self._hover_tile, cell)
        else:
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
            active_idx = self._active_player_index
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
                if active_idx >= 0 and idx == active_idx:
                    # Active player: draw a bright pulsing ring.
                    qp.setPen(QPen(QColor("#147d68"), int(token_r * 0.85)))
                    qp.setBrush(QColor("#0f5b4b"))
                    qp.drawEllipse(cx - token_r, cy - token_r, token_r * 2, token_r * 2)
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
        if self._win_cells:
            for tile_index, flash_size in self._win_cells:
                r, c = grid.get(tile_index, (0, 0))
                if not isinstance(r, int) or not isinstance(c, int):
                    continue
                wx, wy = pos(c, r)
                wr = max(6, int(flash_size * cell))
                # A pulsing amber/range overlay highlights the winning tiles
                # across the whole board when a game ends.
                qp.setPen(QPen(QColor("#ffd54f") if self._win_flash < 8 else QColor("#ff7043"), 3))
                qp.drawRect(QRect(int(wx) + cell - wr, int(wy) + cell - wr, wr * 2, wr * 2))
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
            0: [],
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
    """One player's card on the left: 姓名/初始资金/现金/地产/股票/净资产."""

    def __init__(self, player: Player, board: Board, is_human: bool, parent=None,
                 avatar: str = "🧑", color: str = "#555", stock_market=None):
        super().__init__(parent)
        self.player = player
        self.board = board
        self.is_human = is_human
        self.avatar = avatar
        self.stock_market = stock_market
        self.setMinimumHeight(118)
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
        self.meta = QLabel("初始 ¥0 · 净资产 ¥0")
        self.meta.setStyleSheet("QLabel { color: #176d5b; font-size: 11px; font-weight: bold; }")
        layout.addWidget(self.meta)
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
        prop_value = sum(self.board.tiles[i].price for i in p.properties)
        stock_value = 0
        if self.stock_market is not None:
            stock_value = sum(
                s.price * p.stocks.get(s.code, 0) for s in self.stock_market.stocks
            )
        net = p.money + prop_value + stock_value
        self.info.setText(f"现金 ¥{p.money} · 地产 {len(p.properties)} 块 · {tag}")
        self.meta.setText(f"初始 ¥{p.initial_money} · 净资产 ¥{net}")
        parts = [self.board.tiles[i].name for i in p.properties]
        if p.stocks and self.stock_market is not None:
            for s in self.stock_market.stocks:
                n = p.stocks.get(s.code, 0)
                if n:
                    parts.append(f"📈{s.name}×{n}")
        self.props.setText(" / ".join(parts) if parts else "（暂无）")


class StockPanel(QWidget):
    """Live stock quotes plus buy/sell controls for the human player."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game = None
        self.human_index = 0
        self.on_trade = None  # callable(ok: bool, message: str)
        self.setStyleSheet(
            "StockPanel { background: #ffffff; border: 1px solid #d5e0d6; border-radius: 6px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        title = QLabel("📈 股票市场")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #176d5b;")
        layout.addWidget(title)
        self.quote_label = QLabel("（未开始）")
        self.quote_label.setWordWrap(True)
        self.quote_label.setStyleSheet("color: #444; font-size: 11px;")
        layout.addWidget(self.quote_label)
        row = QHBoxLayout()
        self.stock_combo = QComboBox()
        self.shares_spin = QSpinBox()
        self.shares_spin.setRange(1, 999)
        self.shares_spin.setValue(10)
        row.addWidget(self.stock_combo, 2)
        row.addWidget(self.shares_spin, 1)
        layout.addLayout(row)
        row2 = QHBoxLayout()
        buy_btn = QPushButton("买入")
        sell_btn = QPushButton("卖出")
        buy_btn.clicked.connect(lambda: self._trade(True))
        sell_btn.clicked.connect(lambda: self._trade(False))
        row2.addWidget(buy_btn)
        row2.addWidget(sell_btn)
        layout.addLayout(row2)
        self.holding_label = QLabel("我的持仓：无")
        self.holding_label.setWordWrap(True)
        self.holding_label.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.holding_label)

    def set_game(self, game, human_index):
        self.game = game
        self.human_index = human_index
        self._refresh_combo()
        self.refresh()

    def _refresh_combo(self):
        self.stock_combo.clear()
        if self.game is None:
            return
        for s in self.game.stock_market.stocks:
            self.stock_combo.addItem(f"{s.name} ({s.code})", s.code)

    def refresh(self):
        if self.game is None:
            self.quote_label.setText("（未开始）")
            return
        market = self.game.stock_market
        self.quote_label.setText(
            "  |  ".join(f"{s.name} ¥{s.price}" for s in market.stocks)
        )
        human = self.game.players[self.human_index]  # human_index updated by step() each turn
        held = [(s.name, human.stocks.get(s.code, 0)) for s in market.stocks]
        held = [(n, c) for n, c in held if c > 0]
        if held:
            self.holding_label.setText(
                "我的持仓：" + "，".join(f"{n} ×{c}" for n, c in held)
            )
        else:
            self.holding_label.setText("我的持仓：无")

    def _trade(self, is_buy):
        if self.game is None or self.on_trade is None:
            return
        code = self.stock_combo.currentData()
        shares = self.shares_spin.value()
        human = self.game.players[self.human_index]  # human_index updated by step() each turn
        if is_buy:
            ok, msg = self.game.buy_stock(human, code, shares)
        else:
            ok, msg = self.game.sell_stock(human, code, shares)
        self.on_trade(ok, msg)


class BankPanel(QWidget):
    """Banking: view balance, deposit / withdraw / borrow / repay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game = None
        self.human_index = 0
        self.on_bank = None  # callable(ok: bool, message: str)
        self.setStyleSheet(
            "BankPanel { background: #ffffff; border: 1px solid #d5e0d6; border-radius: 6px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        title = QLabel("🏦 银行（存款 5%/圈 · 贷款 10%/圈，逾期 20%）")
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: bold; font-size: 12px; color: #176d5b;")
        layout.addWidget(title)
        self.balance_label = QLabel("存款 ¥0 · 贷款 ¥0 · 现金 ¥0")
        self.balance_label.setWordWrap(True)
        self.balance_label.setStyleSheet("color: #444; font-size: 11px;")
        layout.addWidget(self.balance_label)
        row = QHBoxLayout()
        row.addWidget(QLabel("金额"))
        self.amount_spin = QSpinBox()
        self.amount_spin.setRange(100, 100000)
        self.amount_spin.setSingleStep(500)
        self.amount_spin.setValue(1000)
        row.addWidget(self.amount_spin, 1)
        layout.addLayout(row)
        grid = QGridLayout()
        deposit_btn = QPushButton("存款")
        withdraw_btn = QPushButton("取款")
        borrow_btn = QPushButton("贷款")
        repay_btn = QPushButton("还款")
        deposit_btn.clicked.connect(lambda: self._act("deposit"))
        withdraw_btn.clicked.connect(lambda: self._act("withdraw"))
        borrow_btn.clicked.connect(lambda: self._act("borrow"))
        repay_btn.clicked.connect(lambda: self._act("repay"))
        grid.addWidget(deposit_btn, 0, 0)
        grid.addWidget(withdraw_btn, 0, 1)
        grid.addWidget(borrow_btn, 1, 0)
        grid.addWidget(repay_btn, 1, 1)
        layout.addLayout(grid)

    def set_game(self, game, human_index):
        self.game = game
        self.human_index = human_index
        self.refresh()

    def refresh(self):
        if self.game is None:
            self.balance_label.setText("（未开始）")
            return
        lines = []
        for i, p in enumerate(self.game.players):
            avatar = PLAYER_AVATARS[i % len(PLAYER_AVATARS)]
            tag = " ⚠️逾期" if p.loan_age >= LOAN_OVERDUE_TURNS else ""
            me = "（你）" if not p.is_bot else ""
            lines.append(f"{avatar}{p.name}{me}: 存¥{p.bank} 贷¥{p.loan}{tag}")
        self.balance_label.setText("\n".join(lines))

    def _act(self, op):
        if self.game is None or self.on_bank is None:
            return
        p = self.game.players[self.human_index]  # human_index updated by step() each turn
        amount = self.amount_spin.value()
        if op == "deposit":
            ok, msg = self.game.deposit(p, amount)
        elif op == "withdraw":
            ok, msg = self.game.withdraw(p, amount)
        elif op == "borrow":
            ok, msg = self.game.borrow(p, amount)
        else:
            ok, msg = self.game.repay(p, amount)
        self.on_bank(ok, msg)


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
        self._human_log_marker = 0
        self._show_human_report = False
        self._card_render_marker = -1
        self._card_index = 0
        self._win_cells: List = []
        self._win_iter: Optional[Iterable[int]] = None
        # turn-countdown + win-flash UI state
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(100)
        self.ui_timer.timeout.connect(self._on_ui_timer_tick)
        self._turn_timer_state = None
        self._win_flash = 0
        self._win_anim: Optional[QTimer] = None
        self._turn_timer = TurnTimer(base_seconds=90)
        self._turn_countdown_bar: Optional[QProgressBar] = None
        self.board_view: BoardView = BoardView(Board())
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
        save_action = QAction("存档", self); save_action.triggered.connect(self.save_game)
        menu.addAction(save_action)
        load_action = QAction("读档", self); load_action.triggered.connect(self.load_game)
        menu.addAction(load_action)
        quit_action = QAction("退出", self); quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _toggle_sound(self, enabled: bool) -> None:
        sound.set_enabled(enabled)

    def save_game(self) -> None:
        if self.game is None:
            self.status.setText("请先开始游戏")
            return
        path, _ = QFileDialog.getSaveFileName(self, "存档", "monopoly_save.json", "JSON (*.json)")
        if not path:
            return
        try:
            save.save_game(self.game, path)
            self.status.setText(f"已存档：{path}")
        except Exception as exc:  # pragma: no cover
            self.status.setText(f"存档失败：{exc}")

    def load_game(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "读档", "", "JSON (*.json)")
        if not path:
            return
        try:
            loaded = save.load_game(path)
        except Exception as exc:  # pragma: no cover
            self.status.setText(f"读档失败：{exc}")
            return
        self.game = loaded
        self._played_log_count = 0
        self._turn_timer.reset()
        self._turn_timer_state = None
        self._card_render_marker = -1
        self._win_cells = []
        self._win_flash = 0
        if self._win_anim is not None:
            self._win_anim.stop()
        self._sync_players()
        self.stock_panel.set_game(self.game, self.human_index)
        self.bank_panel.set_game(self.game, self.human_index)
        self.board_view.set_game(self.game)
        self.log_pane.game = self.game
        self.log_pane.refresh()
        self.dice_view.set_values(self.game._last_roll)
        self.status.setText("读档完成")
        self._refresh_purchase_controls()
        self._render_turn_timer()
        self._refresh_token_highlight()

    def _after_trade(self, ok: bool, message: str) -> None:
        self.status.setText(message)
        self.log_pane.refresh()
        for panel in self._player_panels:
            panel.refresh()
        self.stock_panel.refresh()

    def _after_bank(self, ok: bool, message: str) -> None:
        self.status.setText(message)
        self.log_pane.refresh()
        for panel in self._player_panels:
            panel.refresh()
        self.bank_panel.refresh()

    def _build_body(self):
        central = QWidget(); self.setCentralWidget(central)
        central.setStyleSheet("QMainWindow { background: #eef3ee; } QLabel { color: #23362b; } QPushButton { background: #176d5b; color: white; border: 0; border-radius: 5px; padding: 9px 12px; font-weight: bold; } QPushButton:hover { background: #0f5b4b; } QPushButton:disabled { background: #a8bbb0; }")
        box = QHBoxLayout(central)
        box.setContentsMargins(16, 16, 16, 16)
        box.setSpacing(12)

        left = QFrame()
        left.setFrameShape(QFrame.StyledPanel)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        players_title = QLabel("玩家资产")
        players_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #176d5b;")
        left_layout.addWidget(players_title)
        self.players_grid = QGridLayout()
        left_layout.addLayout(self.players_grid)
        self.stock_panel = StockPanel()
        self.stock_panel.on_trade = self._after_trade
        left_layout.addWidget(self.stock_panel)
        left_layout.addStretch()
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left)
        left_scroll.setMinimumWidth(190)
        left_scroll.setMaximumWidth(250)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        box.addWidget(left_scroll)

        self.board_view = BoardView(Board())
        box.addWidget(self.board_view, 3)

        controls = QFrame()
        controls.setFrameShape(QFrame.StyledPanel)
        cb = QVBoxLayout(controls)
        title = QLabel("回合控制")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #176d5b;")
        cb.addWidget(title)
        self.map_combo = QComboBox()
        for key in available_maps():
            board_map = by_key(key)
            self.map_combo.addItem(board_map.name, key)
        cb.addWidget(self.map_combo)
        # 人工玩家数量选择
        human_row = QHBoxLayout()
        human_row.addWidget(QLabel("人工玩家："))
        self.human_count_combo = QComboBox()
        for n in (1, 2, 3, 5):
            self.human_count_combo.addItem(f"{n} 人", n)
        self.human_count_combo.setCurrentIndex(0)  # 默认 1 人
        human_row.addWidget(self.human_count_combo, 1)
        cb.addLayout(human_row)
        self.status = QLabel("状态：等待新局")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("background: #e1eee5; padding: 8px; border-radius: 4px;")
        cb.addWidget(self.status)
        self.dice_view = DiceView()
        cb.addWidget(self.dice_view)
        self._turn_countdown_bar = QProgressBar()
        self._turn_countdown_bar.setRange(0, 100)
        self._turn_countdown_bar.setValue(100)
        self._turn_countdown_bar.setTextVisible(True)
        self._turn_countdown_bar.setFixedHeight(26)
        self._turn_countdown_bar.setStyleSheet(
            "QProgressBar { background: #e1eee5; border: 1px solid #176d5b; border-radius: 4px; color: #176d5b; font-weight: bold; }"
            "QProgressBar::chunk { background: #176d5b; border-radius: 3px; }"
        )
        cb.addWidget(self._turn_countdown_bar)
        self.bank_panel = BankPanel()
        self.bank_panel.on_bank = self._after_bank
        cb.addWidget(self.bank_panel)
        # --- 开始新游戏（次要按钮，放顶部，远离主操作区）---
        b1 = QPushButton("⚑  开始新游戏")
        b1.clicked.connect(self.new_game)
        b1.setStyleSheet(
            "QPushButton { background: #e1eee5; color: #2d6a4f; border: 1px solid #95c8a8;"
            " border-radius: 5px; padding: 6px 10px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #c8e6d4; }"
        )
        cb.addWidget(b1)

        # --- 分隔线 ---
        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("color: #b4c7b8; margin: 4px 0;")
        cb.addWidget(sep1)

        # --- 主行动按钮：掷骰（大、醒目）---
        b2 = QPushButton("🎲  掷骰并行动")
        b2.clicked.connect(self.step)
        b2.setMinimumHeight(52)
        b2.setStyleSheet(
            "QPushButton { background: #1b6e45; color: white; border: 0;"
            " border-radius: 8px; padding: 10px; font-weight: bold; font-size: 15px; }"
            "QPushButton:hover { background: #145236; }"
            "QPushButton:disabled { background: #a8bbb0; color: #e0e0e0; }"
        )
        cb.addWidget(b2)
        self.step_button = b2

        # --- 购买地产（横排，情境按钮）---
        buy_row = QHBoxLayout()
        self.buy_button = QPushButton("✔  购买")
        self.buy_button.clicked.connect(self.buy_pending_asset)
        self.buy_button.setEnabled(False)
        self.buy_button.setStyleSheet(
            "QPushButton { background: #d4edda; color: #155724; border: 1px solid #95c8a8;"
            " border-radius: 5px; padding: 7px; font-weight: bold; }"
            "QPushButton:hover { background: #b8dfc6; }"
            "QPushButton:disabled { background: #e9ecef; color: #999; border-color: #ced4da; }"
        )
        self.skip_buy_button = QPushButton("✖  略过")
        self.skip_buy_button.clicked.connect(self.decline_pending_asset)
        self.skip_buy_button.setEnabled(False)
        self.skip_buy_button.setStyleSheet(
            "QPushButton { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;"
            " border-radius: 5px; padding: 7px; font-weight: bold; }"
            "QPushButton:hover { background: #f1b0b7; }"
            "QPushButton:disabled { background: #e9ecef; color: #999; border-color: #ced4da; }"
        )
        buy_row.addWidget(self.buy_button)
        buy_row.addWidget(self.skip_buy_button)
        cb.addLayout(buy_row)

        # --- 分隔线 ---
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #b4c7b8; margin: 4px 0;")
        cb.addWidget(sep2)

        # --- 次要操作组 ---
        self.mortgage_button = QPushButton("🏠  管理地产（盖房 / 抵押）")
        self.mortgage_button.clicked.connect(self.open_mortgage_dialog)
        self.mortgage_button.setStyleSheet(
            "QPushButton { background: #fff3cd; color: #856404; border: 1px solid #ffc107;"
            " border-radius: 5px; padding: 7px; font-weight: bold; }"
            "QPushButton:hover { background: #ffe69c; }"
        )
        cb.addWidget(self.mortgage_button)
        log_title = QLabel("事件记录")
        log_title.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 12px;")
        cb.addWidget(log_title)
        self.log_pane = LogPane()
        self.log_pane.setMinimumHeight(190)
        cb.addWidget(self.log_pane, 1)
        cb.addStretch()
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setWidget(controls)
        controls_scroll.setMinimumWidth(230)
        controls_scroll.setMaximumWidth(280)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        box.addWidget(controls_scroll)

    def new_game(self):
        n_human = self.human_count_combo.currentData()
        total = max(n_human + 1, 4)  # 至少 4 名玩家（不足部分补 AI）
        human_names = [f"玩家{i+1}" for i in range(n_human)]
        bot_count = total - n_human
        bot_names = [f"AI-{i+1}" for i in range(bot_count)]
        all_names = human_names + bot_names
        players = [Player(name, holds=3) for name in all_names]
        for i in range(n_human, len(players)):
            players[i].is_bot = True
        # human_index 指向第一个人工玩家（index 0）
        self.human_index = 0
        board = build_map(by_key(self.map_combo.currentData()))
        self.game = game_engine.Game(players, board=board, seed=1, auto_buy=False)
        self.game.start()
        self._played_log_count = 0
        self._turn_timer.reset()
        self._turn_timer_state = None
        self._card_render_marker = -1
        self._win_cells = []
        self._win_flash = 0
        if self._win_anim is not None:
            self._win_anim.stop()
        self.dice_view.set_values(self.game._last_roll)
        self._sync_players()
        self.stock_panel.set_game(self.game, self.human_index)
        self.bank_panel.set_game(self.game, self.human_index)
        self.board_view.set_game(self.game)
        self.log_pane.game = self.game
        self.log_pane.refresh()
        self.status.setText(f"游戏开始 · {self.map_combo.currentText()} · {len(players)} 名玩家")
        self._refresh_purchase_controls()
        self._render_turn_timer()
        self._refresh_token_highlight()

    def _sync_players(self):
        for p in self._player_panels:
            p.setParent(None)
        self._player_panels = []
        for i, player in enumerate(self.game.players):
            panel = PlayerPanel(
                player, self.game.board, not player.is_bot,
                self.players_grid.parentWidget(),
                avatar=PLAYER_AVATARS[i % len(PLAYER_AVATARS)],
                color=PLAYER_COLORS[i % len(PLAYER_COLORS)],
                stock_market=self.game.stock_market,
            )
            self.players_grid.addWidget(panel, i, 0, 1, -1)
            self._player_panels.append(panel)

    def _n_human(self) -> int:
        """Number of human (non-bot) players in the current game."""
        if self.game is None:
            return 1
        return sum(1 for p in self.game.players if not p.is_bot)

    def _is_human_turn(self) -> bool:
        """True when the current player is any human (non-bot) player."""
        if self.game is None:
            return False
        return not self.game._current_player().is_bot

    def _remaining(self) -> int:
        return sum(1 for p in self.game.players if not p.bankrupt)

    def _human_bankrupt(self) -> bool:
        """True when ALL human players are bankrupt (game over for humans)."""
        if self.game is None:
            return False
        humans = [p for p in self.game.players if not p.is_bot]
        return all(p.bankrupt for p in humans)

    def _auto_run_allowed(self) -> bool:
        """True when the AI may keep running (game alive and human still in)."""
        return self.game is not None and not self.game.is_won() and not self._human_bankrupt()

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
        if self._human_bankrupt():
            self.status.setText("所有人工玩家已破产，游戏结束" if self._n_human() > 1 else "你已破产，游戏结束")
            return
        if self._remaining() == 0:
            return
        if self.game.pending_purchase is not None:
            self.status.setText("请先决定是否购买当前地产")
            return
        if not self._is_human_turn():
            self.status.setText("请先运行 AI 至你的回合")
            return
        cur = self.game._current_player()
        self._sync_human_index()
        self.status.setText(f"{cur.name} 正在行动")
        self._human_log_marker = len(self.game.log)
        self._act_current()
        self._show_human_report = True
        self._after_step()
        if self.game.pending_purchase is None and self._auto_run_allowed():
            QTimer.singleShot(0, lambda: self.run_bots(start_with_human=False))

    def open_mortgage_dialog(self) -> None:
        """List the human's properties with mortgage / redeem actions."""
        if not self.game:
            self.status.setText("请先开始游戏")
            return
        human = self.game.players[self.human_index]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"管理地产 — {human.name}")
        layout = QVBoxLayout(dialog)
        if not human.properties:
            layout.addWidget(QLabel("你还没有地产"))
        for tile_index in sorted(human.properties):
            tile = self.game.board.tiles[tile_index]
            row = QHBoxLayout()
            color = _GROUP_COLORS.get(tile.group, "#516158")
            name = QLabel(f"● {tile.name}" + ("（已抵押）" if tile.mortgaged else "") + (f"  {tile.house}级" if tile.house else ""))
            name.setStyleSheet(f"color: {color}; font-weight: bold;")
            row.addWidget(name, 1)
            actions = []
            if tile.mortgaged:
                actions.append((f"赎回 ¥{self.game.redeem_cost(tile):,}", self.game.redeem_tile, True))
            else:
                actions.append((f"抵押 +¥{self.game.mortgage_value(tile):,}", self.game.mortgage_tile, True))
            if tile.category == TileType.PROPERTY:
                can_build, why_build = self.game.can_build(human, tile_index)
                can_sell, why_sell = self.game.can_sell_house(human, tile_index)
                actions.append((f"盖房 -¥{self.game.build_cost(tile):,}", self.game.build_house, can_build, why_build))
                actions.append((f"卖房 +¥{self.game.sell_value(tile):,}", self.game.sell_house, can_sell, why_sell))
            for item in actions:
                label, action, enabled = item[0], item[1], item[2]
                button = QPushButton(label)
                if len(item) > 3 and not enabled:
                    button.setEnabled(False)
                    button.setToolTip(item[3])

                def run(_checked=False, act=action, idx=tile_index):
                    ok, message = act(human, idx)
                    self.status.setText(message)
                    self._after_bank(ok, message)
                    self.board_view.update()
                    dialog.accept()
                    self.open_mortgage_dialog()
                button.clicked.connect(run)
                row.addWidget(button)
            layout.addLayout(row)
        close = QPushButton("关闭")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def buy_pending_asset(self) -> None:
        if self.game:
            self._human_log_marker = len(self.game.log)
            self.game.buy_pending_asset(self.game.players[self.human_index])
            self._show_human_report = True
        self._after_step()
        if self._auto_run_allowed():
            QTimer.singleShot(0, lambda: self.run_bots(start_with_human=False))

    def decline_pending_asset(self) -> None:
        if self.game:
            self._human_log_marker = len(self.game.log)
            self.game.decline_pending_asset(self.game.players[self.human_index])
            self._show_human_report = True
        self._after_step()
        if self._auto_run_allowed():
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
            if self.game.pending_purchase is not None or self.game.is_won() or self._human_bankrupt():
                self._after_step()
                return
        for _ in range(limit):
            if self.game.is_won() or self._remaining() == 0 or self._human_bankrupt():
                break
            self.game.next_turn()
            current = self.game._current_player()
            if self._is_human_turn():
                break
            self._act_current()
            self._play_sounds_for_new_logs()
        self._after_step()

    def _sync_human_index(self) -> None:
        """Point human_index (and the panels' copies) at the current human player."""
        if self.game is None or not self._is_human_turn():
            return
        self.human_index = self.game.players.index(self.game._current_player())
        self.stock_panel.human_index = self.human_index
        self.bank_panel.human_index = self.human_index

    def _after_step(self):
        self._sync_human_index()
        self.log_pane.refresh()
        if self.game is not None:
            self.dice_view.set_values(self.game._last_roll)
        for panel in self._player_panels:
            panel.refresh()
        self.stock_panel.refresh()
        self.bank_panel.refresh()
        self._play_sounds_for_new_logs()
        self._update_status()
        self._refresh_purchase_controls()
        self._render_turn_timer()
        self._check_win_condition()
        self._check_card_prompt()
        self._refresh_token_highlight()

    _REPORT_EMOJI = {
        "roll": "🎲", "起点奖金": "🎉", "税收": "💰", "rent": "💸",
        "buy": "🏠", "build": "🏗️", "机会": "🎁", "社区": "🎁",
        "银行": "🏦", "坐牢": "🔒", "牢房": "🔒", "出狱": "🔓",
        "股票": "📈", "结束": "🏆", "地产": "📍",
    }

    def _human_report(self, exclude_buy_offer: bool = False) -> str:
        """Summarise the human player's latest action (roll + outcomes)."""
        human = self.game.players[self.human_index]
        tile = self.game.board.tile_by_index(human.position)
        lines: List[str] = []
        others: List[str] = []
        for phase, text in self.game.log[self._human_log_marker:]:
            if human.name not in text:
                continue
            if exclude_buy_offer and phase == "buy" and "可购买" in text:
                continue
            short = text.replace(human.name + " ", "", 1)
            emoji = self._REPORT_EMOJI.get(phase, "•")
            if phase == "roll":
                lines.append(f"{emoji} {short}")
            else:
                others.append(f"{emoji} {short}")
        lines.append(f"📍 走到 {tile.name}")
        lines.extend(others)
        lines.append(f"💵 现金：¥{human.money}")
        return "\n".join(lines)

    def _render_turn_timer(self) -> None:
        """Drive the richman-turn style countdown bar; auto-run if exceeded."""
        if self.game is None:
            return
        human = self.game.players[self.human_index]
        self._turn_timer.name = human.name
        if self.game._current_player() is human and not human.bankrupt:
            turn_state = (id(self.game), self.game.turn, self.game.turn_index)
            if turn_state != self._turn_timer_state:
                self._turn_timer.start()
                self._turn_timer_state = turn_state
            if not self._turn_timer.passed() and not self.ui_timer.isActive():
                self.ui_timer.start()
        else:
            self._turn_timer.stop()
            self._turn_timer_state = None
            self.ui_timer.stop()
        remaining = self._turn_timer.remaining_ms()
        if self._turn_countdown_bar is not None:
            self._turn_countdown_bar.setRange(0, self._turn_timer.base_seconds)
            self._turn_countdown_bar.setValue((remaining + 999) // 1000)
            self._turn_countdown_bar.setFormat(f"{human.name} 回合：{(remaining + 999) // 1000} 秒")

    def _on_ui_timer_tick(self) -> None:
        """Advance the human-turn countdown and resolve a timeout once."""
        if self.game is None or not self._is_human_turn() or self.game.is_won():
            self.ui_timer.stop()
            return
        self._turn_timer.tick(self.ui_timer.interval())
        self._render_turn_timer()
        if self._turn_timer.passed() and self._auto_run_allowed():
            self.ui_timer.stop()
            QTimer.singleShot(0, self._auto_complete_human_turn)

    def _auto_complete_human_turn(self) -> None:
        """Finish an expired human turn, declining any resulting purchase offer."""
        if not self._auto_run_allowed() or not self._is_human_turn():
            return
        self._act_current()
        if self.game.pending_purchase is not None:
            self.game.decline_pending_asset(self.game.players[self.human_index])
        self._after_step()
        if self._auto_run_allowed():
            QTimer.singleShot(0, lambda: self.run_bots(start_with_human=False))

    def _on_win_flash(self) -> None:
        if self.game is None or not self.game.is_won():
            return
        self._win_flash = (self._win_flash % 16) + 1
        self._render_win_animation()

    def _render_win_animation(self) -> None:
        """Apply the current win pulse to the board highlight cells."""
        self.board_view._win_cells = [
            (tile_index, 0.16 + 0.03 * (self._win_flash % 8))
            for tile_index in self._win_cells
        ]
        self.board_view._win_flash = self._win_flash
        self.board_view.update()

    def _check_win_condition(self) -> None:
        """Animate + highlight winning tiles across the board once game ends."""
        if self.game is None:
            return
        if not self.game.is_won():
            self.board_view._win_cells = []
            self.board_view._win_flash = 0
            if self._win_anim is not None:
                self._win_anim.stop()
            return
        if self._win_flash == 0:
            self._win_cells = [
                self.game.players[w].position for w in range(len(self.game.players))
            ]
            self._win_flash = 1
            self._render_win_animation()
            if self._win_anim is None:
                self._win_anim = QTimer(self)
                self._win_anim.setInterval(150)
                self._win_anim.timeout.connect(self._on_win_flash)
            self._win_anim.start()

    def _check_card_prompt(self) -> None:
        """Show the human's upcoming CHANCE/COMMUNITY card as a modal."""
        if self.game is None:
            return
        human = self.game.players[self.human_index]
        idx = card_event_index(self.game.log, human.name, self._card_render_marker + 1)
        if idx == -1:
            return
        phase, text = card_event_display(self.game.log[idx], human.name)
        kind = CARD_KIND.get(phase, phase)
        icon = CARD_ICON.get(phase, "🎁")
        msg = QMessageBox(self)
        msg.setWindowTitle(f"{icon} {kind}")
        msg.setIcon(QMessageBox.Information)
        msg.setText(f"{icon} {text}")
        execBtn = QPushButton("确定"); msg.addButton(execBtn, QMessageBox.AcceptRole)
        msg.exec()
        self._card_render_marker = idx

    def _update_status(self) -> None:
        if self.game is None:
            return
        human = self.game.players[self.human_index]
        cash = f"💵 现金：¥{human.money}"
        if self._human_bankrupt():
            self.status.setText("你破产了！游戏结束")
            return
        if self.game.is_won():
            self.status.setText(f"游戏结束 · {self.game.winner.name} 获胜!\n{cash}")
            return
        if self.game.pending_purchase is not None:
            _, tile = self.game.pending_purchase
            self.status.setText(f"🏠 可购买 {tile.name}（¥{tile.price}）\n{self._human_report(exclude_buy_offer=True)}")
            self._show_human_report = False
            return
        if self._show_human_report:
            self._show_human_report = False
            self.status.setText(self._human_report())
        else:
            self.status.setText(f"轮到你行动\n{cash}")

    def _refresh_token_highlight(self) -> None:
        """Recompute and push the active player index to the board view."""
        if self.game is None:
            return
        if self.game.is_won():
            self.board_view.set_active_highlight(-1)
            return
        try:
            idx = self.game.players.index(self.game._current_player())
        except (ValueError, IndexError):
            idx = -1
        self.board_view.set_active_highlight(idx)

    _PHASE_SOUNDS = {
        "roll": "roll",
        "buy": "buy",
        "build": "buy",
        "rent": "rent",
        "税收": "event",
        "股票": "buy",
        "银行": "event",
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
        if pending_for_human:
            _, tile = self.game.pending_purchase
            self.buy_button.setText(f"购买 {tile.name} · ¥{tile.price}")
            self.skip_buy_button.setText(f"放弃购买 {tile.name}")
        else:
            self.buy_button.setText("购买当前地产")
            self.skip_buy_button.setText("暂不购买")
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
