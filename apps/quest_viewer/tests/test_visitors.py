from __future__ import annotations

from pathlib import Path

from quest_viewer.visitors import DailyVisitorCounter


def test_daily_visitor_counter_counts_one_browser_once(tmp_path: Path) -> None:
    counter = DailyVisitorCounter(tmp_path / "visitor_stats.db")

    first_count, _, first_is_new = counter.record("browser_a_123456")
    repeat_count, _, repeat_is_new = counter.record("browser_a_123456")
    another_count, _, another_is_new = counter.record("browser_b_123456")

    assert (first_count, first_is_new) == (1, True)
    assert (repeat_count, repeat_is_new) == (1, False)
    assert (another_count, another_is_new) == (2, True)
    assert counter.count() == 2


def test_counter_recovers_when_today_row_is_missing(tmp_path: Path) -> None:
    counter = DailyVisitorCounter(tmp_path / "visitor_stats.db")
    counter.record("browser_a_123456")
    counter.database_path.unlink()

    recovered_count, _, recovered_is_new = counter.record("browser_a_123456")

    assert (recovered_count, recovered_is_new) == (1, True)
