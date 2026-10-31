"""Load the rankings file and check that it has the expected shape.

The app does no model training. It only reads a saved file of predictions
(made by the modelling code) and serves it. This is the simplest form of
"model serving": precomputed forecasts, refreshed whenever a new file is saved.
"""
import os
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ["week", "style", "category", "horizon", "predicted_growth", "rank"]
ALLOWED_HORIZONS = {4, 8}
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "rankings.csv"

def rankings_path() -> Path:
    """File to serve. Set the RANKINGS_PATH environment variable to use another file."""
    return Path(os.environ.get("RANKINGS_PATH", DEFAULT_PATH))


def rising_threshold() -> float:
    """Growth ratio above which a style counts as rising (1.1 or 1.2 in the proposal)."""
    return float(os.environ.get("RISING_THRESHOLD", "1.2"))


def check_rankings(df: pd.DataFrame) -> None:
    """Raise a clear error if the file is not in the agreed format."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Rankings file is missing columns: {missing}")

    if df[REQUIRED_COLUMNS].isna().any().any():
        raise ValueError("Rankings file has empty values in required columns")

    bad_horizons = set(df["horizon"].unique()) - ALLOWED_HORIZONS
    if bad_horizons:
        raise ValueError(f"Horizon must be 4 or 8, found: {sorted(bad_horizons)}")

    if (df["predicted_growth"] <= 0).any():
        raise ValueError("predicted_growth must be above 0 (it is a ratio, 1.0 = no change)")

    if df.duplicated(["week", "style", "horizon"]).any():
        raise ValueError("Each style should appear once per week and horizon")

    # Within each week and horizon, ranks should be exactly 1, 2, ..., n.
    for (week, horizon), group in df.groupby(["week", "horizon"]):
        if sorted(group["rank"]) != list(range(1, len(group) + 1)):
            raise ValueError(f"Ranks for week {week}, horizon {horizon} are not 1..{len(group)}")


def load_rankings(path: Path | None = None) -> pd.DataFrame:
    """Read the CSV, check it, and add a 'rising' column using the threshold."""
    df = pd.read_csv(path or rankings_path())
    check_rankings(df)
    df["week"] = pd.to_datetime(df["week"]).dt.strftime("%Y-%m-%d")
    df["horizon"] = df["horizon"].astype(int)
    df["rank"] = df["rank"].astype(int)
    df["rising"] = df["predicted_growth"] > rising_threshold()
    return df
