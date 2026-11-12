"""Export the two extra data files the buyer app uses for its item details.

1. deployment/data/search_history.csv
   Weekly search interest for every style (the same prepared series the model is trained on),
   for the 'last 8 weeks + forecast' chart.

2. deployment/data/explanations.csv
   For every forecast in deployment/data/rankings.csv: how much each group of model inputs
   pushed the forecast up or down. These are SHAP values from LightGBM's built-in
   pred_contrib, computed with the rebuilt model (rebuild_lightgbm.py), retrained every
   4 weeks as in the final test and averaged over the same 5 seeds as the live forecasts.
   Values are on the model's scale, log((forecast + 1) / (last 4-week average + 1)):
   exp(value) - 1 is the push in percent.

Run from the analysis folder:  python export_app_data.py
"""
import numpy as np
import pandas as pd

from common import RESULTS, WEEKLY_FILE
from rebuild_lightgbm import EPS, build_table, fit_model, rows_for

APP_DATA = RESULTS.parent.parent / "deployment" / "data"
SEEDS = range(5)

# Inputs grouped into ideas a buyer can follow.
GROUPS = {
    "recent_level": ["lag0", "lag1", "lag2", "lag4", "lag8", "lag12", "lag26"],
    "momentum": ["growth4", "growth8", "growth12", "accel", "vol8", "vol26"],
    "season": ["lag52", "last_year_growth4", "last_year_growth8", "week_sin", "week_cos"],
    "market": ["market_growth4", "rel_growth4"],
    "category": ["category"],
}


def explain(h: int, weeks: list) -> pd.DataFrame:
    table, numeric = build_table()
    features = numeric + ["category"]
    assert sorted(sum(GROUPS.values(), [])) == sorted(features), "every input must belong to one group"
    d = rows_for(table, numeric, h)
    parts = []
    for i in range(0, len(weeks), 4):
        block = weeks[i:i + 4]
        rows = d[d["date"].isin(block)].reset_index(drop=True)
        if rows.empty:
            continue
        contrib = np.mean([fit_model(d, features, h, block[0], seed=s).predict(rows[features], pred_contrib=True)
                           for s in SEEDS], axis=0)
        out = rows[["date", "item"]].rename(columns={"date": "week", "item": "style"})
        out["horizon"] = h
        out["base"] = contrib[:, -1]
        for name, cols in GROUPS.items():
            out[name] = contrib[:, [features.index(c) for c in cols]].sum(axis=1)
        out["explained_growth"] = (np.exp(contrib.sum(axis=1)) * (rows["last4_avg"] + EPS) - EPS).clip(0) / rows["last4_avg"]
        parts.append(out)
    return pd.concat(parts, ignore_index=True)


def main():
    rankings = pd.read_csv(APP_DATA / "rankings.csv", parse_dates=["week"])
    weeks = sorted(rankings["week"].unique())

    history = pd.read_csv(WEEKLY_FILE, parse_dates=["date"])
    history = history[history["date"] <= weeks[-1]]
    history.round(2).to_csv(APP_DATA / "search_history.csv", index=False)

    ex = pd.concat([explain(h, weeks) for h in (4, 8)], ignore_index=True)
    check = ex.merge(rankings[["week", "style", "horizon", "predicted_growth"]], on=["week", "style", "horizon"])
    print(f"{len(check)} of {len(rankings)} forecasts explained; "
          f"correlation with the live forecast {check['explained_growth'].corr(check['predicted_growth']):.4f}, "
          f"mean absolute difference {(check['explained_growth'] - check['predicted_growth']).abs().mean():.4f}")
    ex["week"] = ex["week"].dt.strftime("%Y-%m-%d")
    ex.round(4).to_csv(APP_DATA / "explanations.csv", index=False)


if __name__ == "__main__":
    main()
