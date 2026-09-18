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
from game.stock import StockMarket
from game.serial import rng_from_json, rng_to_json
from game.bank import LOAN_LIMIT, LOAN_RATE, LOAN_OVERDUE_TURNS, deposit_interest, loan_interest

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
        human_index: int = -1,
    ) -> None:
        self.log: Log = []
        self.board: Board = board or Board()
        self.players: List[Player] = list(players)
        self.max_turns = max_turns
        self.auto_buy = auto_buy
        self.board_size = len(self.board.tiles)
        self._seed = seed
        self._rng = random.Random(seed)
        self.turn_index = 0
        self.turn = 0
        self.phase = "setup"
        self.winner: Optional[Player] = None
        self.pending_purchase: Optional[tuple[Player, Tile]] = None
        self.human_index: int = human_index
        self._last_roll: Tuple[int, int] = (0, 0)
        self._stacks: dict[str, List[str]] = self._build_stacks()
        self.stock_market = StockMarket(seed)

    def start(self) -> None:
        self.board.reset_owned()
        self.log = []
        self.turn = 0
        self.turn_index = 0
        self.phase = "setup"
        self.winner = None
        self.pending_purchase = None
        self.stock_market = StockMarket(self._seed)
        for p in self.players:
            p.position = 0
            p.bankrupt = False
            p.in_prison = False
            p.jail_turn = 0
            p.bank = 0
            p.loan = 0
            p.loan_age = 0
        self.add_log("start", f"游戏开始，共 {len(self.players)} 名玩家")

    def add_log(self, phase: str, text: str) -> str:
        self.log.append((phase, text))
        return text

    def _build_stacks(self) -> dict[str, List[str]]:
        # 机会卡偏向“得利/出行”，社区卡偏向“开销/互助”，更贴近大富翁风味。
        chance = ["money_get", "windfall", "collect_all", "jail_go", "tax_pay", "pass"]
        community = ["bank_lotto", "house_fire", "pay_each", "tax_pay", "money_get", "pass"]
        return {
            "chance": list(chance),
            "community": list(community),
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
        self.stock_market.tick()
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
        pair = roll_pair(self._rng)
        self._last_roll = pair.values
        total = sum(pair.values)
        self.add_log("roll", f"{self._current_player().name} 掷出 {total}")

    def advance(self, player: Player, count: int) -> int:
        before = player.position
        after = (before + count) % self.board_size
        player.position = after
        if before + count >= self.board_size:
            player.add(2500)
            self.add_log("起点奖金", f"{player.name} 经过起点 +¥2500")
            self.apply_interest(player)
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
                if player.is_bot:
                    if self._should_bot_buy(player, t):
                        self._buy_asset(player, t)
                    return
                if player.can_pay(t.price):
                    self.pending_purchase = (player, t)
                    self.add_log("buy", f"{player.name} 可购买 {t.name}（¥{t.price}）")
                return
            if self._should_bot_buy(player, t):
                self._buy_asset(player, t)
            return
        if t.owner == player.name:
            # 自己的地：拥有整个集团且房屋未满时可继续盖房
            if self._owns_group(player, t.group) and t.house < 4:
                self._build_house(player, t)
            else:
                self.add_log("地产", f"{player.name} 回到自己的地产 {t.name}")
            return
        # 别人的地：交租
        self._pay_rent(player, t)

    def _should_bot_buy(self, player: Player, t: object) -> bool:
        if not player.can_pay(t.price):
            return False
        group_owned = any(
            self.board.tiles[property_id].group == t.group
            for property_id in player.properties
        )
        if group_owned:
            return True
        remaining_cash = player.money - t.price
        reserve = max(4000, t.price // 3)
        return remaining_cash >= reserve and t.price <= player.money * 0.9

    def _build_house(self, player: Player, t: object) -> None:
        cost = int(t.price * 0.5)
        if player.can_pay(cost) and player.money - cost >= 3000:
            player.pay(cost)
            t.house += 1
            self.add_log("build", f"{player.name} 为 {t.name} 建房子（-{cost}）")

    def _pay_rent(self, player: Player, t: object) -> None:
        base = t.price // 20
        rent = base * (1 + 2 * t.house)
        self._collect_rent(player, t.owner, rent)

    def _land_railroad(self, player: Player, t: object) -> None:
        if self._buy_asset(player, t):
            return
        if t.owner != player.name:
            owned_railroads = sum(
                tile.category == TileType.RAILROAD and tile.owner == t.owner
                for tile in self.board.tiles
            )
            self._collect_rent(player, t.owner, 200 * owned_railroads)

    def _land_utility(self, player: Player, t: object) -> None:
        if self._buy_asset(player, t):
            return
        if t.owner != player.name:
            owned_utilities = sum(
                tile.category == TileType.UTILITY and tile.owner == t.owner
                for tile in self.board.tiles
            )
            multiplier = 100 if owned_utilities == 2 else 40
            self._collect_rent(player, t.owner, multiplier * sum(self._last_roll))

    def _buy_asset(self, player: Player, t: object) -> bool:
        """Purchase an unowned tile; returns True only when it succeeds."""
        if t.owner is not None:
            return False
        if not player.can_pay(t.price):
            return False
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

    # ------------------------------------------------------------- stocks
    def buy_stock(self, player: Player, code: str, shares: int) -> tuple[bool, str]:
        """Buy ``shares`` of ``code`` with cash. Returns (ok, message)."""
        stock = self.stock_market.get(code)
        if stock is None or shares <= 0:
            return False, "无效的股票代码或数量"
        cost = stock.price * shares
        if not player.can_pay(cost):
            return False, f"现金不足（需 ¥{cost}）"
        player.pay(cost)
        player.stocks[code] = player.stocks.get(code, 0) + shares
        self.add_log("股票", f"{player.name} 买入 {stock.name} ×{shares}（-¥{cost}）")
        return True, f"买入 {stock.name} ×{shares}"

    def sell_stock(self, player: Player, code: str, shares: int) -> tuple[bool, str]:
        """Sell ``shares`` of ``code`` for cash. Returns (ok, message)."""
        stock = self.stock_market.get(code)
        if stock is None or shares <= 0:
            return False, "无效的股票代码或数量"
        held = player.stocks.get(code, 0)
        if held < shares:
            return False, f"持股不足（持有 {held} 股）"
        revenue = stock.price * shares
        player.add(revenue)
        left = held - shares
        if left:
            player.stocks[code] = left
        else:
            player.stocks.pop(code, None)
        self.add_log("股票", f"{player.name} 卖出 {stock.name} ×{shares}（+¥{revenue}）")
        return True, f"卖出 {stock.name} ×{shares}"

    # ------------------------------------------------------------- banking
    def deposit(self, player: Player, amount: int) -> tuple[bool, str]:
        """Move cash into the bank account. Returns (ok, message)."""
        if amount <= 0:
            return False, "金额无效"
        if player.money < amount:
            return False, f"现金不足（现有 ¥{player.money}）"
        player.pay(amount)
        player.bank += amount
        self.add_log("银行", f"{player.name} 存入 ¥{amount}（存款 ¥{player.bank}）")
        return True, f"存入 ¥{amount}"

    def withdraw(self, player: Player, amount: int) -> tuple[bool, str]:
        """Move cash out of the bank account. Returns (ok, message)."""
        if amount <= 0:
            return False, "金额无效"
        if player.bank < amount:
            return False, f"存款不足（现有 ¥{player.bank}）"
        player.bank -= amount
        player.add(amount)
        self.add_log("银行", f"{player.name} 取出 ¥{amount}（存款 ¥{player.bank}）")
        return True, f"取出 ¥{amount}"

    def borrow(self, player: Player, amount: int) -> tuple[bool, str]:
        """Borrow cash from the bank (interest accrues every turn)."""
        if amount <= 0:
            return False, "金额无效"
        if player.loan + amount > LOAN_LIMIT:
            return False, f"超过贷款上限 ¥{LOAN_LIMIT}（已贷 ¥{player.loan}）"
        player.add(amount)
        player.loan += amount
        self.add_log("银行", f"{player.name} 贷款 ¥{amount}（利率 {LOAN_RATE * 100:.0f}%/圈）")
        return True, f"贷款 ¥{amount}"

    def repay(self, player: Player, amount: int) -> tuple[bool, str]:
        """Repay (part of) the outstanding loan. Returns (ok, message)."""
        if amount <= 0:
            return False, "金额无效"
        if player.loan <= 0:
            return False, "没有贷款"
        amount = min(amount, player.loan)
        if player.money < amount:
            return False, f"现金不足（需 ¥{amount}）"
        player.pay(amount)
        player.loan -= amount
        if player.loan == 0:
            player.loan_age = 0
        self.add_log("银行", f"{player.name} 还款 ¥{amount}（剩余贷款 ¥{player.loan}）")
        return True, f"还款 ¥{amount}"

    def apply_interest(self, player: Player) -> None:
        """Settle one player's deposit / loan interest when they pass GO."""
        if player.bankrupt:
            return
        if player.bank > 0:
            interest = deposit_interest(player.bank)
            if interest > 0:
                player.bank += interest
                self.add_log("银行", f"{player.name} 存款利息 +¥{interest}")
        if player.loan > 0:
            player.loan_age += 1
            overdue = player.loan_age >= LOAN_OVERDUE_TURNS
            interest = loan_interest(player.loan, overdue)
            if interest > 0:
                player.loan += interest
                tag = "（逾期 20%）" if overdue else ""
                self.add_log("银行", f"{player.name} 贷款利息 +¥{interest}{tag}")

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
        if not group:
            return False
        group_tiles = [
            t for t in self.board.tiles
            if t.category == TileType.PROPERTY and t.group == group
        ]
        return len(group_tiles) > 0 and all(t.owner == player.name for t in group_tiles)

    def _check_bankrupt(self) -> None:
        for pl in self.players:
            if pl.money == 0 and pl.bank == 0 and pl.wallets:
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

    # ------------------------------------------------------------ serialise
    def to_dict(self) -> dict:
        pending = None
        if self.pending_purchase is not None:
            pending = [self.pending_purchase[0].name, self.pending_purchase[1].tile]
        return {
            "players": [p.to_dict() for p in self.players],
            "board": self.board.to_dict(),
            "stock_market": self.stock_market.to_dict(),
            "turn": self.turn,
            "turn_index": self.turn_index,
            "phase": self.phase,
            "winner": self.winner.name if self.winner else None,
            "pending_purchase": pending,
            "log": [[phase, text] for phase, text in self.log],
            "last_roll": list(self._last_roll),
            "stacks": {k: list(v) for k, v in self._stacks.items()},
            "max_turns": self.max_turns,
            "auto_buy": self.auto_buy,
            "seed": self._seed,
            "rng_state": rng_to_json(self._rng),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Game":
        players = [Player.from_dict(p) for p in data["players"]]
        board = Board.from_dict(data["board"])
        g = cls(
            players,
            board=board,
            seed=data.get("seed"),
            max_turns=data.get("max_turns", 1000),
            auto_buy=data.get("auto_buy", True),
        )
        g.stock_market = StockMarket.from_dict(data["stock_market"])
        g.turn = data.get("turn", 0)
        g.turn_index = data.get("turn_index", 0)
        g.phase = data.get("phase", "setup")
        winner_name = data.get("winner")
        g.winner = next((p for p in g.players if p.name == winner_name), None) if winner_name else None
        pending = data.get("pending_purchase")
        if pending:
            pname, tidx = pending
            player = next((p for p in g.players if p.name == pname), None)
            g.pending_purchase = (player, g.board.tiles[tidx]) if player is not None else None
        g.log = [(p, t) for p, t in data.get("log", [])]
        g._last_roll = tuple(data.get("last_roll", [0, 0]))
        g._stacks = {k: list(v) for k, v in data.get("stacks", {}).items()}
        rng_from_json(g._rng, data["rng_state"])
        return g
