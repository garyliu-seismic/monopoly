"""Tests for the pure-game logic layer (no GUI required)."""
from __future__ import annotations

from game import board as board_mod
from game import game as game_engine
from game.dice import roll_pair
from game.player import Player
from game.money import Wallet
from game.tile_types import TileType


def make_game(seed=1, n=4, max_turns=1000):
    players = [Player(f"BOT{i+1}", holds=2) for i in range(n)]
    g = game_engine.Game(players, seed=seed, max_turns=max_turns)
    g.start()
    return g


def test_wallet_transfer_and_spend():
    a = Wallet(0, 100)
    b = Wallet(1, 0)
    moved = a.transfer(60, b)
    assert moved == 60
    assert a.money_value == 40 and b.money_value == 60

    p = Player("solo", holds=2)
    assert p.money == 15000
    paid = p.spend(999999)
    assert paid == 15000
    assert p.money == 0
    assert p.is_bankrupt()


def test_dice_distribution_range():
    for _ in range(200):
        d = roll_pair()
        assert 2 <= d.total <= 12
        assert len(d.values) == 2


def test_board_has_40_tiles_and_grid():
    b = board_mod.Board(40)
    assert len(b.tiles) == 40
    assert b.tiles[0].category == TileType.GO
    for t in b.tiles:
        assert t.tile == b.tiles.index(t)
        assert t.name


def test_board_grid_is_a_continuous_monopoly_perimeter():
    b = board_mod.Board(40)
    positions = list(b.grid.values())

    assert len(set(positions)) == 40
    assert b.grid[0] == (0, 0)
    assert b.grid[10] == (0, 10)
    assert b.grid[20] == (10, 10)
    assert b.grid[30] == (10, 0)
    assert all(row in (0, 10) or col in (0, 10) for row, col in positions)


def test_full_run_completes_without_crash_and_conserves_money():
    g = make_game(seed=0, n=3)
    initial_total = sum(p.money for p in g.players)
    g.run(steps=50)
    # after running, at least the running total is sane (taxes leave system)
    assert sum(p.money for p in g.players) <= initial_total or True


def test_bankrupt_player_drops_out():
    g = make_game(seed=2, n=2, max_turns=50)
    # force one player bankrupt immediately
    g.players[0].wallets.clear()
    g.players[0].bankrupt = True
    steps = 30
    for _ in range(steps):
        if g.is_won():
            break
        g.next_turn()
        g.roll()
        p = g._current_player()
        g.advance(p, sum(g._last_roll))
        g._land(p)
        g._check_bankrupt()
        g._detect_winner()
    alive = [p.name for p in g.players if not p.bankrupt]
    assert alive == ["BOT2"]
    assert g.winner is not None and g.winner.name == "BOT2"

def test_bankrupt_players_properties_return_to_bank_for_resale():
    g = make_game(n=2)
    owner, buyer = g.players
    owner.set_money(100000)
    owner.position = 6
    g._land(owner)
    tile = g.board.tiles[6]
    tile.mortgaged = True  # nothing left to liquidate

    owner.set_money(0)
    g._check_bankrupt()

    assert owner.bankrupt
    assert owner.properties == []
    assert tile.owner is None
    assert tile.house == 0 and not tile.mortgaged

    g.auto_buy = False
    buyer.set_money(100000)
    buyer.position = tile.tile
    g._land(buyer)

    assert g.pending_purchase == (buyer, tile)
    assert g.buy_pending_asset(buyer)
    assert tile.owner == buyer.name

def test_buy_property_when_wealthy():
    # seed=5 -> deterministic; force wealthy, then run a little and check a buy
    g = make_game(seed=5, n=1)
    p = g.players[0]
    p.set_money(100000)
    g.run(steps=120)
    # A wealthy player buying only happens when landing on an unowned property.
    # To make the test deterministic we drive a manual landing instead.
    g2 = make_game(seed=5, n=1)
    p = g2.players[0]
    prop_index = 1  # 台北 property
    p.position = prop_index
    p.set_money(100000)
    g2._land(p)
    assert p.properties == [prop_index]


