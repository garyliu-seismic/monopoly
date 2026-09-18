"""Board *map* catalog (pure logic, testable without a QApplication).

A *map* is a named layout of tiles mirrored from ``game.game.Game``.
The UI menu switches maps at runtime via :data:`MAPS` / :func:`by_key`.

Maps ship in three flavours (the three referenced games):

* ``taiwan`` – Taiwan-city map (the original layout).
* ``world``  – world-landmarks map.
* ``gpa``    – a lightweight "GPA / campus" map for variety.

Raw layouts are mirrored in ``data/maps/*.json`` for non-Python authors, but
the Python registry here is always the source of truth for tests so they never
touch the filesystem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


def _tile(name: str, category: str, group: str, price: int) -> Tuple[str, str, str, int]:
    return (name, category, group, price)


# ---------------------------------------------------------- map: taiwan (default)
TAIWAN_TILES: List[Tuple[str, str, str, int]] = [
    _tile("起点", "GO", "", 0),
    _tile("基隆", "PROPERTY", "brown", 1500),
    _tile("社区", "COMMUNITY", "", 0),
    _tile("苗栗", "PROPERTY", "brown", 2000),
    _tile("所得税", "TAX", "", 800),
    _tile("台北车站", "RAILROAD", "railroad", 2000),
    _tile("彰化", "PROPERTY", "lightblue", 1500),
    _tile("机会", "CHANCE", "", 0),
    _tile("云林", "PROPERTY", "lightblue", 2000),
    _tile("嘉义", "PROPERTY", "lightblue", 2500),
    _tile("监狱", "JAIL", "", 0),
    _tile("屏东", "PROPERTY", "pink", 3000),
    _tile("电力公司", "UTILITY", "utility", 1500),
    _tile("台东", "PROPERTY", "pink", 3500),
    _tile("宜兰", "PROPERTY", "pink", 4000),
    _tile("台中车站", "RAILROAD", "railroad", 2000),
    _tile("花莲", "PROPERTY", "orange", 5000),
    _tile("社区", "COMMUNITY", "", 0),
    _tile("南投", "PROPERTY", "orange", 5500),
    _tile("台中", "PROPERTY", "orange", 6000),
    _tile("免费停车", "FREE", "", 0),
    _tile("台南", "PROPERTY", "red", 7000),
    _tile("机会", "CHANCE", "", 0),
    _tile("新竹", "PROPERTY", "red", 7500),
    _tile("桃园", "PROPERTY", "red", 8000),
    _tile("高雄车站", "RAILROAD", "railroad", 2000),
    _tile("高雄", "PROPERTY", "yellow", 9000),
    _tile("台北", "PROPERTY", "yellow", 9500),
    _tile("自来水公司", "UTILITY", "utility", 2000),
    _tile("新北", "PROPERTY", "yellow", 10000),
    _tile("前往牢房", "GO_JAIL", "", 0),
    _tile("板桥", "PROPERTY", "green", 11000),
    _tile("中和", "PROPERTY", "green", 11500),
    _tile("社区", "COMMUNITY", "", 0),
    _tile("三重", "PROPERTY", "green", 12000),
    _tile("花莲车站", "RAILROAD", "railroad", 2000),
    _tile("机会", "CHANCE", "", 0),
    _tile("信义", "PROPERTY", "darkblue", 15000),
    _tile("奢侈税", "TAX", "", 1200),
    _tile("大安", "PROPERTY", "darkblue", 20000),
]


# ---------------------------------------------------------- map: world landmarks
WORLD_TILES: List[Tuple[str, str, str, int]] = [
    _tile("机场", "GO", "", 0),
    _tile("长城", "PROPERTY", "brown", 1500),
    _tile("命运", "COMMUNITY", "", 0),
    _tile("金字塔", "PROPERTY", "brown", 2000),
    _tile("度假税", "TAX", "", 800),
    _tile("世界中心", "RAILROAD", "railroad", 2000),
    _tile("铁塔", "PROPERTY", "lightblue", 1500),
    _tile("命运", "CHANCE", "", 0),
    _tile("自由钟", "PROPERTY", "lightblue", 2000),
    _tile("国会", "PROPERTY", "lightblue", 2500, ),
    _tile("拘留所", "JAIL", "", 0),
    _tile("梵蒂冈", "PROPERTY", "pink", 3000),
    _tile("电力网", "UTILITY", "utility", 1500),
    _tile("大本钟", "PROPERTY", "pink", 3500),
    _tile("埃菲尔", "PROPERTY", "pink", 4000),
    _tile("星港", "RAILROAD", "railroad", 2000),
    _tile("富士山", "PROPERTY", "orange", 5000),
    _tile("命运", "COMMUNITY", "", 0),
    _tile("大峡谷", "PROPERTY", "orange", 5500),
    _tile("迪拜塔", "PROPERTY", "orange", 6000),
    _tile("免费机场", "FREE", "", 0),
    _tile("好望角", "PROPERTY", "red", 7000),
    _tile("命运", "CHANCE", "", 0),
    _tile("悉尼歌剧院", "PROPERTY", "red", 7500),
    _tile("珠穆拉", "PROPERTY", "red", 8000),
    _tile("赤道站", "RAILROAD", "railroad", 2000),
    _tile("泰姬陵", "PROPERTY", "yellow", 9000),
    _tile("泰晤士", "PROPERTY", "yellow", 9500),
    _tile("水利网", "UTILITY", "utility", 2000),
    _tile("亚马逊", "PROPERTY", "yellow", 10000),
    _tile("前往拘留所", "GO_JAIL", "", 0),
    _tile("金门大桥", "PROPERTY", "green", 11000),
    _tile("科罗拉多", "PROPERTY", "green", 11500),
    _tile("命运", "COMMUNITY", "", 0),
    _tile("尼罗河", "PROPERTY", "green", 12000),
    _tile("丝路", "RAILROAD", "railroad", 2000),
    _tile("命运", "CHANCE", "", 0),
    _tile("帝国大厦", "PROPERTY", "darkblue", 15000),
    _tile("旅行税", "TAX", "", 1200),
    _tile("自由女神", "PROPERTY", "darkblue", 20000),
]


# ---------------------------------------------------------- map: gpa (campus / gpa flavour)
GPA_TILES: List[Tuple[str, str, str, int]] = [
    _tile("入学点", "GO", "", 0),
    _tile("文学楼", "PROPERTY", "brown", 1500),
    _tile("学生事务", "COMMUNITY", "", 0),
    _tile("化学楼", "PROPERTY", "brown", 2000),
    _tile("教育费", "TAX", "", 800),
    _tile("校巴", "RAILROAD", "railroad", 2000),
    _tile("计算机楼", "PROPERTY", "lightblue", 1500),
    _tile("机会", "CHANCE", "", 0),
    _tile("图书馆", "PROPERTY", "lightblue", 2000),
    _tile("体育室", "PROPERTY", "lightblue", 2500),
    _tile("休息室", "JAIL", "", 0),
    _tile("经济系", "PROPERTY", "pink", 3000),
    _tile("电网", "UTILITY", "utility", 1500),
    _tile("外语系", "PROPERTY", "pink", 3500),
    _tile("艺术系", "PROPERTY", "pink", 4000),
    _tile("校车", "RAILROAD", "railroad", 2000),
    _tile("法学院", "PROPERTY", "orange", 5000),
    _tile("学生事务", "COMMUNITY", "", 0),
    _tile("医学院", "PROPERTY", "orange", 5500),
    _tile("商学院", "PROPERTY", "orange", 6000),
    _tile("免费校车", "FREE", "", 0),
    _tile("建筑系", "PROPERTY", "red", 7000),
    _tile("机会", "CHANCE", "", 0),
    _tile("地质系", "PROPERTY", "red", 7500),
    _tile("能源系", "PROPERTY", "red", 8000),
    _tile("校巴", "RAILROAD", "railroad", 2000),
    _tile("统计系", "PROPERTY", "yellow", 9000),
    _tile("数学系", "PROPERTY", "yellow", 9500),
    _tile("供水", "UTILITY", "utility", 2000),
    _tile("生物系", "PROPERTY", "yellow", 10000),
    _tile("前往休息室", "GO_JAIL", "", 0),
    _tile("物理系", "PROPERTY", "green", 11000),
    _tile("化学系", "PROPERTY", "green", 11500),
    _tile("学生事务", "COMMUNITY", "", 0),
    _tile("地质系", "PROPERTY", "green", 12000),
    _tile("校车", "RAILROAD", "railroad", 2000),
    _tile("机会", "CHANCE", "", 0),
    _tile("规划系", "PROPERTY", "darkblue", 15000),
    _tile("学费", "TAX", "", 1200),
    _tile("荣誉廊", "PROPERTY", "darkblue", 20000),
]


_MAPS = {
    "taiwan": {"name": "台湾·城市地图", "tiles": TAIWAN_TILES},
    "world": {"name": "世界·地标地图", "tiles": WORLD_TILES},
    "gpa": {"name": "校园·G绩点地图", "tiles": GPA_TILES},
}


@dataclass
class GameMap:
    """An in-memory, serialisable board layout."""

    key: str
    name: str = ""
    tiles: List[Tuple[str, str, str, int]] = field(default_factory=list)

    @classmethod
    def from_key(cls, key: str) -> "GameMap":
        spec = _MAPS.get(key)
        if not spec:
            raise KeyError(f"Unknown board map key: {key}")
        return cls(key=key, name=spec["name"], tiles=list(spec["tiles"]))

    def as_definitions(self) -> List[Tuple[str, str, str, int]]:
        return list(self.tiles)


def available_maps() -> List[str]:
    """Return the list of available map keys (sorted by insertion order)."""
    return list(_MAPS.keys())


def by_key(key: str) -> GameMap:
    """Look up a :class:`GameMap` by its registry key."""
    return GameMap.from_key(key)
