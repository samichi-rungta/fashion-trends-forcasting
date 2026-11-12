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
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_PATH = DATA_DIR / "rankings.csv"

def rankings_path() -> Path:
    """File to serve. Set the RANKINGS_PATH environment variable to use another file."""
    return Path(os.environ.get("RANKINGS_PATH", DEFAULT_PATH))


def order_lead_weeks() -> int:
    """Supplier lead time in weeks: how long an order takes to arrive (ORDER_LEAD_WEEKS, default 6)."""
    return int(os.environ.get("ORDER_LEAD_WEEKS", "6"))


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


def _as_bool(column: pd.Series) -> pd.Series:
    """Read True/False columns safely, whether pandas saw them as booleans or as text."""
    return column.astype(str).str.strip().str.lower().isin(["true", "1"])


def add_market_columns(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Add the market and alert columns, or check them if the modelling code already made them.

    market_growth       average predicted growth of all styles in that week and horizon
    growth_vs_market    a style's predicted growth divided by market_growth (above 1 = beats the market)
    inputs_out_of_range the market's recent growth lay outside the training range, so alerts are held back
    rising              the rising alert: predicted growth above the threshold, in a week that is not out of range
    """
    df = df.copy()
    if "market_growth" not in df.columns:
        df["market_growth"] = df.groupby(["week", "horizon"])["predicted_growth"].transform("mean")
    if "growth_vs_market" not in df.columns:
        df["growth_vs_market"] = df["predicted_growth"] / df["market_growth"]
    df["inputs_out_of_range"] = (
        _as_bool(df["inputs_out_of_range"]) if "inputs_out_of_range" in df.columns else False
    )

    expected_alert = (df["predicted_growth"] > threshold) & ~df["inputs_out_of_range"]
    if "alert" in df.columns:
        # The file's alerts were made by the modelling code. They must follow the same rule and
        # threshold as this app, otherwise the page would show alerts made with another setting.
        differ = int((_as_bool(df["alert"]) != expected_alert).sum())
        if differ:
            raise ValueError(
                f"The file's alert column does not match RISING_THRESHOLD={threshold} "
                f"({differ} rows differ). Was the file made with a different threshold?"
            )
    df["rising"] = expected_alert
    # Above the threshold, but the alert was held back because the inputs were out of range.
    df["held_back"] = (df["predicted_growth"] > threshold) & df["inputs_out_of_range"]
    return df


def load_rankings(path: Path | None = None) -> pd.DataFrame:
    """Read the CSV, check it, and add the market, alert and held-back columns."""
    df = pd.read_csv(path or rankings_path())
    check_rankings(df)
    df["week"] = pd.to_datetime(df["week"]).dt.strftime("%Y-%m-%d")
    df["horizon"] = df["horizon"].astype(int)
    df["rank"] = df["rank"].astype(int)
    return add_market_columns(df, rising_threshold())


# ---------------------------------------------------------------- optional detail data
# Both files are made by analysis/export_app_data.py. The app still works without them:
# the item details then leave out the chart or the explanation.

GROUPS = ["recent_level", "momentum", "season", "market", "category"]


def load_history(path: Path | None = None) -> pd.DataFrame | None:
    """Weekly search interest per style (rows = weeks, columns = styles), or None if the file is missing."""
    path = path or DATA_DIR / "search_history.csv"
    if not path.exists():
        return None
    history = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    if history.empty:
        raise ValueError("search_history.csv is empty")
    return history


def load_explanations(path: Path | None = None) -> pd.DataFrame | None:
    """SHAP contributions per forecast, indexed by (week, style, horizon), or None if the file is missing."""
    path = path or DATA_DIR / "explanations.csv"
    if not path.exists():
        return None
    ex = pd.read_csv(path)
    missing = {"week", "style", "horizon", "base", *GROUPS} - set(ex.columns)
    if missing:
        raise ValueError(f"explanations.csv is missing columns: {sorted(missing)}")
    return ex.set_index(["week", "style", "horizon"]).sort_index()
