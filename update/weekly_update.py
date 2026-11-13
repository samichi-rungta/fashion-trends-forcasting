"""Weekly update of the buyer app's forecasts.

Run from the repository root, one command at a time:

  python update/weekly_update.py pull
      Download the latest Google Trends data for all styles (about 25 minutes). Saved as
      update/data/pulls/pull_<today>.csv. If it stops, run it again: finished styles are cached.

  python update/weekly_update.py build --pull update/data/pulls/pull_<date>.csv
      Add the new weeks to update/data/trends_weekly_live.csv, forecast them with the final
      LightGBM model, add them to deployment/data/rankings.csv (and fill in what actually happened
      for older forecasts), then refresh the app's search history and explanations (about 10 minutes).

  python update/weekly_update.py check --as-of 2026-10-11
      Consistency check: recompute the forecasts of one week that is already in the app, from the
      frozen study data, and compare them with the app's file. They should match.

The study files in results/ are never changed, so the report's results stay reproducible.
"""
import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

UPDATE = Path(__file__).resolve().parent
REPO = UPDATE.parent
sys.path.insert(0, str(UPDATE))
sys.path.insert(0, str(REPO / "analysis"))

from common import RISING_THRESHOLD, WEEKLY_FILE  # noqa: E402
from core import fill_actuals, join_new_weeks, make_rankings, RANKINGS_COLUMNS  # noqa: E402

LIVE_FILE = UPDATE / "data" / "trends_weekly_live.csv"
PULLS = UPDATE / "data" / "pulls"
CACHE = UPDATE / "data" / "cache"          # per-style downloads, not kept in Git
RANKINGS_FILE = REPO / "deployment" / "data" / "rankings.csv"
MIN_OVERLAP_CORR = 0.5     # below this a download does not look like the same series: stop


def read_weekly(path) -> pd.DataFrame:
    return pd.read_csv(path, index_col=0, parse_dates=True).sort_index()


def read_rankings() -> pd.DataFrame:
    r = pd.read_csv(RANKINGS_FILE, parse_dates=["week"])
    for col in ["predicted_rising", "inputs_out_of_range", "alert"]:
        r[col] = r[col].astype(str).str.lower().eq("true")
    return r


def cmd_pull(args):
    from pull import download
    styles = list(read_weekly(LIVE_FILE if LIVE_FILE.exists() else WEEKLY_FILE).columns)
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    table, failed = download(styles, CACHE / today)
    if failed:
        print(f"\n{len(failed)} styles failed: {failed}\nWait a few minutes and run the same command again.")
        sys.exit(1)
    PULLS.mkdir(parents=True, exist_ok=True)
    out = PULLS / f"pull_{today}.csv"
    table.to_csv(out)
    print(f"\nSaved {out.relative_to(REPO)}: {table.shape[1]} styles, weeks {table.index.min().date()} "
          f"to {table.index.max().date()}")


