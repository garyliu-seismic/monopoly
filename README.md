# 大富翁 (Richman / Monopoly 风格棋类游戏)

基于 PySide6 (Qt6) 开发的回合制棋类游戏，玩法参照大宇大富翁 4：骰子行进、买地收租、建房子、随机事件、强盗集团、监狱 / 进房、税收、破产淘汰。

## 分层架构 (可测逻辑层 + PySide6 / PyQt6 表现层)

- `game/` — 纯逻辑层（无 GUI 依赖、可单测）
- `ui.py` — 表现层（PySide6 主窗口），驱动逻辑层

## 目录结构

```
monopoly/
├── game/            # 纯逻辑层 (无 GUI 依赖，可独立单测)
│   ├── money.py     #   Wallet 钱包 (富翁"整格钱包制")
│   ├── player.py    #   Player: 现金 / 持有地产 / 住房 / 牢房 / 破产 / 股票
│   ├── dice.py      #   骰子 roll / 校验
│   ├── tile_types.py#   地图格子类型枚举 (TileType)
│   ├── board.py     #   地图 (34 格) / 格子所有权
│   ├── events.py    #   随机事件表 (机会 / 命运 / 强盗集团 / 监狱)
│   ├── jail.py      #   监狱 / 进房规则 (入狱、掷骰出狱、赎金)
│   ├── stock.py     #   股票市场 (股价随机游走、买卖)
│   ├── serial.py    #   随机数状态序列化助手
│   └── game.py      #   回合主循环、胜负判定、收租 / 缴税 / 破产 / 股票
├── ui.py            #   PySide6 表现层 (主窗口)
├── sound.py         #   程序化音效合成 (无外部音频资源)
├── save.py          #   存档 / 读档 (JSON)
├── run.py           #   程序入口 (GUI，无显示则降级为纯文本模拟)
└── test_core.py     #   逻辑层单测 (pytest)
```

## 表现层增强

- **人物头像**：每位玩家有专属 emoji 头像 + 配色，显示在棋盘棋子与左侧玩家卡片上。
- **音效**：掷骰、移动、购买、收租、入狱、事件、胜利均有音效（`sound.py` 本地合成 WAV，无需外部资源；菜单“游戏 → 音效”可开关）。
- **骰子显示**：右侧控制区实时显示两颗骰子的点数。
- **动画**：玩家棋子逐格行走动画（含步进音效）；地产格上的白色方块表示房屋数量。
- **股票面板**：左侧显示四支股票实时报价与我的持仓，可直接买入/卖出。
- **存档 / 读档**：菜单“游戏 → 存档 / 读档”，把整局（玩家、棋盘、股票、随机数状态）保存为 JSON 并随时恢复。

## 随机事件

机会 / 社区卡共 8 种：`money_get`（+400）、`windfall`（+800）、`collect_all`（向每人收 200）、`jail_go`（入狱）、`tax_pay`（-300）、`bank_lotto`（+500）、`house_fire`（-600）、`pay_each`（给每人 200）。

## 核心玩法

- **骰子行进**：玩家掷骰子，沿大富翁地图行进 N 格，经过起点额外 +¥100。
- **买地收租**：踩到未持有地产可购买；被他人地产踩中需缴纳租金（拥有全集团可建房子，租金翻倍）。
- **建房子**：同属一个集团的地产全部拥有且房屋数量为 0 时，可用半价（`price * 0.5`）建房。
- **随机事件**：机会 / 命运卡片（`money_get` / `bank_lotto` 等），以及强盗集团抢劫。
- **监狱 / 进房**：停靠在"进房"（GO_JAIL）触放入狱；入狱后掷骰得到对子立刻出狱，否则按天累计，满 `JAIL_MAX_TURNS`（3 天）后可支付 `BAIL_COST`（50 元）赎金出狱，无力支付则再停留一天。
- **税收**：经过"税收"格按固定金额缴税。
- **股票交易**：四支股票（科技 / 银行 / 能源 / 地产）每回合价格随机波动（±10），玩家可用现金买卖，赚取差价。
- **破产淘汰**：现金耗尽（`money == 0` 且仍有钱包）即标记为破产出局。

## 游戏流程

回合主循环（`Game.run_step`）顺序执行：

```
roll()  ->  advance()  ->  _land()  ->  pay/breakrupt  ->  _detect_winner()
```

 jailed player：回合开始时先由 `_handle_jail_turn()` 裁决，释放则行进、否则跳过本轮。

## 快速开始

```bash
# 安装依赖
pip install pyside6 pytest

# 运行游戏（无显示设备降级为文本模拟）
python run.py

# 运行测试
pytest test_core.py -v
```

## 测试

逻辑层（`game/`）不依赖任何 GUI，可直接用 pytest 单测：

- `test_wallet_transfer_and_spend` — Wallet 转账 / 玩家消费至破产
- `test_dice_distribution_range` — 骰子分布 (2..12)
- `test_board_has_34_tiles_and_grid` — 地图 34 格 + GO 首格
- `test_full_run_completes_without_crash_and_conserves_money` — 整局运行
- `test_bankrupt_player_drops_out` — 破产玩家出局、判定赢家
- `test_buy_property_when_wealthy` — 富豪玩家购买地产
- `test_windfall_event_adds_cash` / `test_house_fire_event_deducts_cash` — 新增事件
- `test_collect_all_event_takes_from_others` / `test_pay_each_event_gives_to_others` — 多人交互事件
- `test_stock_buy_and_sell` / `test_stock_buy_rejects_when_cash_insufficient` — 股票买卖
- `test_stock_sell_rejects_when_holding_insufficient` / `test_stock_prices_change_each_turn` — 股票规则
- `test_save_load_roundtrip` — 存档 / 读档往返一致

---
本项目采用纯逻辑层与表现层分离设计，便于测试与二次开发。
