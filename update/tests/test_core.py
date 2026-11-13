"""Tests for the pure steps of the weekly update (no network, no model, runs in a second)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import TEST_START, block_start, fill_actuals, join_new_weeks, make_rankings, weeks  # noqa: E402


def weekly(start, n, values):
    idx = pd.date_range(start, periods=n, freq="7D", name="date")
    return pd.DataFrame(values, index=idx)


@pytest.fixture
def live():
    rng = np.random.default_rng(0)
    return weekly("2026-01-04", 40, {"a": 20 + rng.random(40) * 10, "b": 50 + rng.random(40) * 20})


def test_join_rescales_the_download_and_adds_only_new_weeks(live):
    # A new download on a scale twice as large, with the same history plus 3 new weeks.
    pull = weekly(live.index[5], 38, {"a": 0.0, "b": 0.0})
    pull.loc[live.index[5:], :] = live.loc[live.index[5:]].to_numpy() * 2
    pull.loc[pull.index[-3:], :] = [[60, 140], [62, 150], [64, 160]]
    extended, report = join_new_weeks(live, pull)

    assert len(extended) == len(live) + 3
    pd.testing.assert_frame_equal(extended.iloc[:len(live)], live)       # stored weeks unchanged
    assert report["factor"].round(6).tolist() == [0.5, 0.5]
    assert extended["a"].iloc[-3:].tolist() == [30, 31, 32]              # scaled back to the live level
    assert report["overlap_corr"].min() > 0.999


def test_join_refuses_a_download_with_nothing_new(live):
    with pytest.raises(ValueError, match="nothing to add"):
        join_new_weeks(live, live.iloc[:-1])


def test_join_refuses_a_download_with_a_missing_style(live):
    pull = weekly(live.index[5], 37, {"a": 1.0})
    with pytest.raises(ValueError, match="missing"):
        join_new_weeks(live, pull)


def test_join_refuses_a_gap_after_the_live_table(live):
    pull = weekly(live.index[-1] + weeks(2), 3, {"a": 1.0, "b": 1.0})
    pull = pd.concat([live.iloc[-10:], pull])
    with pytest.raises(ValueError, match="gap"):
        join_new_weeks(live, pull)


def test_join_marks_a_low_volume_overlap_as_weak(live):
    live2 = live.assign(a=np.linspace(1.0, 2.0, len(live)))  # low volume, but not constant
    pull = pd.concat([live2.iloc[-10:], weekly(live.index[-1] + weeks(1), 1, {"a": 1.0, "b": 60.0})])
    _, report = join_new_weeks(live2, pull)
    assert report.set_index("style").loc["a", "weak"] and not report.set_index("style").loc["b", "weak"]


def test_block_start_follows_the_final_test_schedule():
    assert block_start(TEST_START) == TEST_START
    assert block_start(TEST_START + weeks(3)) == TEST_START
    assert block_start(TEST_START + weeks(4)) == TEST_START + weeks(4)
    assert block_start("2026-10-11") == pd.Timestamp("2026-10-11")     # 92 weeks after the test start
    assert block_start("2026-11-01") == pd.Timestamp("2026-10-11")
    with pytest.raises(ValueError):
        block_start("2024-12-29")


def test_make_rankings_ranks_and_holds_back_out_of_range_alerts():
    f = pd.DataFrame({
        "week": pd.Timestamp("2026-11-01"), "horizon": 4, "style": ["x", "y", "z"], "category": "Shoes",
        "last4_avg": [9.0, 9.0, 9.0], "predicted": [14.0, 9.0, 4.0], "actual": np.nan,
        "inputs_out_of_range": [False, False, False]})
    r = make_rankings(f, threshold=1.2)
    assert r["style"].tolist() == ["x", "y", "z"] and r["rank"].tolist() == [1, 2, 3]
    assert r["predicted_growth"].round(2).tolist() == [1.5, 1.0, 0.5]   # (predicted + 1) / (last4 + 1)
    assert r["alert"].tolist() == [True, False, False]
    assert r["market_growth"].round(2).iloc[0] == 1.0
    held = make_rankings(f.assign(inputs_out_of_range=True), threshold=1.2)
    assert held["predicted_rising"].iloc[0] and not held["alert"].any()


def test_fill_actuals_fills_only_empty_values():
    r = pd.DataFrame({"week": pd.to_datetime(["2026-10-04", "2026-10-11"]), "style": "x", "horizon": 4,
                      "actual": [5.0, np.nan]})
    known = r.assign(actual=[99.0, 7.0])
    out, filled = fill_actuals(r, known)
    assert out["actual"].tolist() == [5.0, 7.0] and filled == 1
