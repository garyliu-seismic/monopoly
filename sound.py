"""Programmatic sound effects for the Monopoly game.

All sounds are synthesised locally as small 16-bit mono WAV files (no
external audio assets required), then played back through Qt's
``QSoundEffect``. This keeps the game fully self-contained.

The WAV files are written lazily into ``assets/sounds/`` on first run.
"""
from __future__ import annotations

import math
import os
import random
import struct
import wave

SAMPLE_RATE = 22050
_SOUNDS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "sounds"
)


# ----------------------------------------------------------------- synthesis
def _sine(freq: float, dur: float, vol: float = 0.5) -> list[float]:
    """A decaying sine tone."""
    n = int(SAMPLE_RATE * dur)
    out: list[float] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        attack = min(1.0, i / (0.004 * SAMPLE_RATE))
        decay = math.exp(-3.0 * t / dur) if dur > 0 else 1.0
        out.append(vol * attack * decay * math.sin(2 * math.pi * freq * t))
    return out


def _noise(dur: float, vol: float = 0.4) -> list[float]:
    """A decaying white-noise burst (dice rattle)."""
    n = int(SAMPLE_RATE * dur)
    out: list[float] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        attack = min(1.0, i / (0.002 * SAMPLE_RATE))
        decay = math.exp(-5.0 * t / dur)
        out.append(vol * attack * decay * random.uniform(-1.0, 1.0))
    return out


def _concat(*parts: list[float]) -> list[float]:
    return [s for part in parts for s in part]


# Each effect is a pre-built sample buffer (freqs chosen to sound pleasant).
_EFFECTS: dict[str, list[float]] = {
    "roll": _concat(_noise(0.08, 0.5), _noise(0.08, 0.5)),
    "move": _sine(880, 0.05, 0.32),
    "buy": _concat(_sine(523.25, 0.09, 0.5), _sine(659.25, 0.13, 0.5)),
    "rent": _concat(_sine(659.25, 0.10, 0.5), _sine(523.25, 0.15, 0.5)),
    "jail": _concat(_sine(196.0, 0.18, 0.55), _sine(146.83, 0.26, 0.55)),
    "event": _concat(_sine(1046.5, 0.09, 0.5), _sine(783.99, 0.14, 0.5)),
    "win": _concat(
        _sine(523.25, 0.12, 0.5),
        _sine(659.25, 0.12, 0.5),
        _sine(783.99, 0.12, 0.5),
        _sine(1046.5, 0.32, 0.6),
    ),
}


def _write_wav(path: str, samples: list[float]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples
        )
        w.writeframes(frames)


def _wav_path(name: str) -> str:
    return os.path.join(_SOUNDS_DIR, f"{name}.wav")


def ensure_sound_files() -> None:
    """Synthesise any missing WAV files (safe to call repeatedly)."""
    for name, samples in _EFFECTS.items():
        path = _wav_path(name)
        if not os.path.exists(path):
            _write_wav(path, samples)


class SoundManager:
    """Plays the named sound effects through QSoundEffect.

    Must be instantiated *after* a QApplication exists. Set ``enabled`` to
    False to mute the whole game.
    """

    def __init__(self, enabled: bool = True):
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QSoundEffect

        ensure_sound_files()
        self.enabled = enabled
        self._effects: dict[str, QSoundEffect] = {}
        for name in _EFFECTS:
            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(_wav_path(name)))
            eff.setVolume(0.9)
            self._effects[name] = eff

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        eff = self._effects.get(name)
        if eff is not None:
            eff.play()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


# ------------------------------------------------------------------ global
_manager: SoundManager | None = None


def init(enabled: bool = True) -> SoundManager:
    """Create the global sound manager (requires an existing QApplication)."""
    global _manager
    _manager = SoundManager(enabled)
    return _manager


def play(name: str) -> None:
    """Play a named effect if the manager exists and sound is enabled."""
    if _manager is not None:
        _manager.play(name)


def set_enabled(enabled: bool) -> None:
    if _manager is not None:
        _manager.set_enabled(enabled)
