"""Tiny serialisation helpers shared by the save/load and stock systems.

Kept free of any imports from ``game`` so it cannot create import cycles.
"""
from __future__ import annotations


def rng_to_json(rng) -> dict:
    """Snapshot a ``random.Random`` state as a JSON-friendly dict."""
    version, internal, gauss = rng.getstate()
    return {"version": version, "state": list(internal), "gauss": gauss}


def rng_from_json(rng, data: dict) -> None:
    """Restore a ``random.Random`` state previously stored by ``rng_to_json``."""
    rng.setstate((data["version"], tuple(data["state"]), data["gauss"]))