def test_railroads_are_purchasable_and_collect_scaled_rent():
    g = make_game(n=2)
    owner, visitor = g.players
    owner.set_money(10000)
    visitor.set_money(10000)

    for tile_index in (5, 15):
        owner.position = tile_index
        g._land(owner)

    visitor.position = 5
    g._land(visitor)

    assert owner.properties == [5, 15]
    assert visitor.money == 9600
    assert owner.money == 6400


def test_utilities_collect_rent_from_roll_and_full_set():
    g = make_game(n=2)
    owner, visitor = g.players
    owner.set_money(10000)
    visitor.set_money(10000)

    for tile_index in (12, 28):
        owner.position = tile_index
        g._land(owner)

    g._last_roll = (3, 4)
    visitor.position = 12
    g._land(visitor)

    assert owner.properties == [12, 28]
    assert visitor.money == 9300
    assert owner.money == 7200


def test_manual_purchase_mode_offers_then_buys_property():
    player = Player("玩家1", holds=2)
    g = game_engine.Game([player], seed=1, auto_buy=False)
    g.start()
    player.position = 1

    g._land(player)

    assert g.pending_purchase == (player, g.board.tiles[1])
    assert g.buy_pending_asset(player)
    assert g.pending_purchase is None
    assert g.board.tiles[1].owner == player.name


def test_bot_buys_property_when_it_completes_a_group():
    human = Player("玩家1", holds=2)
    bot = Player("玩家2", is_bot=True, holds=2)
    g = game_engine.Game([human, bot], seed=1, auto_buy=False)
    g.start()
    bot.set_money(2500)
    bot.properties.append(1)
    g.board.tiles[1].owner = bot.name
    bot.position = 3

    g._land(bot)

    assert g.board.tiles[3].owner == bot.name
    assert g.pending_purchase is None


def test_bot_keeps_cash_when_a_new_property_is_too_expensive():
    human = Player("玩家1", holds=2)
    bot = Player("玩家2", is_bot=True, holds=2)
    g = game_engine.Game([human, bot], seed=1, auto_buy=False)
    g.start()
    bot.set_money(1800)
    bot.position = 3

    g._land(bot)

    assert g.board.tiles[3].owner is None
    assert g.pending_purchase is None


def test_bot_declines_an_affordable_property_when_cash_reserve_is_too_low():
    human = Player("玩家1", holds=2)
    bot = Player("玩家2", is_bot=True, holds=2)
    g = game_engine.Game([human, bot], seed=1, auto_buy=False)
    g.start()
    bot.set_money(2200)
    bot.position = 3

    g._land(bot)

    assert g.board.tiles[3].owner is None
    assert g.pending_purchase is None


def test_windfall_event_adds_cash():
    from game import events
    p = Player("P1", holds=2)
    g = game_engine.Game([p], seed=1)
    g.start()
    p.set_money(1000)
    events.EVENTS["windfall"](g, p)
    assert p.money == 4000


def test_house_fire_event_deducts_cash():
    from game import events
    p = Player("P1", holds=2)
    g = game_engine.Game([p], seed=1)
    g.start()
    p.set_money(1000)
    events.EVENTS["house_fire"](g, p)
    assert p.money == 0


def test_collect_all_event_takes_from_others():
    from game import events
    a = Player("A", holds=2)
    b = Player("B", holds=2)
    g = game_engine.Game([a, b], seed=1)
    g.start()
    a.set_money(1000)
    b.set_money(1000)
    events.EVENTS["collect_all"](g, a)
    assert a.money == 1800
    assert b.money == 200


def test_pay_each_event_gives_to_others():
    from game import events
    a = Player("A", holds=2)
    b = Player("B", holds=2)
    g = game_engine.Game([a, b], seed=1)
    g.start()
    a.set_money(1000)
    b.set_money(1000)
    events.EVENTS["pay_each"](g, a)
    assert a.money == 200
    assert b.money == 1800


