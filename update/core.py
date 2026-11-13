"""Pure data steps of the weekly update (pandas only, no network, no model).

Kept separate so they can be unit-tested quickly in CI:
- join_new_weeks: fit a fresh Google Trends download onto the live table and add the new weeks
- block_start: which 4-weekly refit a forecast week belongs to (same schedule as the final test)
- make_rankings: turn averaged forecasts into rows in the app's rankings format
- fill_actuals: add what actually happened to older forecasts whose answer is now known
"""
import numpy as np
import pandas as pd

EPS = 1.0                      # same smoothing constant as the model
TEST_START = pd.Timestamp("2025-01-05")   # first week of the final test; refits every 4 weeks from here
REFIT_EVERY = 4
MIN_OVERLAP_VOLUME = 3.0       # same rule as the original stitching: below this the scale factor is unreliable
RANKINGS_COLUMNS = ["week", "horizon", "rank", "style", "category", "last4_avg", "predicted",
                    "predicted_growth", "predicted_rising", "prob_rising", "actual",
                    "inputs_out_of_range", "market_growth", "growth_vs_market", "alert"]


def weeks(n: int) -> pd.Timedelta:
    """n weeks as a time step. (pd.Timedelta(weeks=n) warns with this pandas and numpy pair.)"""
    return pd.to_timedelta(7 * n, unit="D")


def join_new_weeks(live: pd.DataFrame, pull: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scale a new download to the live table over their shared weeks, then append the weeks after the live table ends.

    live: weekly table (index = week start dates, one column per style), the data the model already uses.
    pull: a fresh "today 5-y" download in the same layout (complete weeks only), on Google's new 0-100 scale.
    Returns the extended table and a report with one row per style (scale factor and overlap quality).
    Weeks that are already in the live table are never changed, so earlier forecasts stay reproducible.
    """
    missing = [c for c in live.columns if c not in pull.columns]
    if missing:
        raise ValueError(f"The download is missing {len(missing)} styles: {missing[:5]}")
    new_weeks = pull.index[pull.index > live.index.max()]
    if len(new_weeks) == 0:
        raise ValueError(f"The download has no weeks after {live.index.max().date()}: nothing to add")
    expected = pd.date_range(live.index.max() + weeks(1), periods=len(new_weeks), freq="7D")
    if not new_weeks.equals(expected):
        raise ValueError("The new weeks do not follow on weekly from the live table (gap or wrong week days)")

    rows, added = [], {}
    for style in live.columns:
        both = pd.concat([live[style], pull[style]], axis=1, keys=["live", "pull"]).dropna()
        o, r = both["live"].mean(), both["pull"].mean()
        factor = o / r if (o > 0 and r > 0) else 1.0
        corr = both["live"].corr(both["pull"]) if len(both) > 2 else np.nan
        rows.append({"style": style, "overlap_weeks": len(both), "factor": factor,
                     "overlap_corr": corr, "weak": bool(o < MIN_OVERLAP_VOLUME or r < MIN_OVERLAP_VOLUME)})
        added[style] = (pull.loc[new_weeks, style] * factor).round(2)
    extended = pd.concat([live, pd.DataFrame(added, index=new_weeks)[live.columns]])
    extended.index.name = live.index.name
    return extended, pd.DataFrame(rows)


def block_start(week) -> pd.Timestamp:
    """First week of the 4-week refit block that `week` belongs to. The model for a block is trained on
    everything known by its first week, as in the final test."""
    week = pd.Timestamp(week)
    n = (week - TEST_START).days // 7
    if n < 0:
        raise ValueError(f"{week.date()} is before the test period")
    return TEST_START + weeks((n // REFIT_EVERY) * REFIT_EVERY)


def make_rankings(forecasts: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Rows in the app's rankings format, from forecasts already averaged over seeds.

    forecasts needs: week, horizon, style, category, last4_avg, predicted, actual, inputs_out_of_range.
    The formulas are the ones in the modelling notebook (growth with EPS, rank within week and horizon,
    market = average predicted growth, alert = rising and inputs not out of range).
    """
    r = forecasts.copy()
    r["predicted_growth"] = (r["predicted"] + EPS) / (r["last4_avg"] + EPS)
    r["predicted_rising"] = r["predicted_growth"] > threshold
    r["prob_rising"] = np.nan    # the logistic model is not part of the live update; the app does not use it
    r["rank"] = r.groupby(["week", "horizon"])["predicted_growth"].rank(ascending=False, method="first").astype(int)
    r["inputs_out_of_range"] = r["inputs_out_of_range"].astype(bool)
    r["market_growth"] = r.groupby(["week", "horizon"])["predicted_growth"].transform("mean")
    r["growth_vs_market"] = r["predicted_growth"] / r["market_growth"]
    r["alert"] = r["predicted_rising"] & ~r["inputs_out_of_range"]
    return r.sort_values(["week", "horizon", "rank"])[RANKINGS_COLUMNS].reset_index(drop=True)


def fill_actuals(rankings: pd.DataFrame, known: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Fill empty `actual` values with answers that are now known. Existing values are never changed.

    known: week, style, horizon, actual (NaN where the answer is still in the future).
    Returns the updated rankings and how many values were filled.
    """
    out = rankings.merge(known.rename(columns={"actual": "_known"}), on=["week", "style", "horizon"], how="left")
    fill = out["actual"].isna() & out["_known"].notna()
    out.loc[fill, "actual"] = out.loc[fill, "_known"]
    return out.drop(columns="_known"), int(fill.sum())
