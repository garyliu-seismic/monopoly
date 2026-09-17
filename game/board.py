"""The Monopoly board.

A Monopoly board is a list of 40 ``Tile`` records arranged in the classic
大富翁 / Monopoly ring: 8 colour groups, 4 railroads, 2 utilities, 3 chance,
3 community-chest, 2 tax tiles and the 4 corner tiles. ``tiles`` is linear
(index == tile ordinal), which is all the engine needs for walking/rent;
``grid`` keeps the x/y grid position for painting only.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from .tile_types import TileType


class Tile:
    """One board cell.

    ``category`` tells the engine how to dispatch. For PROPERTY tiles the
    ``group`` identifies the colour set and ``house`` counts the
    hotel/houses. ``owner`` is the owning player's name.
    """

    def __init__(
        self,
        tile: int,
        name: str,
        category: TileType,
        group: str = "",
        price: int = 0,
        owner: Optional[str] = None,
        house: int = 0,
    ) -> None:
        self.tile = tile
        self.name = name
        self.category = category
        self.group = group
        self.price = price
        self.owner = owner
        self.house = house

    def to_dict(self) -> dict:
        return {
            "tile": self.tile,
            "name": self.name,
            "category": int(self.category),
            "group": self.group,
            "price": self.price,
            "owner": self.owner,
            "house": self.house,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Tile":
        return cls(
            data["tile"],
            data["name"],
            TileType(data["category"]),
            data.get("group", ""),
            data.get("price", 0),
            data.get("owner"),
            data.get("house", 0),
        )


# (name, category, group, price) — classic 40-tile layout with Taiwanese
# city names. 8 property groups: brown(2), lightblue(3), pink(3), orange(3),
# red(3), yellow(3), green(3), darkblue(2).
_DEFINITIONS = [
    ("起点", TileType.GO, "", 0),                      # 0
    ("基隆", TileType.PROPERTY, "brown", 1500),        # 1
    ("社区", TileType.COMMUNITY, "", 0),               # 2
    ("苗栗", TileType.PROPERTY, "brown", 2000),        # 3
    ("所得税", TileType.TAX, "", 200),                 # 4
    ("台北车站", TileType.RAILROAD, "railroad", 500),  # 5
    ("彰化", TileType.PROPERTY, "lightblue", 1500),    # 6
    ("机会", TileType.CHANCE, "", 0),                  # 7
    ("云林", TileType.PROPERTY, "lightblue", 2000),    # 8
    ("嘉义", TileType.PROPERTY, "lightblue", 2500),    # 9
    ("监狱", TileType.JAIL, "", 0),                    # 10
    ("屏东", TileType.PROPERTY, "pink", 3000),         # 11
    ("电力公司", TileType.UTILITY, "utility", 1500),   # 12
    ("台东", TileType.PROPERTY, "pink", 3500),         # 13
    ("宜兰", TileType.PROPERTY, "pink", 4000),         # 14
    ("台中车站", TileType.RAILROAD, "railroad", 500),  # 15
    ("花莲", TileType.PROPERTY, "orange", 5000),       # 16
    ("社区", TileType.COMMUNITY, "", 0),               # 17
    ("南投", TileType.PROPERTY, "orange", 5500),       # 18
    ("台中", TileType.PROPERTY, "orange", 6000),       # 19
    ("免费停车", TileType.FREE, "", 0),                # 20
    ("台南", TileType.PROPERTY, "red", 7000),          # 21
    ("机会", TileType.CHANCE, "", 0),                  # 22
    ("新竹", TileType.PROPERTY, "red", 7500),          # 23
    ("桃园", TileType.PROPERTY, "red", 8000),          # 24
    ("高雄车站", TileType.RAILROAD, "railroad", 500),  # 25
    ("高雄", TileType.PROPERTY, "yellow", 9000),       # 26
    ("台北", TileType.PROPERTY, "yellow", 9500),       # 27
    ("自来水公司", TileType.UTILITY, "utility", 2000),  # 28
    ("新北", TileType.PROPERTY, "yellow", 10000),      # 29
    ("前往牢房", TileType.GO_JAIL, "", 0),             # 30
    ("板桥", TileType.PROPERTY, "green", 11000),       # 31
    ("中和", TileType.PROPERTY, "green", 11500),       # 32
    ("社区", TileType.COMMUNITY, "", 0),               # 33
    ("三重", TileType.PROPERTY, "green", 12000),       # 34
    ("花莲车站", TileType.RAILROAD, "railroad", 500),  # 35
    ("机会", TileType.CHANCE, "", 0),                  # 36
    ("信义", TileType.PROPERTY, "darkblue", 15000),    # 37
    ("奢侈税", TileType.TAX, "", 500),                 # 38
    ("大安", TileType.PROPERTY, "darkblue", 20000),    # 39
]


class Board:
    def __init__(self, size: int = 40, rng: random.Random | None = None):
        self.size = size
        self.tiles: List[Tile] = []
        for i in range(size):
            if i < len(_DEFINITIONS):
                name, cat, group, price = _DEFINITIONS[i]
            else:
                name, cat, group, price = f"tile{i}", TileType.SPECIAL, "", 0
            self.tiles.append(
                Tile(tile=i, name=name, category=cat, group=group, price=price)
            )
        self.grid = _grid(size)

    def tile_by_index(self, index: int) -> Tile:
        return self.tiles[index % self.size]

    def reset_owned(self) -> None:
        for t in self.tiles:
            t.owner = None
            t.house = 0

    # ------------------------------------------------------------ serialise
    def to_dict(self) -> dict:
        return {"size": self.size, "tiles": [t.to_dict() for t in self.tiles]}

    @classmethod
    def from_dict(cls, data: dict) -> "Board":
        b = cls(size=data["size"])
        b.tiles = [Tile.from_dict(t) for t in data["tiles"]]
        return b


def _grid(size: int) -> Dict[int, tuple[int, int]]:
    """Loop the tiles out around an 11×11 perimeter (a classic Monopoly ring).

    ``grid[tile]`` maps a tile ordinal to a ``(row, col)`` cell so the UI can
    paint the board as a ring rather than a plain table.

    The 40 tiles form the full perimeter of an 11×11 board: 11 across the
    bottom, 10 up the right edge, 10 across the top, then 9 down the left
    edge (corners counted once).
    """
    if size < 0:
        return {}
    coords: list[tuple[int, int]] = []
    # bottom row: left to right (11 cells)
    for c in range(11):
        coords.append((0, c))
    # right column: up from bottom-right corner (10 cells)
    for r in range(1, 11):
        coords.append((r, 10))
    # top row: right to left, excluding the top-right corner (10 cells)
    for c in range(9, -1, -1):
        coords.append((10, c))
    # left column: down from top-left, excluding both corners (9 cells)
    for r in range(9, 0, -1):
        coords.append((r, 0))
    assert len(coords) >= size, coords
    return {i: coords[i] for i in range(size)}


def build_board(size: int = 40, rng: random.Random | None = None) -> Board:
    return Board(size=size, rng=rng)