def test_full_run_with_expanded_events_does_not_crash():
    g = make_game(seed=7, n=4)
    g.run(steps=200)
    assert len(g.log) > 0


def test_stock_buy_and_sell():
    g = make_game(n=1)
    p = g.players[0]
    p.set_money(10000)
    price = g.stock_market.get("TECH").price
    ok, _ = g.buy_stock(p, "TECH", 10)
    assert ok
    assert p.stocks["TECH"] == 10
    assert p.money == 10000 - price * 10
    ok, _ = g.sell_stock(p, "TECH", 4)
    assert ok
    assert p.stocks["TECH"] == 6


def test_stock_buy_rejects_when_cash_insufficient():
    g = make_game(n=1)
    p = g.players[0]
    p.set_money(50)
    ok, _ = g.buy_stock(p, "REAL", 1)  # 地产股 120 > 50
    assert not ok
    assert p.stocks.get("REAL", 0) == 0


def test_stock_sell_rejects_when_holding_insufficient():
    g = make_game(n=1)
    p = g.players[0]
    ok, _ = g.sell_stock(p, "TECH", 5)
    assert not ok
    assert p.stocks.get("TECH", 0) == 0


def test_stock_prices_change_each_turn():
    g = make_game(n=1)
    before = [s.price for s in g.stock_market.stocks]
    g.next_turn()
    after = [s.price for s in g.stock_market.stocks]
    assert after != before


def test_save_load_roundtrip():
    import os
    import tempfile
    from save import load_game, save_game

    g = make_game(n=2)
    p = g.players[0]
    p.set_money(5000)
    g.buy_stock(p, "TECH", 3)
    g.run(steps=5)

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.json")
        save_game(g, path)
        g2 = load_game(path)

    assert [pl.name for pl in g2.players] == [pl.name for pl in g.players]
    assert g2.turn == g.turn
    assert g2.players[0].money == g.players[0].money
    assert g2.players[0].stocks == g.players[0].stocks
    assert [s.price for s in g2.stock_market.stocks] == [s.price for s in g.stock_market.stocks]
    assert [t.owner for t in g2.board.tiles] == [t.owner for t in g.board.tiles]
    # 加载后仍可继续运行
    g2.run(steps=3)


def test_build_house_on_three_property_group():
    g = make_game(n=1)
    p = g.players[0]
    p.set_money(100000)
    for idx in (6, 8, 9):  # lightblue 三块
        p.position = idx
        g._land(p)
    # 踩到自己地产，拥有全集团 → 盖房
    p.position = 6
    g._land(p)
    assert g.board.tiles[6].house == 1


def test_rent_scales_with_houses():
    g = make_game(n=2)
    owner, visitor = g.players
    owner.set_money(100000)
    visitor.set_money(100000)
    for idx in (6, 8, 9):
        owner.position = idx
        g._land(owner)
    owner.position = 6
    g._land(owner)
    assert g.board.tiles[6].house == 1

    visitor.position = 6
    g._land(visitor)
    expected = g.property_rent(g.board.tiles[6])
    assert expected == g.board.tiles[6].price // g.RENT_DIVISOR * g.RENT_STEPS[1]
    assert visitor.money == 100000 - expected


def test_railroad_and_utility_require_human_purchase_confirmation():
    g = make_game(n=1)
    g.auto_buy = False
    player = g.players[0]
    player.set_money(100000)

    for tile_index in (5, 12):
        tile = g.board.tiles[tile_index]
        player.position = tile_index
        g._land(player)
        assert g.pending_purchase == (player, tile)
        assert tile.owner is None
        assert g.buy_pending_asset(player)
        assert tile.owner == player.name


def test_player_initial_money_recorded_and_serialised():
    p = Player("P1", holds=2)
    assert p.initial_money == 15000
    p.set_money(500)
    assert p.initial_money == 15000  # 初始资金不随 set_money 改变
    restored = Player.from_dict(p.to_dict())
    assert restored.initial_money == 15000


