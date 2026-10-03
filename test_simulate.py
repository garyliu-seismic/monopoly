"""Smoke test for the headless batch simulator."""
from tools import simulate


def test_simulator_is_deterministic_and_summarises():
    args = (7, 3, 60, None)
    a, b = simulate.play_one(args), simulate.play_one(args)
    assert a == b
    text = simulate.summarise([a, simulate.play_one((8, 3, 60, None))], 3)
    assert "win rate by seat" in text and "P3" in text
