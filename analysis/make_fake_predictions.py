"""Create a FAKE predictions file in the team's shared format.

The numbers are invented, but they are built to behave like real search data:
some styles drift up or down, outerwear is seasonal, some styles have short
fads that fade, two "emerging" styles rise steadily, and every style jumps
together in spring 2026 (like the real spike in the Google Trends data).

The fake "lightgbm" model partly sees the future and partly chases recent
momentum, so it makes realistic mistakes: false alerts after fads and after
the spring spike, and missed rises on fast-growing styles.

Definitions used here (to confirm with the team):
  date       = the week the forecast was made
  actual     = average search interest over the 4 weeks ending `horizon` weeks after `date`
  predicted  = the model's forecast of that same 4-week average
  last4_avg  = average of the 4 weeks up to and including `date`

Run from the analysis/ folder:
    python make_fake_predictions.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

STYLES = {
    "Jeans and denim": ["skinny jeans", "wide leg jeans", "baggy jeans", "mom jeans", "barrel jeans"],
    "Trousers and shorts": ["cargo pants", "leggings", "joggers", "capri pants", "bermuda shorts"],
    "Skirts and dresses": ["mini skirt", "pleated skirt", "slip dress", "sundress", "corset dress"],
    "Tops and knitwear": ["crop top", "baby tee", "cardigan", "hoodie", "turtleneck"],
    "Outerwear": ["blazer", "puffer jacket", "trench coat", "bomber jacket", "faux fur coat"],
    "Shoes": ["ballet flats", "mary janes", "loafers", "kitten heels", "clogs"],
    "Bags": ["baguette bag", "tote bag", "crossbody bag", "mini bag", "belt bag"],
    "Accessories": ["claw clip", "scrunchie", "bucket hat", "hoop earrings", "oversized sunglasses"],
    "Patterns and materials": ["polka dot", "leopard print", "gingham", "satin", "lace"],
    "Colors": ["sage green", "butter yellow", "chocolate brown", "cherry red", "baby blue"],
    "Aesthetics and styles": ["y2k fashion", "quiet luxury", "coquette", "balletcore", "gorpcore"],
}
EMERGING = {"balletcore", "gorpcore"}
THRESHOLD = 1.1
WEEKS = pd.date_range("2023-01-01", "2026-10-11", freq="7D")  # Sundays, like Google Trends
TEST_START = pd.Timestamp("2025-01-05")
OUTPUT = Path(__file__).resolve().parent / "fake_data" / "predictions_fake.csv"


def market_multiplier(weeks: pd.DatetimeIndex) -> np.ndarray:
    """Every style jumps together in spring 2026 (peak in mid-April), then falls back."""
    t = weeks.values.astype("datetime64[D]").astype(float)
    peak = np.datetime64("2026-04-12").astype(float)
    feb = np.datetime64("2026-02-11").astype(float)
    return 1 + 1.5 * np.exp(-((t - peak) / 21) ** 2) + 0.4 * np.exp(-((t - feb) / 7) ** 2)


def make_series(rng, category: str, style: str) -> np.ndarray:
    n = np.arange(len(WEEKS))
    week_of_year = WEEKS.isocalendar().week.values.astype(float)
    level = rng.uniform(20, 60)

    if style in EMERGING:  # low before 2024, then a steady rise
        log_trend = np.where(WEEKS >= "2024-01-01", 0.012 * (n - 52), 0.0) - 0.8
    else:
        log_trend = rng.normal(0, 0.002) * n

    if category == "Outerwear":
        seasonal = 0.45 * np.cos(2 * np.pi * (week_of_year - 46) / 52)
    else:
        seasonal = 0.08 * np.cos(2 * np.pi * (week_of_year - rng.uniform(0, 52)) / 52)

    fads = np.zeros(len(WEEKS))  # short bursts of interest that fade within weeks
    for start in rng.choice(np.arange(60, len(WEEKS) - 6), size=rng.integers(1, 4), replace=False):
        fads[start:start + 4] += np.array([0.35, 0.6, 0.4, 0.15])

    noise = rng.normal(0, 0.06, len(WEEKS))
    return level * np.exp(log_trend + seasonal + fads + noise) * market_multiplier(WEEKS)


def avg(y: np.ndarray, end: int) -> float:
    """Average of the 4 weeks ending at position `end`."""
    return y[end - 3:end + 1].mean()


def main() -> None:
    rng = np.random.default_rng(7)
    rows = []
    for category, styles in STYLES.items():
        for style in styles:
            y = make_series(rng, category, style)
            for h in (4, 8):
                for i in np.where(WEEKS >= TEST_START)[0]:
                    if i + h >= len(WEEKS):
                        break  # the future is not known yet
                    base = avg(y, i)
                    actual = avg(y, i + h)
                    momentum = np.log(base / avg(y, i - 4))
                    noise = rng.normal(0, 0.05 if h == 4 else 0.08)
                    forecasts = {
                        # Fake model: partly right about the future, partly chasing momentum.
                        "lightgbm": base * np.exp(0.55 * np.log(actual / base) + 0.5 * momentum + noise),
                        "last_value": y[i],
                        "four_week_avg": base,
                        "seasonal_naive": avg(y, i + h - 52) * base / avg(y, i - 52),
                    }
                    for model, predicted in forecasts.items():
                        rows.append({
                            "date": WEEKS[i].strftime("%Y-%m-%d"),
                            "item": style,
                            "horizon": h,
                            "actual": round(actual, 2),
                            "predicted": round(float(predicted), 2),
                            "model": model,
                            "period": "test",
                            "last4_avg": round(base, 2),
                            "category": category,
                            "predicted_rising": int(predicted / base > THRESHOLD),
                            "actually_rose": int(actual / base > THRESHOLD),
                        })

    df = pd.DataFrame(rows)
    OUTPUT.parent.mkdir(exist_ok=True)
    df.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(df):,} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