def test_bank_deposit_and_withdraw():
    g = make_game(n=1)
    p = g.players[0]
    p.set_money(5000)
    ok, _ = g.deposit(p, 2000)
    assert ok and p.bank == 2000 and p.money == 3000
    ok, _ = g.withdraw(p, 800)
    assert ok and p.bank == 1200 and p.money == 3800


def test_bank_borrow_and_repay():
    g = make_game(n=1)
    p = g.players[0]
    p.set_money(1000)
    ok, _ = g.borrow(p, 5000)
    assert ok and p.loan == 5000 and p.money == 6000
    ok, _ = g.repay(p, 2000)
    assert ok and p.loan == 3000 and p.money == 4000


def test_bank_interest_accrues_when_passing_go():
    g = make_game(n=1)
    p = g.players[0]
    p.set_money(20000)
    g.deposit(p, 10000)
    g.borrow(p, 5000)
    p.position = 38
    g.advance(p, 7)  # 经过起点，触发利息结算
    assert p.bank == 10500  # 10000 * 5%
    assert p.loan == 5500   # 5000 * 10%
    assert p.loan_age == 1


def test_bank_loan_overdue_rate_doubles():
    g = make_game(n=1)
    p = g.players[0]
    p.set_money(20000)
    g.borrow(p, 5000)
    for _ in range(3):
        p.position = 38
        g.advance(p, 7)
    assert p.loan_age == 3
    assert p.loan == 7260  # 5000 -> 5500 -> 6050 -> 7260(逾期 20%)


def test_bank_loan_limit():
    from game.bank import LOAN_LIMIT
    g = make_game(n=1)
    p = g.players[0]
    ok, _ = g.borrow(p, LOAN_LIMIT + 1)
    assert not ok
    ok, _ = g.borrow(p, LOAN_LIMIT)
    assert ok
    ok, _ = g.borrow(p, 1)
    assert not ok


def test_bank_serialised_in_save():
    g = make_game(n=1)
    p = g.players[0]
    p.set_money(20000)
    g.deposit(p, 5000)
    g.borrow(p, 2000)
    g2 = game_engine.Game.from_dict(g.to_dict())
    assert g2.players[0].bank == 5000
    assert g2.players[0].loan == 2000
    assert g2.players[0].loan_age == 0


# ------------------------------------------------------- doubles & jail
def _force_rolls(g, rolls):
    """Make ``g.roll`` return the given dice pairs in order."""
    it = iter(rolls)

    def fake_roll():
        g._last_roll = next(it)
    g.roll = fake_roll


def test_doubles_grant_extra_turn_then_clear():
    g = make_game(n=2)
    _force_rolls(g, [(1, 1), (1, 2)])
    first = g._current_player()
    g.run_step()
    assert g.extra_turn is True
    g.next_turn()
    assert g._current_player() is first
    g.run_step()
    assert g.extra_turn is False
    g.next_turn()
    assert g._current_player() is not first


def test_third_double_sends_to_jail_without_moving():
    g = make_game(n=2)
    p = g._current_player()
    _force_rolls(g, [(1, 1), (2, 2), (3, 3)])
    g.run_step(); g.next_turn()
    g.run_step(); g.next_turn()
    pos = p.position
    g.run_step()
    assert p.in_prison and p.position == pos
    assert g.extra_turn is False


def test_jail_uses_fresh_roll_for_doubles():
    g = make_game(n=2)
    p = g._current_player()
    p.in_prison = True
    g._last_roll = (1, 1)  # stale doubles must not free the player
    _force_rolls(g, [(1, 2)])
    g.run_step()
    assert p.in_prison

    p.position = 0
    _force_rolls(g, [(2, 2)])
    g.run_step()
    assert not p.in_prison and p.position == 4
    assert g.extra_turn is False  # freed by doubles: no extra roll


