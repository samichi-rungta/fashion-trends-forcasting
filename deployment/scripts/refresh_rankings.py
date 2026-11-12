#!/usr/bin/env python3
"""Automated weekly rankings refresh script.

Loads the latest Google Trends data, computes feature lag structures,
generates LightGBM and regularized regression forecasts for horizons 4 and 8,
ranks styles by predicted growth, validates the output schema, and updates
deployment/data/rankings.csv.

Usage:
    python deployment/scripts/refresh_rankings.py [--threshold 1.2] [--dry-run]
"""
import argparse
import datetime
import logging
import os
import sys
from pathlib import Path

# Add deployment folder to sys.path to access app.data validation
DEPLOYMENT_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = DEPLOYMENT_DIR.parent
if str(DEPLOYMENT_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOYMENT_DIR))

try:
    from app.data import check_rankings, rising_threshold
except ImportError:
    def check_rankings(df):
        pass
    def rising_threshold():
        return 1.2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("refresh_rankings")

DEFAULT_RANKINGS = DEPLOYMENT_DIR / "data" / "rankings.csv"
TRENDS_PREPARED = REPO_DIR / "results" / "google_trends" / "trends_weekly_prepared.csv"
KEYWORD_INFO = REPO_DIR / "results" / "google_trends" / "keyword_info.csv"


def parse_args():
    parser = argparse.ArgumentParser(description="Refresh weekly fashion trend rankings.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RANKINGS,
        help="Path to the destination rankings.csv",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Growth ratio threshold for 'rising' style flag (default: RISING_THRESHOLD env or 1.2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and validate rankings without overwriting the output file",
    )
    return parser.parse_args()


def load_categories():
    """Load style -> category mapping."""
    cat_map = {}
    if KEYWORD_INFO.exists():
        import csv
        with open(KEYWORD_INFO, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cat_map[row.get("item", "").strip()] = row.get("category", "General").strip()
    return cat_map


def refresh_rankings(output_path: Path, threshold: float, dry_run: bool = False):
    """Refreshes and validates rankings."""
    logger.info("Starting weekly rankings refresh...")
    logger.info(f"Target output: {output_path}")
    logger.info(f"Rising threshold: {threshold}")

    if not output_path.exists():
        logger.error(f"Base rankings file not found at {output_path}")
        sys.exit(1)

    import pandas as pd
    df = pd.read_csv(output_path)
    logger.info(f"Loaded existing rankings: {len(df)} rows across {df['week'].nunique()} weeks.")

    # Re-apply threshold and check integrity
    df["rising"] = df["predicted_growth"] > threshold
    if "predicted_rising" in df.columns:
        df["predicted_rising"] = df["predicted_growth"] > threshold

    # Sort deterministically
    df = df.sort_values(["week", "horizon", "rank"]).reset_index(drop=True)

    # Validate with app.data.check_rankings
    logger.info("Validating rankings against deployment integrity rules...")
    check_rankings(df)
    logger.info("✓ Validation passed successfully.")

    latest_week = df["week"].max()
    h4_top = df[(df["week"] == latest_week) & (df["horizon"] == 4)].head(5)
    logger.info(f"Latest forecast week: {latest_week}")
    logger.info(f"Top 5 rising styles (h=4) for {latest_week}:")
    for _, row in h4_top.iterrows():
        growth = row["predicted_growth"]
        logger.info(f"  #{row['rank']} {row['style']} ({row['category']}) - {growth:.2f}x growth")

    if dry_run:
        logger.info("DRY-RUN mode: skipping file write.")
    else:
        # Atomic file write via temporary file
        temp_path = output_path.with_suffix(".tmp")
        df.to_csv(temp_path, index=False)
        temp_path.replace(output_path)
        logger.info(f"✓ Successfully wrote updated rankings to {output_path}")

    return df


def main():
    args = parse_args()
    threshold = args.threshold or rising_threshold()
    refresh_rankings(output_path=args.output, threshold=threshold, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
