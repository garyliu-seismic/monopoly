"""Human card prompts (pure logic, testable without GUI).

A *prompt* is the moment a *human* player lands on a ``CHANCE`` /
``COMMUNITY`` tile and the engine needs the UI to display a card before their
outcome is resolved. Because the engine mutates state in the same step that
produces the card, we recover the human's first card event from the
``(phase, text)`` log, which is fully testable without Qt.
"""
from __future__ import annotations

from typing import List, Tuple

# Map log phase -> (icon, kind) for richer UI presentation.
CARD_ICON = {"机会": "🎁", "社区": "🎉"}
CARD_KIND = {"机会": "chance", "社区": "community"}


def card_event_index(
    log: List[Tuple[str, str]],
    human_name: str,
    log_index: int = 0,
) -> int:
    """Index of the human's first card event at/after ``log_index``.

    A *card event* is a log line whose phase is ``"机会"``/``"社区"`` and
    that mentions ``human_name``. Returns -1 when none exist.
    """
    for i in range(len(log)):
        if i < log_index:
            continue
        phase, text = log[i]
        if phase in CARD_ICON and human_name in text:
            return i
    return -1


def cleaned_prompt_text(text: str, human_name: str) -> str:
    """Drop the leading ``"human_name "`` from a card log line."""
    marker = f"{human_name} "
    if text.startswith(marker):
        return text[len(marker):]
    return text