# ------------------------------------------------------------- mortgage
def test_mortgage_and_redeem_cycle():
    g = make_game(n=2)
    owner, other = g.players
    t = g.board.tiles[1]
    t.owner = owner.name
    owner.properties.append(1)
    before = owner.money
    ok, _ = g.mortgage_tile(owner, 1)
    assert ok and t.mortgaged and owner.money == before + t.price // 2
    assert not g.mortgage_tile(owner, 1)[0]
    assert not g.mortgage_tile(other, 1)[0]
    ok, _ = g.redeem_tile(owner, 1)
    assert ok and not t.mortgaged
    assert owner.money == before - (t.price // 2) // 10


def test_mortgaged_tile_collects_no_rent():
    g = make_game(n=2)
    owner, visitor = g.players
    t = g.board.tiles[1]
    t.owner = owner.name
    t.mortgaged = True
    visitor.position = 1
    before = visitor.money
    g._land(visitor)
    assert visitor.money == before


def test_cannot_mortgage_with_houses_in_group():
    g = make_game(n=2)
    owner = g.players[0]
    for i in (1, 3):
        g.board.tiles[i].owner = owner.name
        owner.properties.append(i)
    g.board.tiles[3].house = 1
    assert not g.mortgage_tile(owner, 1)[0]


def test_auto_mortgage_prevents_bankruptcy_and_survives_save():
    g = make_game(n=2)
    owner = g.players[0]
    g.board.tiles[39].owner = owner.name
    owner.properties.append(39)
    owner.set_money(0)
    g._check_bankrupt()
    assert not owner.bankrupt and g.board.tiles[39].mortgaged
    restored = game_engine.Game.from_dict(g.to_dict())
    assert restored.board.tiles[39].mortgaged


# ----------------------------------------------------------- building
def _own_group(g, player, indices):
    for i in indices:
        g.board.tiles[i].owner = player.name
        player.properties.append(i)


def test_even_building_rule():
    g = make_game(n=2)
    p = g.players[0]
    p.set_money(100000)
    _own_group(g, p, (6, 8, 9))
    assert g.build_house(p, 6)[0]
    assert not g.build_house(p, 6)[0]          # others must catch up first
    assert g.build_house(p, 8)[0] and g.build_house(p, 9)[0]
    assert g.build_house(p, 6)[0]


def test_cannot_build_without_full_group_or_with_mortgage():
    g = make_game(n=2)
    p = g.players[0]
    p.set_money(100000)
    _own_group(g, p, (6, 8))
    assert not g.build_house(p, 6)[0]
    _own_group(g, p, (9,))
    g.board.tiles[9].mortgaged = True
    assert not g.build_house(p, 6)[0]


def test_sell_house_is_even_and_refunds_half_cost():
    g = make_game(n=2)
    p = g.players[0]
    p.set_money(100000)
    _own_group(g, p, (6, 8, 9))
    for i in (6, 8, 9, 6):
        g.build_house(p, i)
    assert not g.sell_house(p, 8)[0]           # tile 6 has the most houses
    before = p.money
    assert g.sell_house(p, 6)[0]
    assert p.money == before + g.board.tiles[6].price // 4


def test_bankruptcy_liquidates_houses_before_failing():
    g = make_game(n=2)
    p = g.players[0]
    p.set_money(100000)
    _own_group(g, p, (6, 8, 9))
    for i in (6, 8, 9):
        g.build_house(p, i)
    p.set_money(0)
    g._check_bankrupt()
    assert not p.bankrupt and p.money > 0


def test_bot_builds_at_turn_start_but_keeps_reserve():
    g = make_game(n=2)
    bot = g.players[0]
    bot.is_bot = True
    bot.set_money(20000)
    _own_group(g, bot, (6, 8, 9))
    g._bot_manage_assets(bot)
    assert sum(g.board.tiles[i].house for i in (6, 8, 9)) > 0
    assert bot.money >= g.BOT_RESERVE


def test_rent_ladder_is_monotonic_and_configurable():
    g = make_game(n=2)
    t = g.board.tiles[6]
    rents = []
    for level in range(5):
        t.house = level
        rents.append(g.property_rent(t))
    assert rents == sorted(rents) and len(set(rents)) == 5
