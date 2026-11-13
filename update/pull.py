"""Download the latest weekly Google Trends data for every style.

Same settings as the original download in google_trends_eda.ipynb: one style per request,
worldwide, "today 5-y" (weekly), 8 seconds between requests, up to 3 tries with a 60-second wait,
and Google's unfinished last week dropped. Each style is cached as soon as it arrives, so a run
that stops (for example after a rate limit) continues where it left off.
"""
import time
from pathlib import Path

import pandas as pd

TIMEFRAME = "today 5-y"
GEO = ""                # "" = worldwide, as in the original download
SLEEP_SECONDS = 8
TRIES = 3
WAIT_AFTER_FAIL = 60


def _cache_file(cache_dir: Path, style: str) -> Path:
    return cache_dir / f"{style.replace(' ', '_')}.csv"


def download(styles: list, cache_dir: Path) -> tuple[pd.DataFrame, list]:
    """Return (weekly table of all styles that downloaded, list of styles that failed)."""
    from pytrends.request import TrendReq   # imported here so the tests do not need pytrends

    cache_dir.mkdir(parents=True, exist_ok=True)
    client = TrendReq(hl="en-US", tz=0)
    series, failed = {}, []
    for i, style in enumerate(styles, 1):
        path = _cache_file(cache_dir, style)
        if path.exists():
            series[style] = pd.read_csv(path, index_col=0, parse_dates=True)[style]
            print(f"{i}/{len(styles)} {style}: cached")
            continue
        for attempt in range(1, TRIES + 1):
            try:
                client.build_payload([style], timeframe=TIMEFRAME, geo=GEO)
                data = client.interest_over_time()
                if data.empty:
                    raise ValueError("no data returned")
                data = data[~data["isPartial"].astype(bool)]      # drop the unfinished last week
                data[[style]].to_csv(path)
                series[style] = data[style]
                print(f"{i}/{len(styles)} {style}: ok ({len(data)} weeks)")
                break
            except Exception as error:   # rate limits and network errors: wait and try again
                print(f"{i}/{len(styles)} {style}: try {attempt} failed ({type(error).__name__})")
                if attempt < TRIES:
                    time.sleep(WAIT_AFTER_FAIL)
        else:
            failed.append(style)
        time.sleep(SLEEP_SECONDS)
    table = pd.DataFrame(series)
    table.index.name = "date"
    return table, failed
