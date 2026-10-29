"""Shared settings and loading code for the section 4 analysis notebooks.

Every notebook starts with:
    from common import load_predictions
    df = load_predictions()
"""
from pathlib import Path

import pandas as pd

# Which file to analyse. Switch to the real file when it arrives, e.g.
# Path(__file__).resolve().parent.parent / "results" / "google_trends" / "predictions.csv"
PREDICTIONS_PATH = Path(__file__).resolve().parent / "fake_data" / "predictions_fake.csv"

# Growth above this counts as "rising" (the team chooses 1.1 or 1.2 on training years).
RISING_THRESHOLD = 1.1

# What the `date` column means. Confirm with Persons 1 and 2:
#   "origin" = the week the forecast was made   (used by the fake file)
#   "target" = the week being predicted
DATE_MEANS = "origin"

REQUIRED_COLUMNS = ["date", "item", "horizon", "actual", "predicted", "model", "period", "last4_avg"]


def load_predictions(path: Path = PREDICTIONS_PATH) -> pd.DataFrame:
    """Read a predictions file and add the columns every analysis needs."""
    df = pd.read_csv(path, parse_dates=["date"])

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Predictions file is missing columns: {missing}")

    # `origin` = the week the forecast was made, whatever `date` means in the file.
    if DATE_MEANS == "origin":
        df["origin"] = df["date"]
    else:
        df["origin"] = df["date"] - pd.to_timedelta(df["horizon"] * 7, unit="D")

    # Growth = 4-week average ahead divided by the last 4-week average (1.0 = no change).
    df["predicted_growth"] = df["predicted"] / df["last4_avg"]
    df["actual_growth"] = df["actual"] / df["last4_avg"]
    return df
