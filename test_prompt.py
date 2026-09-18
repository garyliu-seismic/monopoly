"""Tests for human cardprompt helpers (pure logic, no GUI)."""
from __future__ import annotations

from game.prompt import (
    card_event_index,
    CARD_ICON,
    CARD_KIND,
    cleaned_prompt_text,
    card_event_display,
)


def _log(*events):
    return list(events)


def test_card_event_index_finds_last_chance():
    log = _log(
        ("roll", "玩家1 掷出 5"),
        ("起点", "玩家1 获得起点奖金 ¥1500"),
        ("社区", "玩家1 社区：前进到监狱"),
    )
    assert card_event_index(log, "玩家1", 0) == 2


def test_card_event_index_respects_offset():
    log = _log(
        ("roll", "玩家2 掷出 5"),
        ("社区", "玩家1 社区：前进到监狱"),
        ("机会", "玩家1 机会：退回 3 格"),
    )
    # A prompt only appears when scanning from the human's turn onward.
    assert card_event_index(log, "玩家1", 0) == 1
    # Skipping past the first card -> the second one.
    assert card_event_index(log, "玩家1", 2) == 2


def test_card_event_index_zero_when_uncapped():
    log = _log(("roll", "玩家1 掷出 5"), ("tax", "玩家1 缴纳税费 ¥200"))
    assert card_event_index(log, "玩家1", 0) == -1


def test_card_event_index_ignores_other_players():
    log = _log(
        ("机会", "玩家2 机会：前进到监狱"),
        ("社区", "玩家1 社区：退回 3 格"),
    )
    assert card_event_index(log, "玩家1", 0) == 1


def test_prompt_text_helpers():
    assert CARD_ICON == {"机会": "\U0001F381", "社区": "\U0001F389"}
    assert CARD_KIND == {"机会": "chance", "社区": "community"}
    text = "玩家1 社区：前进到监狱"
    assert cleaned_prompt_text(text, "玩家1") == "社区：前进到监狱"
    # Missing human name -> returned unchanged.
    assert cleaned_prompt_text("玩家2 抽到一张卡", "玩家1") == "玩家2 抽到一张卡"


def test_card_event_display_strips_name_for_card():
    assert card_event_display(("机会", "玩家1 机会卡: 获得 +2000"), "玩家1") == (
        "机会", "机会卡: 获得 +2000",
    )


def test_card_event_display_leaves_non_card_untouched():
    # A roll/tax/etc entry is not a card; keep it verbatim (name intact).
    assert card_event_display(("roll", "玩家1 掷出 5"), "玩家1") == (
        "roll", "玩家1 掷出 5",
    )
