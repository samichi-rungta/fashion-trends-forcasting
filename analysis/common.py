"""Shared settings and loading code for the section 4 analysis notebooks.

Every notebook starts with:
    from common import load_predictions, RISING_THRESHOLD, DATA_LABEL
    df = load_predictions()

All settings are in this file, so adapting to new or changed result files
means editing here only, never inside the notebooks.
"""
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------- settings --

# True = test the notebooks on the fake file from make_fake_predictions.py.
USE_FAKE_DATA = False

ANALYSIS = Path(__file__).resolve().parent
RESULTS = ANALYSIS.parent / "results" / "google_trends"
FAKE_FILE = ANALYSIS / "fake_data" / "predictions_fake.csv"

MAIN_FILE = RESULTS / "predictions_lightgbm.csv"   # LightGBM: agreed format, 5 seeds
BASELINE_FILE = RESULTS / "predictions.csv"         # baselines, ETS, Ridge, Lasso
KEYWORD_FILE = RESULTS / "keyword_info.csv"         # category of every style
SPIKE_FILE = RESULTS / "spike_weeks.csv"            # weeks flagged as market-wide spikes
WEEKLY_FILE = RESULTS / "trends_weekly_prepared.csv"  # weekly search interest, for checks

# The baseline file follows the agreed format (date = week the forecast was made,
# 4-week averages, last4_avg). Set to True only for an older version that used
# date = the week being predicted and one week's value: it is then converted the
# same way as in the LightGBM notebook's "fair comparison".
BASELINE_NEEDS_CONVERSION = False

RISING_THRESHOLD = 1.2      # team decision, chosen on the validation years
PERIOD = "test"             # analyse the final test only (January 2025 onwards)
MAIN_MODEL = "lightgbm"
BASELINES = ["last_value", "seasonal_naive"]   # avg_4w never says "rising", so it is left out of comparisons

DATA_LABEL = "FAKE data" if USE_FAKE_DATA else "real data"
REQUIRED_COLUMNS = ["date", "item", "horizon", "actual", "predicted", "model", "period", "last4_avg"]


# ----------------------------------------------------------------- loading --

def _main_runs() -> pd.DataFrame:
    """LightGBM forecasts for the chosen period, one row per seed."""
    df = pd.read_csv(MAIN_FILE, parse_dates=["date"])
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{MAIN_FILE.name} is missing columns: {missing}")
    return df[df["period"] == PERIOD]


def _baselines(truth: pd.DataFrame) -> pd.DataFrame:
    """Baseline, ETS, Ridge and Lasso forecasts, matched to the same forecasts and answers as LightGBM."""
    df = pd.read_csv(BASELINE_FILE, parse_dates=["date"])
    df = df[df["period"] == PERIOD]
    if BASELINE_NEEDS_CONVERSION:
        df["date"] = df["date"] - pd.to_timedelta(df["horizon"] * 7, unit="D")
        df = df.drop(columns=["actual"])
        # keep only forecasts that LightGBM also made, with the same answers
        df = df.merge(truth, on=["date", "item", "horizon"], how="inner")
    return df


def load_seed_runs() -> pd.DataFrame:
    """Main model, one row per seed (for the robustness check across seeds)."""
    if USE_FAKE_DATA:
        return _add_columns(pd.read_csv(FAKE_FILE, parse_dates=["date"]).query("model == @MAIN_MODEL"))
    return _add_columns(_main_runs())


def load_predictions() -> pd.DataFrame:
    """All models for the chosen period, one row per forecast (seeds averaged)."""
    if USE_FAKE_DATA:
        return _add_columns(pd.read_csv(FAKE_FILE, parse_dates=["date"]))

    runs = _main_runs()
    main = (runs.groupby(["date", "item", "horizon", "model", "period"], as_index=False)
                .agg(actual=("actual", "mean"), predicted=("predicted", "mean"),
                     last4_avg=("last4_avg", "first"), seeds=("seed", "nunique")))
    truth = main[["date", "item", "horizon", "actual", "last4_avg"]]
    combined = pd.concat([main, _baselines(truth)], ignore_index=True)

    # Compare like with like: keep only forecasts that every model made.
    keys = ["date", "item", "horizon"]
    models_per_forecast = combined.groupby(keys)["model"].transform("nunique")
    combined = combined[models_per_forecast == combined["model"].nunique()]
    return _add_columns(combined)


def _add_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Columns every notebook needs: origin, growth and category."""
    df = df[df["last4_avg"] > 0].copy()          # growth is undefined when the last 4 weeks were all 0
    df["origin"] = df["date"]                    # week the forecast was made
    df["predicted_growth"] = df["predicted"] / df["last4_avg"]
    df["actual_growth"] = df["actual"] / df["last4_avg"]
    # Recent jump = last 4-week average ÷ the one 4 weeks earlier, matched by date
    # (not by row position, because some weeks are missing for low-volume styles).
    earlier = (df[["item", "origin", "last4_avg"]].drop_duplicates(["item", "origin"])
                 .assign(origin=lambda d: d["origin"] + pd.Timedelta(weeks=4))
                 .rename(columns={"last4_avg": "last4_avg_4w_ago"}))
    df = df.merge(earlier, on=["item", "origin"], how="left")
    df["recent_jump"] = df["last4_avg"] / df["last4_avg_4w_ago"]
    if "category" not in df.columns:
        categories = pd.read_csv(KEYWORD_FILE)[["item", "category"]]
        df = df.merge(categories, on="item", how="left")
    return df


def spike_weeks() -> list:
    """Weeks the team flagged as market-wide spikes."""
    if USE_FAKE_DATA:
        return list(pd.to_datetime(["2026-02-08", "2026-02-15"])) + list(pd.date_range("2026-03-29", "2026-05-17", freq="7D"))
    s = pd.read_csv(SPIKE_FILE, parse_dates=["date"])
    return list(s.loc[s["spike_week"].astype(bool), "date"])


# ------------------------------------------------------------------ checks --

def check_definitions(df: pd.DataFrame, sample: int = 500) -> pd.DataFrame:
    """Recompute `actual` and `last4_avg` from the weekly data for a sample of rows.

    Both should match 100%. A lower share means a file uses a different definition
    of date or actual, and every growth number built on it would be wrong.
    """
    weekly = pd.read_csv(WEEKLY_FILE, parse_dates=["date"]).set_index("date")
    position = {d: i for i, d in enumerate(weekly.index)}
    rows = []
    for model, g in df.groupby("model"):
        g = g[g["item"].isin(weekly.columns)].sample(min(sample, len(g)), random_state=0)
        ok_actual, ok_last4 = [], []
        for _, r in g.iterrows():
            y, i, h = weekly[r["item"]].values, position[r["origin"]], int(r["horizon"])
            ok_last4.append(abs(y[i - 3:i + 1].mean() - r["last4_avg"]) < 1e-6)
            if i + h < len(y):
                ok_actual.append(abs(y[i + h - 3:i + h + 1].mean() - r["actual"]) < 1e-6)
        rows.append({"model": model,
                     "actual matches (%)": round(100 * sum(ok_actual) / max(len(ok_actual), 1), 1),
                     "last4_avg matches (%)": round(100 * sum(ok_last4) / max(len(ok_last4), 1), 1)})
    return pd.DataFrame(rows).set_index("model")
