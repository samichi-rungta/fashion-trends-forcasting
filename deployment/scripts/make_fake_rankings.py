"""Create a FAKE rankings file so the app can be built before real results exist.

The numbers are random. They only have the same shape as the real file that
Person 2 will produce (one row per week, style and horizon).

Run from the deployment/ folder:
    python scripts/make_fake_rankings.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

# Example keywords from Table 2.3 of the proposal (55 of the 137 styles).
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

# Six forecast weeks ending with the last week of the Google Trends data.
WEEKS = pd.date_range(end="2026-10-11", periods=6, freq="7D")
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "rankings_fake.csv"


def main() -> None:
    rng = np.random.default_rng(42)  # fixed seed, so the file is the same every run
    rows = []
    for horizon, spread in [(4, 0.10), (8, 0.16)]:  # 8 weeks ahead is less certain
        for category, styles in STYLES.items():
            for style in styles:
                # A slow random walk, so a style's growth changes gradually week to week.
                level = rng.normal(0, spread)
                for week in WEEKS:
                    level += rng.normal(0, spread / 3)
                    rows.append({
                        "week": week.strftime("%Y-%m-%d"),
                        "style": style,
                        "category": category,
                        "horizon": horizon,
                        "predicted_growth": round(float(np.exp(level)), 3),
                        "model": "fake_demo",
                    })

    df = pd.DataFrame(rows)
    # Rank 1 = highest predicted growth, separately for each week and horizon.
    df["rank"] = (
        df.groupby(["week", "horizon"])["predicted_growth"]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    df = df.sort_values(["week", "horizon", "rank"])
    columns = ["week", "style", "category", "horizon", "predicted_growth", "rank", "model"]
    df[columns].to_csv(OUTPUT, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
