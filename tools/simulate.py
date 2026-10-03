"""Headless batch simulator: play many bot-only games and report balance stats.

Usage (from the project root)::

    python tools/simulate.py --games 500 --players 4
    python tools/simulate.py --games 2000 --map <key> --jobs 4 --csv out.csv

It needs no GUI. Use it to check the effect of a rule change: run before and
after with the same ``--seed`` and compare the summary.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import game as game_engine  # noqa: E402
from game.board import Board, build_map  # noqa: E402
from game.maps import by_key  # noqa: E402
from game.player import Player  # noqa: E402

LOG_COUNTERS = {
    "extra_rolls": "再掷一次",
    "triple_doubles": "三次掷出双骰",
    "jail_entries": "入监服刑",
    "mortgages": " 抵押 ",
}


def play_one(args: tuple) -> dict:
    """Play a single game; returns one flat result row."""
    seed, n_players, max_turns, map_key = args
    board = build_map(by_key(map_key)) if map_key else Board()
    players = [Player(f"P{i + 1}", is_bot=True) for i in range(n_players)]
    g = game_engine.Game(players, board=board, seed=seed, max_turns=max_turns)
    g.start()
    first_bankrupt_round: object = ""
    for _ in range(max_turns):
        if g.is_won() or all(p.bankrupt for p in players):
            break
        try:
            g.next_turn()
        except game_engine.GameOver:
            break
        g.run_step()
        if first_bankrupt_round == "" and any(p.bankrupt for p in players):
            first_bankrupt_round = round(g.turn / n_players, 1)
    texts = [t for _, t in g.log]
    row = {
        "seed": seed,
        "winner": g.winner.name if g.winner else "",
        "rounds": round(g.turn / n_players, 1),
        "player_turns": g.turn,
        "first_bankruptcy_round": first_bankrupt_round,
    }
    row["bankruptcies"] = sum(p.bankrupt for p in players)
    for key, needle in LOG_COUNTERS.items():
        row[key] = sum(needle in t for t in texts)
    row["leader"] = max(
        players,
        key=lambda p: p.money + p.bank - p.loan + sum(board.tiles[i].price for i in p.properties),
    ).name
    return row


def wilson(wins: int, n: int) -> tuple:
    """95% Wilson interval for a proportion."""
    if n == 0:
        return 0.0, 0.0
    z = 1.96
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def summarise(rows: List[dict], n_players: int) -> str:
    n = len(rows)
    decided = [r for r in rows if r["winner"]]
    lines = [f"games: {n}   players: {n_players}"]
    lines.append(f"decided (one survivor): {len(decided)}/{n} = {len(decided) / n:.1%}")
    rounds = [r["rounds"] for r in rows]
    lines.append(f"rounds  mean {statistics.mean(rounds):.1f}  median {statistics.median(rounds):.1f}"
                 f"  min {min(rounds)}  max {max(rounds)}")
    if decided:
        d = [r["rounds"] for r in decided]
        lines.append(f"rounds (decided only)  median {statistics.median(d):.1f}")
    first = [r["first_bankruptcy_round"] for r in rows if r["first_bankruptcy_round"] != ""]
    if first:
        lines.append(f"first bankruptcy round  median {statistics.median(first):.1f}  ({len(first)}/{n} games had one)")
    else:
        lines.append("first bankruptcy round  none: no player went bankrupt in any game")
    lines.append("")
    lines.append(f"win rate by seat (fair = {1 / n_players:.1%}); 'leader' = highest net worth at end")
    for i in range(n_players):
        name = f"P{i + 1}"
        wins = sum(r["winner"] == name for r in rows)
        lead = sum(r["leader"] == name for r in rows)
        lo, hi = wilson(wins, n)
        lines.append(f"  {name}: wins {wins / n:6.1%}  [{lo:.1%}, {hi:.1%}]   leader {lead / n:6.1%}")
    lines.append("")
    lines.append("per-game averages")
    for key in LOG_COUNTERS:
        lines.append(f"  {key:<15} {statistics.mean(r[key] for r in rows):.2f}")
    lines.append(f"  {'bankruptcies':<15} {statistics.mean(r['bankruptcies'] for r in rows):.2f}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--players", type=int, default=4)
    ap.add_argument("--max-turns", type=int, default=2000, help="player-turn cap per game")
    ap.add_argument("--seed", type=int, default=1, help="seed of game 0; game i uses seed+i")
    ap.add_argument("--map", default=None, help="map key (default: classic board)")
    ap.add_argument("--jobs", type=int, default=1, help="worker processes")
    ap.add_argument("--csv", default=None, help="write one row per game to this file")
    opts = ap.parse_args(argv)

    jobs = [(opts.seed + i, opts.players, opts.max_turns, opts.map) for i in range(opts.games)]
    if opts.jobs > 1:
        with ProcessPoolExecutor(max_workers=opts.jobs) as pool:
            rows = list(pool.map(play_one, jobs, chunksize=max(1, len(jobs) // (opts.jobs * 4))))
    else:
        rows = [play_one(j) for j in jobs]

    if opts.csv:
        with open(opts.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(summarise(rows, opts.players))
    return 0


if __name__ == "__main__":
    sys.exit(main())
