# 大富翁 (Richman / Monopoly 风格棋类游戏)

基于 PySide6 (Qt6) 开发的回合制棋类游戏，玩法参照大宇大富翁4：骰子行进、
买地收租、建房子、随机事件、强盗集团、监狱/进房、税收、破产淘汰。

## 分层架构 (可测逻辑层 + PyQt6 表现层)

- game/ — 纯逻辑层 (无 GUI 依赖、可单测)
    money.py          Wallet 钱包 (富翁"整格钱包制")
    player.py         Player: 现金/持有地产/住房/牢房/破产
    board.py          34 格棋盘, 含 grid 坐标供 UI painters
    tiles_types.py    格子类型枚举
    dice.py           骰子 roll (2-12 分布)
    events.py         事件注册表 (红包/收税/进监狱...)
    game.py           引擎 : 回合、行进、交税收租、买地/建房子、破产检测、胜负
- ui.py             表现层 (Qt6 窗口)
- run.py            入口 (GUI / 文本模拟 自动切换)
- test_core.py      6 个核心逻辑测试

## 安装
    pip install PySide6 pytest

## 运行
    python monopoly/run.py                # gui (PySide6)
    QT_QPA_PLATFORM=offscreen python monopoly/run.py   # 文本模拟 (no display)
    python -m pytest -q                   # tests

## 说明
- 命名空间用 PySide6 (系统已装 6.11.2), API 与 PyQt6 几乎一致、可互换。
- 若切 PyQt6: 装 PyQt6, 把 ui.py 里 from PySide6... 改成 from PyQt6...
