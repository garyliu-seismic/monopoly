"""The Monopoly board.

A Monopoly board is a list of 34 ``Tile`` records. We build the canonical
大富翁 (Richman 4) 34-grid layout: ``tiles`` is linear (index == tile
ordinal), which is all the engine needs for walking/rent. ``grid`` keeps the
x/y grid position for painting only.
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


# (name, category, group, price) in 大富翁 order; the engine dispatches the
# remaining categories (CHANCE/COMMUNITY/TAX/... ).
_DEFINITIONS = [
    ("起点", TileType.GO, "", 0),
    ("台北", TileType.PROPERTY, "brown", 1500),
    ("机会", TileType.CHANCE, "", 0),
    ("高雄", TileType.PROPERTY, "brown", 2000),
    ("台北机场", TileType.TAX, "", 200),
    ("铁路1", TileType.RAILROAD, "railroad", 500),
    ("桃园", TileType.PROPERTY, "lightblue", 1500),
    ("社区", TileType.COMMUNITY, "", 0),
    ("台中", TileType.PROPERTY, "lightblue", 2000),
    ("新竹", TileType.PROPERTY, "lightblue", 2500),
    ("监狱", TileType.GO_JAIL, "", 0),
    ("银行", TileType.GANBANG, "", 0),
    ("电力公司", TileType.UTILITY, "utility", 1500),
    ("台北大桥", TileType.PROPERTY, "pink", 3000),
    ("机会", TileType.CHANCE, "", 0),
    ("台南", TileType.PROPERTY, "pink", 3500),
    ("台中机场", TileType.TAX, "", 0),
    ("铁路2", TileType.RAILROAD, "railroad", 500),
    ("嘉义", TileType.PROPERTY, "pink", 4000),
    ("免费停车", TileType.FREE, "", 0),
    ("牢房", TileType.JAIL, "", 0),
    ("社区", TileType.COMMUNITY, "", 0),
    ("高雄机场", TileType.TAX, "", 0),
    ("南港", TileType.PROPERTY, "orange", 5000),
    ("强盗集团", TileType.COMMUNITY, "", 0),
    ("瓦斯公司", TileType.UTILITY, "utility", 2000),
    ("高雄大桥", TileType.PROPERTY, "orange", 5500),
    ("机会", TileType.CHANCE, "", 0),
    ("高雄", TileType.PROPERTY, "orange", 6000),
    ("自由广场", TileType.SPECIAL, "", 0),
    ("前往牢房", TileType.FREE, "", 0),
    ("铁路3", TileType.RAILROAD, "railroad", 500),
    ("台北机场", TileType.PROPERTY, "yellow", 7000),
    ("社区", TileType.COMMUNITY, "", 0),
]


class Board:
    def __init__(self, size: int = 34, rng: random.Random | None = None):
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


def _grid(size: int) -> Dict[int, tuple[int, int]]:
    """Loop the tiles out around a rectangular perimeter (a Monopoly ring).

    ``grid[tile]`` maps a tile ordinal to a ``(row, col)`` cell so the UI can
    paint the board as a ring rather than a plain table.

    The 34 tiles form the full perimeter of a 10 by 9 board: 10 across the
    bottom, 8 up the right edge, 9 across the top, then 7 down the left edge.
    This produces a balanced, traditional Monopoly-style board with a large
    central play area.
    """
    if size < 0:
        return {}
    coords: list[tuple[int, int]] = []
    # bottom row: left to right
    for c in range(10):
        coords.append((0, c))
    # right column: up from bottom-right
    for r in range(1, 9):
        coords.append((r, 9))
    # top row: right to left, excluding the top-right corner
    for c in range(8, -1, -1):
        coords.append((8, c))
    # left column: down from top-left, excluding both corners
    for r in range(7, 0, -1):
        coords.append((r, 0))
    assert len(coords) >= size, coords
    return {i: coords[i] for i in range(size)}


def build_board(size: int = 34, rng: random.Random | None = None) -> Board:
    return Board(size=size, rng=rng)
