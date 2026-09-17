"""Pure game engine for the Dàfùwēng / Monopoly board game.

Nothing in this module touches GUI; every public API surface is unit-testable.
The per-turn flow lives in :meth:`run_step`, driven by :meth:`run`, following
the pipeline ``roll -> advance -> land -> pay/jail -> winner``.

Public API
----------
* ``run(steps)``        drive ``steps`` turns, return the log.
* ``run_step()``        drive a *single* full turn of the current player.
* ``start``             (re)initialise players / board.
* ``next_turn``         advance to the next live player.

Everything else is ``@private`` (leading underscore) and internal only.
"""
from __future__ import annotations

import random
from typing import List, Optional, Sequence, Tuple

from game.board import Board, Tile
from game.dice import roll_pair
from game.jail import BAIL_COST, JAIL_MAX_TURNS, is_double
from game.player import Player
from game.events import EVENTS
from game.tile_types import TileType

Log = List[Tuple[str, str]]


class GameOver(Exception):
    """Raised when a game reaches its end condition (turn limit / all bankrupt)."""


class Game:
    def __init__(
        self,
        players: Sequence[Player],
        board: Optional[Board] = None,
        seed: Optional[int] = None,
        max_turns: int = 1000,
        auto_buy: bool = True,
    ) -> None:
        self.log: Log = []
        self.board: Board = board or Board(34)
        self.players: List[Player] = list(players)
        self.max_turns = max_turns
        self.auto_buy = auto_buy
        self.board_size = len(self.board.tiles)
        self._rng = random.Random(seed)
        self.turn_index = 0
        self.turn = 0
        self.phase = "setup"
        self.winner: Optional[Player] = None
        self.pending_purchase: Optional[tuple[Player, Tile]] = None
        self._last_roll: Tuple[int, int] = (0, 0)
        self._stacks: dict[str, List[str]] = self._build_stacks()

    def start(self) -> None:
        self.board.reset_owned()
        self.log = []
        self.turn = 0
        self.turn_index = 0
        self.phase = "setup"
        self.winner = None
        self.pending_purchase = None
        for p in self.players:
            p.position = 0
            p.bankrupt = False
            p.in_prison = False
            p.jail_turn = 0
        self.add_log("start", f"游戏开始，共 {len(self.players)} 名玩家")

    def add_log(self, phase: str, text: str) -> str:
        self.log.append((phase, text))
        return text

    def _build_stacks(self) -> dict[str, List[str]]:
        names = ["money_get", "bank_lotto", "jail_go", "tax_pay", "pass"]
        return {
            "chance": list(names),
            "community": list(reversed(names)),
        }

    def _pop_stack(self, key: str) -> str:
        stack = self._stacks[key]
        if not stack:
            stack.extend(["money_get", "pass", "tax_pay"])
        return stack.pop(self._rng.randrange(len(stack)))

    def next_turn(self) -> None:
        if self.turn >= self.max_turns:
            raise GameOver("turn limit reached, no winner")
        self.turn += 1
        n = len(self.players)
        for _ in range(n):
            self.turn_index = (self.turn_index + 1) % n
            if not self.players[self.turn_index].bankrupt:
                return
        raise GameOver("all players bankrupt")

    def _remaining_players(self) -> int:
        return sum(1 for p in self.players if not p.bankrupt)

    def _current_player(self) -> Player:
        return self.players[self.turn_index]

    def run(self, steps: Optional[int] = 100) -> Log:
        for _ in range(steps):
            if self.is_won() or self._remaining_players() == 0:
                break
            try:
                self.next_turn()
            except GameOver:
                break
            self.run_step()
        return self.log

    def run_step(self) -> Log:
        """Drive one complete turn of the current player.

        Jailed players are resolved first: if they release (doubles or bail)
        they move this turn, otherwise they stay put for the round.
        """
        player = self._current_player()
        if player.bankrupt:
            return self.log
        if player.in_prison:
            if not self._handle_jail_turn(player):
                self._check_bankrupt()
                self._detect_winner()
                return self.log
        self.roll()
        self.advance(player, sum(self._last_roll))
        self._land(player)
        self._check_bankrupt()
        self._detect_winner()
        return self.log

    def roll(self) -> None:
        pair = roll_pair()
        self._last_roll = pair.values
        total = sum(pair.values)
        self.add_log("roll", f"{self._current_player().name} 掷出 {total}")

    def advance(self, player: Player, count: int) -> int:
        before = player.position
        after = (before + count) % self.board_size
        player.position = after
        if before + count >= self.board_size:
            player.add(100)
            self.add_log("起点奖金", f"{player.name} 经过起点 +¥100")
        return after

    def _land(self, player: Player) -> None:
        t = self.board.tile_by_index(player.position)
        cat = t.category
        if cat == TileType.CHANCE:
            self._draw_card(player, "chance")
        elif cat == TileType.COMMUNITY:
            self._draw_card(player, "community")
        elif cat == TileType.TAX:
            amt = t.price or 0
            if amt:
                paid = player.pay(amt)
                self.add_log("税收", f"{player.name} 缴纳税收 -{paid}")
            return
        elif cat == TileType.PROPERTY:
            self._land_property(player, t)
        elif cat == TileType.RAILROAD:
            self._land_railroad(player, t)
        elif cat == TileType.UTILITY:
            self._land_utility(player, t)
        elif cat == TileType.GO_JAIL:
            self._enter_jail(player)
        else:
            self.add_log(cat.name, f"{player.name} 到达 {t.name}")

    def _land_property(self, player: Player, t: object) -> None:
        if t.owner is None:
            if not self.auto_buy:
                if player.can_pay(t.price):
                    self.pending_purchase = (player, t)
                    self.add_log("buy", f"{player.name} 可购买 {t.name}（¥{t.price}）")
                return
            if player.can_pay(t.price):
                self._buy_asset(player, t)
            return
        if t.owner != player.name:
            if self._owns_group(player, t.group) and t.house == 0:
                self._build_house(player, t)
            else:
                self._pay_rent(player, t)
        elif t.house == 0 and self._owns_group(player, t.group):
            self._build_house(player, t)

    def _build_house(self, player: Player, t: object) -> None:
        cost = int(t.price * 0.5)
        if player.can_pay(cost):
            player.pay(cost)
            t.house += 1
            self.add_log("build", f"{player.name} 为 {t.name} 建房子（-{cost}）")

    def _pay_rent(self, player: Player, t: object) -> None:
        rent = (t.price // 10) * (1 + 2 * t.house)
        rent = max(rent, t.price // 10)
        self._collect_rent(player, t.owner, rent)

    def _land_railroad(self, player: Player, t: object) -> None:
        if self._buy_asset(player, t):
            return
        if t.owner != player.name:
            owned_railroads = sum(
                tile.category == TileType.RAILROAD and tile.owner == t.owner
                for tile in self.board.tiles
            )
            self._collect_rent(player, t.owner, 50 * owned_railroads)

    def _land_utility(self, player: Player, t: object) -> None:
        if self._buy_asset(player, t):
            return
        if t.owner != player.name:
            owned_utilities = sum(
                tile.category == TileType.UTILITY and tile.owner == t.owner
                for tile in self.board.tiles
            )
            multiplier = 10 if owned_utilities == 2 else 4
            self._collect_rent(player, t.owner, multiplier * sum(self._last_roll))

    def _buy_asset(self, player: Player, t: object) -> bool:
        if t.owner is not None:
            return False
        if player.can_pay(t.price):
            t.owner = player.name
            t.house = 0
            player.pay(t.price)
            player.properties.append(t.tile)
            self.add_log("buy", f"{player.name} 购买 {t.name}（-{t.price}）")
        return True

    def buy_pending_asset(self, player: Player) -> bool:
        """Buy the current landing asset when it was offered for manual purchase."""
        if self.pending_purchase is None:
            return False
        pending_player, tile = self.pending_purchase
        if pending_player is not player or tile.owner is not None:
            return False
        self.pending_purchase = None
        return self._buy_asset(player, tile)

    def decline_pending_asset(self, player: Player) -> bool:
        """Decline the current landing asset offered for manual purchase."""
        if self.pending_purchase is None or self.pending_purchase[0] is not player:
            return False
        self.pending_purchase = None
        self.add_log("buy", f"{player.name} 放弃购买 {self.board.tile_by_index(player.position).name}")
        return True

    def _collect_rent(self, player: Player, owner: Optional[str], rent: int) -> None:
        paid = player.pay(rent)
        if paid and owner is not None:
            cred = next((pl for pl in self.players if pl.name == owner), None)
            if cred is not None:
                cred.add(paid)
        self.add_log("rent", f"{player.name} 向 {owner} 交租 -{paid}")
        self._check_bankrupt()

    def _enter_jail(self, player: Player) -> None:
        player.in_prison = True
        player.jail_counter = 0
        player.jail_turn = 0
        self.add_log("坐牢", f"{player.name} 入监服刑，需掷骰/付赎金出狱")

    def _handle_jail_turn(self, player: Player) -> bool:
        """Resolve one turn while imprisoned.

        Returns True when the player releases and may still move this turn,
        False when they must stay put. Doubling rolls frees you immediately;
        otherwise a jail day is counted and after JAIL_MAX_TURNS days you may
        pay BAIL_COST to bail out.
        """
        if is_double(self._last_roll):
            player.in_prison = False
            player.jail_turn = 0
            self.add_log("出狱", f"{player.name} 掷出双骰，提前出狱")
            return True

        self.roll()
        player.jail_turn += 1
        player.jail_counter += 1
        if player.jail_turn >= JAIL_MAX_TURNS:
            if player.can_pay(BAIL_COST):
                player.pay(BAIL_COST)
                player.in_prison = False
                player.jail_turn = 0
                self.add_log("出狱", f"{player.name} 支付 {BAIL_COST} 元出狱")
                return True
            self.add_log("出狱", f"{player.name} 无力支付赎金，再停留一轮")
            return False
        return False

    def _draw_card(self, player: Player, key: str) -> None:
        name = self._pop_stack(key)
        handler = EVENTS.get(name)
        if handler is None:
            self.add_log(key, f"{player.name} 抽到 {name}（无事发生）")
            return
        result = handler(self, player)
        if isinstance(result, list):
            self.log.extend(result)

    def _owns_group(self, player: Player, group: str) -> bool:
        group_tiles = [
            self.board.tiles[i]
            for i in range(34)
            if self.board.tiles[i].category == TileType.PROPERTY
            and self.board.tiles[i].group == group
        ]
        return len(group_tiles) == 2 and all(t.owner == player.name for t in group_tiles)

    def _check_bankrupt(self) -> None:
        for pl in self.players:
            if pl.money == 0 and pl.wallets:
                pl.bankrupt = True

    def _detect_winner(self) -> None:
        if self.winner is not None:
            return
        alive = [p for p in self.players if not p.bankrupt]
        if len(alive) == 1:
            self.winner = alive[0]
            self.add_log("结束", f"{alive[0].name} 获胜!")

    def is_won(self) -> bool:
        return self.winner is not None
