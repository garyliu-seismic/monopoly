"""Tests for human card prompt helpers (pure logic, no GUI)."""
from __future__ import annotations

from game.prompt import card_event_index, cleaned_prompt_text, CARD_KIND


def test_card_event_index_finds_chance():
    log = [
        ("roll", "玩家1 掷出 8"),
        ("机会", "玩家1 机会卡: 获得 +2000"),
        ("起点奖金", "玩家1 经过起点 +¥2500"),
    ]
    idx = card_event_index(log, "玩家1", 0)
    assert idx == 1
    assert log[idx] == ("机会", "玩家1 机会卡: 获得 +2000")


def test_card_event_index_finds_community():
    log = [
        ("roll", "玩家1 掷出 3"),
        ("社区", "玩家1 房子失火，维修费 -1500"),
        ("税收", "玩家1 缴纳税收 -1000"),
    ]
    idx = card_event_index(log, "玩家1", 0)
    assert idx == 1


def test_card_event_index_zero_when_uncapped():
    log = [
        ("roll", "玩家1 掷出 5"),
        ("税收", "玩家1 缴纳税收 -1000"),
        ("rent", "玩家1 交租 -2000"),
    ]
    assert card_event_index(log, "玩家1", 0) == -1


def test_card_event_index_respects_offset():
    log = [
        ("roll", "玩家1 掷出 5"),
        ("roll", "玩家2 掷出 9"),
    ]
    # Start scanning after the human's previous roll; nothing new.
    assert card_event_index(log, "玩家1", 1) == -1


def test_card_index_returns_latest_when_called_again():
    log = [
        ("roll", "玩家1 掷出 5"),
        ("机会", "玩家1 机会卡: 获得 +2000"),
        ("机会", "玩家1 机会卡: 移动 3 格"),
    ]
    first = card_event_index(log, "玩家1", 0)
    assert first == 1
    # After resolving, scan from the next index -> the later card.
    second = card_event_index(log, "玩家1", first + 1)
    assert second == 2


def test_clean_prompt_text_strips_name():
    assert cleaned_prompt_text("玩家1 机会卡: 获得 +2000", "玩家1") == "机会卡: 获得 +2000"
    assert cleaned_prompt_text("玩家1 房子失火，维修费 -1500", "玩家1") == "房子失火，维修费 -1500"
    # Unknown marker -> returned unchanged.
    assert cleaned_prompt_text("无标记文本", "玩家1") == "无标记文本"


def test_card_kind_mapping():
    assert CARD_KIND == {"机会": "chance", "社区": "community"}
