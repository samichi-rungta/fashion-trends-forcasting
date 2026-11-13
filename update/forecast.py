"""Forecast new weeks with the same LightGBM model as the final test.

Uses analysis/rebuild_lightgbm.py (same inputs, target, filters and tuned settings as the modelling
notebook), the same 5 seeds averaged, the same 4-weekly refit schedule, and the same out-of-range
flag: a forecast is flagged when the market's 4-week growth lies outside the range seen in the
training rows of its refit.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "analysis"))
from rebuild_lightgbm import EPS, build_table, fit_model, rows_for  # noqa: E402

from core import block_start  # noqa: E402

SEEDS = range(5)
HORIZONS = (4, 8)
WATCH = "market_growth4"    # the input that left the training range in 2026


def forecast_weeks(weekly_file, weeks: list) -> pd.DataFrame:
    """One row per style, horizon and forecast week, averaged over the seeds (before ranking)."""
    table, numeric = build_table(weekly_file)
    features = numeric + ["category"]
    weeks = sorted(pd.to_datetime(weeks))
    parts = []
    for h in HORIZONS:
        d = rows_for(table, numeric, h)
        for start in sorted({block_start(w) for w in weeks}):
            block = [w for w in weeks if block_start(w) == start]
            rows = d[d["date"].isin(block)].reset_index(drop=True)
            if rows.empty:
                continue
            train = d[(d["target_date"] <= start) & d["actual"].notna()]
            lo, hi = train[WATCH].min(), train[WATCH].max()
            levels = [(np.exp(fit_model(d, features, h, start, seed=s).predict(rows[features]))
                       * (rows["last4_avg"] + EPS) - EPS).clip(lower=0) for s in SEEDS]
            parts.append(pd.DataFrame({
                "week": rows["date"], "horizon": h, "style": rows["item"],
                "category": rows["category"].astype(str), "last4_avg": rows["last4_avg"],
                "predicted": np.mean(levels, axis=0), "actual": rows["actual"],
                "inputs_out_of_range": (rows[WATCH] < lo) | (rows[WATCH] > hi),
            }))
    return pd.concat(parts, ignore_index=True)


def known_actuals(weekly_file, weeks: list) -> pd.DataFrame:
    """What actually happened (the 4-week average h weeks later) for forecasts made in `weeks`; NaN if not known yet."""
    table, numeric = build_table(weekly_file)
    weeks = pd.to_datetime(pd.Series(weeks))
    out = []
    for h in HORIZONS:
        d = rows_for(table, numeric, h)
        d = d[d["date"].isin(weeks)]
        out.append(pd.DataFrame({"week": d["date"], "style": d["item"], "horizon": h, "actual": d["actual"]}))
    return pd.concat(out, ignore_index=True)
