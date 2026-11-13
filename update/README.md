# Weekly update

Keeps the buyer app's forecasts current. Once a week, from a laptop, with the virtual environment active,
from the repository root:

```
python update/weekly_update.py pull
python update/weekly_update.py build --pull update/data/pulls/pull_<date>.csv
cd deployment ; python -m pytest -q ; cd ..
```

Then commit `update/data/` and `deployment/data/` on a new branch and open a pull request. When it is merged,
the CI/CD pipeline tests, builds and deploys the new data like any other change.

## What each step does

1. **pull** downloads the last 5 years of weekly Google Trends data for every style, with the same
   settings as the original download (one style per request, worldwide, 8 seconds apart, unfinished
   last week dropped). It takes about 25 minutes. If Google rate-limits the run, wait and run it again:
   finished styles are cached in `update/data/cache/` (not kept in Git).
2. **build**
   - scales the download to the stored data over their shared weeks (the same ratio-of-means method that
     joined the two original download windows) and appends only the new weeks to
     `update/data/trends_weekly_live.csv`; stored weeks are never changed;
   - stops if a style's download does not match its stored history (overlap correlation below 0.5);
   - forecasts every new week with the final LightGBM model (`analysis/rebuild_lightgbm.py`): same inputs,
     tuned settings, 5 seeds averaged, retraining every 4 weeks on the same schedule as the final test,
     and the same out-of-range flag;
   - appends the forecasts to `deployment/data/rankings.csv` and fills in what actually happened for older
     forecasts whose answer is now known;
   - refreshes `deployment/data/search_history.csv` and `explanations.csv` (about 7 minutes).
3. **check** (`--as-of <week>`) recomputes a week that is already in the app from the frozen study data and
   compares it with the app's file, to show that the update reproduces the final test's forecasts.

## Why it runs from a laptop

Google often refuses automated requests from cloud servers such as GitHub's, while the same requests work
from a home or university connection. A scheduled cloud job is left as future work.

## Files

| Path | Content | In Git |
|---|---|---|
| `core.py` | joining, refit schedule, rankings format (pure pandas, unit-tested) | yes |
| `pull.py`, `forecast.py`, `weekly_update.py` | download, forecasting, the command | yes |
| `data/trends_weekly_live.csv` | study data plus every week added since | yes |
| `data/pulls/pull_<date>.csv` | each download as received, for reproducibility | yes |
| `data/cache/` | per-style files during a download | no |
| `tests/` | `python -m pytest -q update/tests` | yes |

The study files in `results/` are never changed by the update, so the report's results stay reproducible.
