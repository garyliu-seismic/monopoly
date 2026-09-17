"""The 12 logical categories of a board tile (index is a stable ordinal,
mirrors the JSON layout in ``tiles.py``)."""
from __future__ import annotations

from enum import IntEnum


class TileType(IntEnum):
    GO = 0
    CHANCE = 1
    COMMUNITY = 2
    TAX = 3
    RAILROAD = 4
    UTILITY = 5
    PROPERTY = 6
    JAIL = 7
    FREE = 8
    GANBANG = 9        # 强盗集团 / 抢银行
    PRISON = 10        # 牢房
    GO_JAIL = 11       # 前往牢房
    SPECIAL = 12       # 特殊场景（如升级城市、升级机场）

    @property
    def self_name(self) -> str:  # pragma: no cover - presentation helper
        return {
            TileType.GO: "起点",
            TileType.CHANCE: "机会",
            TileType.COMMUNITY: "社区chest",
            TileType.TAX: "税收",
            TileType.RAILROAD: "铁路",
            TileType.UTILITY: "公用事业",
            TileType.PROPERTY: "地产",
            TileType.JAIL: "牢房",
            TileType.FREE: "免费停车",
            TileType.GANBANG: "强盗集团/银行",
            TileType.PRISON: "监狱",
            TileType.GO_JAIL: "监狱",
            TileType.SPECIAL: "特殊",
        }[self]
