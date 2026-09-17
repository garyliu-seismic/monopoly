"""The game engine (pure logic, no graphics).

Owns the board, the players, the current turn, money ledger and event
stacks.  Small, testable steps:

* :meth:`start`        reset + seed players at tile 0.
* :meth:`next_turn`    advance the turn pointer, skip bankrupt players.
* :meth:`roll`         consume dice total, log it.
* :meth:`advance`      move, wrap, trigger GO bonus.
* :meth:`_land`        category dispatch + buys.
* :meth:`_detect_winner` win/lose check.

``log`` is a list of ``(phase, text)``; the UI paints from it.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Sequence, Tuple

from .board import Board, Tile
from .dice import roll_pair
from .player import Player
from .tile_types import TileType

Log = List[Tuple[str, str]]


class GameOver(Exception):
    """Raised when the game reaches its end condition."""


class Game:
    def __init__(
        self,
        players: Sequence[Player],
        board: Optional[Board] = None,
        seed: Optional[int] = None,
        max_turns: int = 1000,
    ) -> None:
        self.log: Log = []
        self.board: Board = board or Board(34)
        self.players: List[Player] = list(players)
        self.max_turns = max_turns
        self.board_size = len(self.board.tiles)
        self._rng = random.Random(seed)
        self.turn_index = 0
        self.turn = 0
        self.phase = "setup"
        self.winner: Optional[Player] = None
        self._last_roll: Tuple[int, int] = (0, 0)
        self._stacks: Dict[str, List[str]] = self._build_stacks()

    # --------------------------------------------------------------- setup
    def start(self) -> Log:
        self.board.reset_owned()
        self.log = []
        self.turn = 0
        self.turn_index = 0
        self.phase = "setup"
        self.winner = None
        for p in self.players:
            p.position = 0
            p.bankrupt = False
            p.in_prison = False
            p.jail_turn = 0
        self.add_log("start", "游戏开始，共 " + str(len(self.players)) + " 名玩家")
        return self.log

    def add_log(self, phase: str, text: str) -> str:
        self.log.append((phase, text))
        return text

    def _build_stacks(self) -> Dict[str, List[str]]:
        names = [
            "money_get", "bank_lotto", "jail_go", "tax_pay", "repair", "pass",
            "money_get", "bank_lotto", "money_get", "tax_pay",
        ]
        return {
            "chance": list(names),
            "community": list(reversed(names)),
            "bank": ["bank_lotto"],
        }

    def _pop_stack(self, key: str) -> str:
        stack = self._stacks[key]
        if not stack:
            stack.extend(["money_get", "pass", "tax_pay", "bank_lotto"])
        return stack.pop(self._rng.randrange(len(stack)))

    # --------------------------------------------------------- turn cycling
    def next_turn(self) -> None:
        if self.turn >= self.max_turns:
            raise GameOver("turn limit reached, no winner")
        self.turn += 1
        n = len(self.players)
        self.turn_index = (self.turn_index + 1) % n
        # skip bankrupt players
        guard = 0
        while self._current_player().bankrupt and guard < n:
            self.turn_index = (self.turn_index + 1) % n
            guard += 1
        self.phase = "roll"

    def _current_player(self) -> Player:
        return self.players[self.turn_index]

    def _alive_players(self) -> List[Player]:
        return [p for p in self.players if not p.bankrupt]

    # --------------------------------------------------------------- dice
    def _roll_pair(self) -> None:
        d = roll_pair()
        self._last_roll = d.values

    def roll(self) -> int:
        self._roll_pair()
        total = sum(self._last_roll)
        self.add_log("roll", f"{self._current_player().name} 掷出 {total}")
        return total

    # --------------------------------------------------------------- movement
    def advance(self, player: Player, count: int) -> int:
        before = player.position
        after = (before + count) % self.board_size
        crossed_go = before + count >= self.board_size
        player.position = after
        if crossed_go:
            player.add(100)
            self.add_log("起点", f"{player.name} 经过起点 +100")
        return after

    def _land(self, player: Player) -> None:
        t = self.board.tile_by_index(player.position)
        cat = t.category
        if cat == TileType.CHANCE:
            self._draw_and_apply(player, "chance", "机会")
        elif cat == TileType.COMMUNITY:
            self._draw_and_apply(player, "community", "社区")
        elif cat == TileType.GANBANG:
            self._draw_and_apply(player, "bank", "银行")
        elif cat == TileType.TAX:
            amt = 100 if t.price == 0 else t.price
            paid = player.spend(amt)
            self.add_log("税收", f"{player.name} 缴纳税收 -{paid}")
        elif cat == TileType.PROPERTY:
            self._land_property(player, t)
        else:
            self.add_log(cat.name, f"{player.name} 到了 {t.name}")

    def _land_property(self, player: Player, t: Tile) -> None:
        owner = t.owner
        if owner is None:
            if player.money > t.price:
                t.owner = player.name
                t.house = 0
                player.pay(t.price)
                player.properties.append(t.tile)
                self.add_log("buy", f"{player.name} 购买 {t.name}（-{t.price}）")
            elif player._owns_group(self, t):
                self._build_house(player, t)
            else:
                self.add_log("地产", f"{player.name} 到了 {t.name}（{owner or '未买'}）")
        elif owner != player.name:
            self._pay_rent(player, t)

    def _build_house(self, player: Player, t: Tile) -> None:
        cost = int(t.price * 0.5)
        if player.money >= cost:
            player.spend(cost)
            t.house += 1
            self.add_log("build", f"{player.name} 为 {t.name} 升级（-{cost}）")

    def _pay_rent(self, player: Player, t: Tile) -> None:
        base = t.price
        rent = (base // 10) * (1 + 2 * t.house)
        rent = max(rent, base // 10)
        paid = player.spend(rent)
        cred = next((pl for pl in self.players if pl.name == t.owner), None)
        if cred is not None:
            cred.add(paid)
        self.add_log("rent", f"{player.name} 向 {t.owner} 交租 -{paid}")

    def _draw_and_apply(self, player: Player, key: str, label: str) -> None:
        name = self._pop_stack(key)
        handler = EVENTS.get(name)
        if handler is None:
            self.add_log(label, f"{player.name} 抽到 {label}: {name}（无事发生）")
            return
        res = handler(self, player)
        if isinstance(res, (list, tuple)):
            for phase_, text in res:
                self.add_log(phase_, text)
        elif isinstance(res, str):
            self.add_log(label, res)

    # ----------------------------------------------------------- winner check
    def _detect_winner(self) -> None:
        alive = self._alive_players()
        if len(alive) == 1 and self.winner is None:
            self.winner = alive[0]
            self.add_log("结束", f"{alive[0].name} 获胜!")

    def is_won(self) -> bool:
        return self.winner is not None

    def run(self, steps: Optional[int] = 100) -> Log:
        for _ in range(steps):
            self.next_turn()
            self.roll()
            p = self._current_player()
            total = sum(self._last_roll)
            self.advance(p, total)
            self._land(p)
            self._check_bankrupt()
            self._detect_winner()
            if self.is_won():
                break
        return self.log

    def _check_bankrupt(self) -> None:
        """Flag players that have burned through all cash."""
        for pl in self.players:
            if pl.is_bankrupt():
                pl.bankrupt = True


# --- Event registry (defined in events.py) --------------------------------
from .events import EVENTS  # noqa: E402
