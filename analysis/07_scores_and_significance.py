"""Accuracy table and significance tests for Chapter 3 of the report.

Relative MAE: each style's MAE divided by the 4-week-average baseline's MAE on the same
forecasts, averaged over styles (below 1 = better than the 4-week average).
Significance: LightGBM against last value and Ridge, on the weekly mean absolute-error
difference (LightGBM minus comparison; negative = LightGBM better). Diebold-Mariano test with a
Newey-West variance (lags h-1) and a moving-block bootstrap of weeks (block length h weeks,
2,000 draws). Only forecasts made by every model are compared.

Run from the analysis folder:  python 07_scores_and_significance.py
"""
import numpy as np
import pandas as pd
from scipy.stats import norm

from common import RESULTS

KEYS = ["date", "item", "horizon"]
MODELS = ["lightgbm", "ridge", "ets", "last_value", "avg_4w", "seasonal_naive"]


def load():
    lgb = pd.read_csv(RESULTS / "predictions_lightgbm.csv", parse_dates=["date"])
    lgb = (lgb.groupby(KEYS + ["model"], as_index=False)
              .agg(actual=("actual", "mean"), predicted=("predicted", "mean")))
    base = pd.read_csv(RESULTS / "predictions.csv", parse_dates=["date"])[KEYS + ["model", "actual", "predicted"]]
    d = pd.concat([lgb, base], ignore_index=True)
    d = d[d["model"].isin(MODELS)].dropna(subset=["actual", "predicted"])
    n = d.groupby(KEYS)["model"].transform("nunique")
    d = d[n == len(MODELS)].copy()
    d["period"] = np.where(d["date"] >= "2025-01-01", "test", "validation")
    d["abs_err"] = (d["actual"] - d["predicted"]).abs()
    return d


def relative_mae(d):
    mae = d.groupby(["model", "item"])["abs_err"].mean().unstack("model")
    return (mae.div(mae["avg_4w"], axis=0)).mean()


def dm_test(x, max_lag):
    x = np.asarray(x, float)
    c = x - x.mean()
    v = np.mean(c ** 2)
    for lag in range(1, min(max_lag, len(x) - 1) + 1):
        v += 2 * (1 - lag / (max_lag + 1)) * np.mean(c[lag:] * c[:-lag])
    stat = x.mean() / np.sqrt(max(v, 1e-15) / len(x))
    return stat, max(2 * norm.sf(abs(stat)), 1e-16)


def block_bootstrap(x, block, repeats=2000, seed=42):
    x = np.asarray(x, float)
    n = len(x)
    rng = np.random.default_rng(seed)
    k = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(repeats, k))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(repeats, -1)[:, :n]
    return np.quantile(x[idx].mean(axis=1), [0.025, 0.975])


def main():
    d = load()
    views = {"validation": d[d.period == "validation"],
             "2025": d[(d.period == "test") & (d.date.dt.year == 2025)],
             "full test": d[d.period == "test"]}
    table = {}
    for h in (4, 8):
        for name, v in views.items():
            table[(h, name)] = relative_mae(v[v.horizon == h])
    table = pd.DataFrame(table).round(3)
    print("Relative MAE versus the 4-week average (lower is better)\n", table, "\n")

    rows = []
    for h in (4, 8):
        for name, v in views.items():
            v = v[v.horizon == h]
            wide = v.pivot_table(index=["date", "item"], columns="model", values="abs_err")
            for other in ("last_value", "ridge"):
                weekly = (wide["lightgbm"] - wide[other]).groupby(level="date").mean().sort_index()
                stat, p = dm_test(weekly.to_numpy(), h - 1)
                lo, hi = block_bootstrap(weekly.to_numpy(), block=h)
                rows.append({"period": name, "horizon": h, "comparison": other,
                             "weeks": len(weekly), "mean_difference": weekly.mean(),
                             "ci_low": lo, "ci_high": hi, "dm_statistic": stat, "dm_p_value": p})
    sig = pd.DataFrame(rows)
    sig.to_csv(RESULTS / "significance_tests_lightgbm.csv", index=False)
    print(sig.round(3).to_string(index=False))
    m25 = views["2025"]
    print("\n2025 MAE at 4 weeks:", m25[m25.horizon == 4].groupby("model")["abs_err"].mean().round(2).to_dict())


if __name__ == "__main__":
    main()