def cmd_build(args):
    from forecast import forecast_weeks, known_actuals
    if not LIVE_FILE.exists():   # first update: start from the frozen study data
        LIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(WEEKLY_FILE, LIVE_FILE)
        print(f"Created {LIVE_FILE.relative_to(REPO)} from the study data")
    live = read_weekly(LIVE_FILE)
    pull = read_weekly(args.pull)

    # 1. Join the download onto the live table
    extended, report = join_new_weeks(live, pull)
    new_weeks = extended.index[extended.index > live.index.max()]
    bad = report[~report["weak"] & (report["overlap_corr"] < MIN_OVERLAP_CORR)]
    print(f"New weeks: {[w.strftime('%Y-%m-%d') for w in new_weeks]}")
    print(f"Scale factor: median {report['factor'].median():.3f} (range {report['factor'].min():.2f} "
          f"to {report['factor'].max():.2f}); overlap correlation: median {report['overlap_corr'].median():.3f}, "
          f"lowest {report['overlap_corr'].min():.3f}")
    if len(bad):
        sys.exit(f"Stopped: these styles do not match the stored data: {bad['style'].tolist()}")

    # 2. Forecast the weeks after the app's latest forecast week
    rankings = read_rankings()
    weeks = [w for w in extended.index if w > rankings["week"].max()]
    if not weeks:
        sys.exit("No new forecast weeks.")
    extended.to_csv(LIVE_FILE)
    print(f"Saved {LIVE_FILE.relative_to(REPO)} (last week {extended.index.max().date()}). Forecasting...")
    new_rows = make_rankings(forecast_weeks(LIVE_FILE, weeks), RISING_THRESHOLD)

    # 3. Add them to the rankings and fill in answers that are now known
    combined = pd.concat([rankings, new_rows], ignore_index=True)[RANKINGS_COLUMNS]
    combined, filled = fill_actuals(combined, known_actuals(LIVE_FILE, sorted(combined["week"].unique())))
    expected_alert = (combined["predicted_growth"] > RISING_THRESHOLD) & ~combined["inputs_out_of_range"]
    assert (combined["alert"] == expected_alert).all(), "alert column does not follow the rule"
    assert not combined.duplicated(["week", "style", "horizon"]).any(), "duplicate forecasts"
    combined["week"] = combined["week"].dt.strftime("%Y-%m-%d")
    combined.to_csv(RANKINGS_FILE, index=False)
    print(f"Saved {RANKINGS_FILE.relative_to(REPO)}: {len(new_rows)} new forecasts, {filled} answers filled in")
    for (week, h), g in new_rows.groupby(["week", "horizon"]):
        print(f"  {week:%Y-%m-%d}, {h} weeks: market {g['market_growth'].iloc[0]:.2f}, "
              f"{int(g['alert'].sum())} alerts, out of range: {bool(g['inputs_out_of_range'].any())}, "
              f"top 3: {', '.join(g.nsmallest(3, 'rank')['style'])}")

    # 4. Refresh the app's search history and explanations
    if args.skip_export:
        print("Skipped the export: run it before committing (see update/README.md).")
        return
    print("Refreshing search_history.csv and explanations.csv (about 7 minutes)...")
    import export_app_data
    export_app_data.main(LIVE_FILE)


def cmd_check(args):
    from forecast import forecast_weeks
    week = pd.Timestamp(args.as_of)
    app = read_rankings()
    app = app[app["week"] == week]
    if app.empty:
        sys.exit(f"The app has no forecasts for {week.date()}")
    mine = make_rankings(forecast_weeks(WEEKLY_FILE, [week]), RISING_THRESHOLD)
    both = app.merge(mine, on=["week", "style", "horizon"], suffixes=("_app", "_new"))
    print(f"{week.date()}: {len(both)} of {len(app)} forecasts matched")
    for h, g in both.groupby("horizon"):
        top_app = set(g.nsmallest(10, "rank_app")["style"])
        top_new = set(g.nsmallest(10, "rank_new")["style"])
        print(f"  {h} weeks: correlation {g['predicted_growth_app'].corr(g['predicted_growth_new']):.6f}, "
              f"largest difference {(g['predicted_growth_app'] - g['predicted_growth_new']).abs().max():.6f}, "
              f"same alert {100 * (g['alert_app'] == g['alert_new']).mean():.1f}%, "
              f"same top 10 {len(top_app & top_new)}/10")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("pull", help="download the latest Google Trends data")
    b = sub.add_parser("build", help="add new weeks, forecast them and refresh the app data")
    b.add_argument("--pull", required=True, help="the download to use, e.g. update/data/pulls/pull_2026-11-15.csv")
    b.add_argument("--skip-export", action="store_true", help="skip refreshing search history and explanations")
    c = sub.add_parser("check", help="recompute one week already in the app and compare")
    c.add_argument("--as-of", required=True, help="a forecast week in the app, e.g. 2026-10-11")
    args = parser.parse_args()
    {"pull": cmd_pull, "build": cmd_build, "check": cmd_check}[args.command](args)


if __name__ == "__main__":
    main()
