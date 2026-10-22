# Fashion Trend Forecasting

Machine learning group project: forecasting which fashion styles are about to rise, using search interest, social-media popularity and real retail sales.

> **Status:** proposal stage. The only code so far is data collection, cleaning and EDA (see [Google Trends pull and EDA notebook](#6-google-trends-pull-and-eda-notebook)). Modelling, experiments and deployment are planned, not built.

## Contents

1. [Project idea in brief](#1-project-idea-in-brief)
2. [Datasets](#2-datasets)
3. [Design decisions](#3-design-decisions)
4. [Planned experiments](#4-planned-experiments)
5. [Repository structure](#5-repository-structure)
6. [Google Trends pull and EDA notebook](#6-google-trends-pull-and-eda-notebook)
7. [Known limitations and differences from the original plan](#7-known-limitations-and-differences-from-the-original-plan)
8. [Plan of work](#8-plan-of-work)
9. [Team, credits and licenses](#9-team-credits-and-licenses)

---

## 1. Project idea in brief

**Problem.** Fast-fashion retailers must decide what to stock weeks or months before demand peaks, and consumers want to know which styles are coming. Today this relies largely on intuition and lagging sales reports. Ordering too early or too late means overstock or lost sales (for example with cargo pants or ballet flats).

**Proposed ML application.** Forecast search interest for named fashion styles (for example low-rise jeans, cargo pants, ballet flats) 4 to 8 weeks ahead, rank styles by predicted growth, and show them in a web app with suggested ordering windows based on supplier lead time. The current data collection covers 137 keywords across two stitched weekly windows (2017-06 to present, ~9 years total).

**Intended users.**
1. Fast-fashion buyers and merchandisers (what to stock, when to order).
2. General consumers curious about upcoming styles.

**Prediction targets.**
- Future weekly search interest per style (regression).
- Whether a style is "rising" or not (classification, growth direction).
- A growth ranking of styles.
- Weekly product sales in the VISUELLE experiment.

**Core approach.** Three complementary views of a trend, each evaluated separately and never pooled:

| Lens | Question | Dataset |
| --- | --- | --- |
| What people search for | Can past search interest forecast future interest? | Google Trends |
| What attracts social-media attention | Do influencer signals improve trend forecasts? | F1 / HERMES |
| What people actually buy | Does search interest improve sales forecasts? | VISUELLE 2.0 (optionally H&M) |

**Baselines and models.**
- Baselines: last observed value, and the average of the last 4 weeks.
- Models: regularized regression (Ridge / Lasso), then gradient-boosted trees (LightGBM or XGBoost).

**Metrics.** MAE, precision of the top-K predicted rising styles, and growth-direction accuracy.

**Success criteria.**
- ML level: lower MAE than both baselines and higher growth-direction accuracy.
- Business level: precision of the top-K predicted rising styles, and how many weeks of lead time the forecast gives before a style peaks.

**Deployment (planned).** A web app on AWS or Azure showing forecasts, upcoming styles and suggested order periods. Architecture: cloud storage for cleaned data and models, a scheduled weekly job that refreshes Google Trends and re-scores the styles, a small API, and a simple front end. CI/CD via Git, with lint and tests on every push.

**What the system does not claim.** Search interest is a proxy for demand, not sales, and the forecasts do not prove causation.

---

## 2. Datasets

### Core datasets

| Dataset | What it is | Role | Key limits |
| --- | --- | --- | --- |
| **Google Trends** (primary) | Relative search interest (0 to 100) per keyword, weekly | Main forecasting target; also a feature source for the retail experiments | Values are relative and rescaled per query; ambiguous keywords; search is not sales; rate limits |
| **F1 / HERMES** | 10,000 weekly fashion time series from social media, plus 10,000 matching influencer ("weak") signals, normalized and anonymized | Benchmark for forecasting methods and for the influencer-signal ablation | Anonymized, so styles cannot be named; date range, length and license unconfirmed; social popularity, not sales |
| **VISUELLE 2.0** | Weekly sales, stock, prices and discounts for 5,355 products of Nuna Lie (Italian fast-fashion brand), 6 seasons in 2017 to 2019; tags, images, bundled Google Trends, weather and customer data | Tests whether search interest improves sales forecasts | One brand, about 3 years; file format and license to verify after download |
| **H&M Personalized Fashion Recommendations** (optional) | About 31M transactions, 105,542 articles, about 1.3M customers, roughly Sep 2018 to Sep 2020 | Second retailer, to check whether the VISUELLE findings generalize | About 2 years only; includes the COVID-19 shock; Google Trends must be pulled separately for the matching period; prices are scaled, not real currency |

Download links:
- Google Trends: pulled by the notebook in this repo (see section 6).
- F1 / HERMES: <https://github.com/etidav/f1fashiondataset> (archive: <http://files.heuritech.com/raw_files/f1_fashion_dataset.tar.xz>, containing `f1_main.csv` and `f1_fashion_forward.csv`)
- VISUELLE 2.0: <https://humaticslab.github.io/forecasting/visuelle>
- H&M: <https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations>

### Supporting sources (fallbacks or extra features, not in the core plan)

- **Wikipedia Pageviews**: absolute view counts since 2015, a second interest signal and a backup if Google Trends is blocked.
- **FRED** (UMCSENT, UNRATE, CPIAUCSL): economic indicators for an ablation test.
- **NYT Archive API, CoPA and FashionDB**: long-history sources for the 20-year cycle idea.
- **FIT (Instagram trends) and Amazon Reviews 2023**: other social and review-based signals.

The full list of candidate datasets that the team collected, with a description and applications for each, is in `docs/` (see the repository structure below).

---

## 3. Design decisions

Items marked *(proposed)* have not been confirmed by the whole team yet.

| Decision | Choice | Why |
| --- | --- | --- |
| Forecast target | Weekly Google Trends interest per style keyword, 4 and 8 weeks ahead | Matches the retail ordering window; weekly is the finest resolution Google offers for multi-year ranges |
| Keyword set | 137 style keywords across garments, shoes, bags, colors and aesthetics; each pulled alone with no anchor term | Enough variety to rank styles; no anchor means values are comparable over time *within* a keyword but **not between keywords** — absolute levels across styles cannot be compared |
| Region and language | One fixed region and language for every pull *(proposed: worldwide, English)* | Mixing regions makes series incomparable |
| History window | Two overlapping weekly windows stitched into ~9 years (2017-06 to present) | Google returns weekly data only for ranges up to ~5 years, so two windows are pulled and the older one is rescaled to match the recent one over their ~28-week overlap |
| Definition of "rising" | Mean interest over the next 4 weeks divided by the mean over the last 4 weeks, above a threshold (set from EDA; candidates: 1.1 or 1.2) | Gives precision and growth-direction accuracy a precise, within-keyword meaning |
| Data split | Chronological train / validation / test, with rolling-origin validation inside the training part *(proposed: roughly 70/15/15)* | Random splits leak the future in time series |
| Backtest framing | Hold-out of the most recent period inside each dataset, not a 2022 to 2023 backtest | VISUELLE ends in 2019 and H&M in 2020, so they cannot support it |
| Baselines | Last observed value; average of the last 4 weeks | Simple, hard-to-beat references for short horizons |
| Models | Ridge / Lasso, then gradient-boosted trees; one global model across keywords | Interpretable first, then a stronger non-linear model; short history per series |
| Evaluation scope | Each dataset evaluated separately, never pooled | Different units, periods and meanings of "popularity" |
| F1 handling | Separate benchmark only; no join with other data | Series are anonymized, so no style can be matched |
| Synthetic data | Not used | Real data is available for every experiment |

Leakage prevention: rolling statistics and scalers use past data only, the target week never appears in the features, the test period is never used for tuning, and any rescaling is fixed before the split.

---

## 4. Planned experiments

| # | Question | Data | Variants compared | Metrics |
| --- | --- | --- | --- | --- |
| E1 | Can past search interest forecast future interest better than a simple rule? | Google Trends keywords | Two baselines vs. Ridge/Lasso vs. boosted trees; horizons of 4 and 8 weeks | MAE, growth-direction accuracy, precision at top-K |
| E2 | Do influencer signals improve social-media trend forecasts? | F1 / HERMES | Same models with vs. without the weak signal | MAE, growth-direction accuracy |
| E3 | Does search interest improve sales forecasts? | VISUELLE | Same models with vs. without Google Trends features | MAE, growth-direction accuracy |
| E4 (optional) | Do the E3 findings hold for another retailer? | H&M plus Google Trends | Same design as E3 | MAE, growth-direction accuracy |

Planned analysis: error breakdowns, feature importance (coefficients, permutation importance, SHAP), seasonality vs. trend decomposition, lead-lag between search and sales, sensitivity to the "rising" threshold and top-K size, ablations by feature group, and robustness across low-volume vs. high-volume keywords and 4 vs. 8 week horizons.

---

## 5. Repository structure

Suggested layout (adjust to match what is actually committed):

```
.
├── README.md
├── .gitignore
├── requirements.txt
├── google_trends_eda.ipynb          # pull + cleaning + EDA for Google Trends
├── google_trends_keywords.xlsx      # INPUT: keyword list (sheet "Keywords")
├── raw_pulls/                       # generated: one CSV per keyword and window (tracked on purpose)
│   ├── trends_weekly_raw.csv            # generated: stitched table, all keywords
│   ├── trends_weekly_clean.csv          # generated: low-volume keywords removed
│   ├── trends_weekly_nospike.csv        # generated: spike weeks blanked and short gaps filled
│   ├── trends_spike_weeks.csv           # generated: flag per week
├── data/
│   ├── raw/                         # large downloads (F1, VISUELLE, H&M); NOT tracked
│   └── processed/                   # small cleaned files, tracked if needed
└── docs/                            # project brief and dataset collection PDFs
```

Large third-party datasets (H&M, VISUELLE, F1 archives) are not committed. Download them into `data/raw/` using the links in section 2; that folder is ignored by git.

---

## 6. Google Trends pull and EDA notebook

`google_trends_eda.ipynb` is the first piece of code in the project. It pulls weekly Google Trends data for the team's fashion keywords, cleans it, and runs basic EDA to support the decisions listed in section 3 (zero-share cut-off, "rising" threshold, outlier handling, seasonality).

### What it does

1. **Pulls** weekly interest for every keyword in the keyword file. Each keyword is requested alone (no anchor term), so it is scaled to its own 0 to 100 range.
2. **Stitches two windows.** Google only returns weekly data for ranges up to about 5 years, so the notebook pulls a recent window (`today 5-y`) and an older window (`2017-06-04 2022-04-30`) that overlap by about 28 weeks. The older window is multiplied by a factor that makes its average match the recent window over the overlap. Keywords with very low volume in the overlap are listed as having an unreliable stitch factor.
3. **Cleans.** Drops the incomplete last week, drops keywords with more than 30% zero weeks (`ZERO_CUTOFF = 0.30`), and flags weeks in which many unrelated keywords spike together, producing a second version with those weeks blanked and short gaps interpolated.
4. **Runs EDA.** Summary statistics, trends by category, seasonality (median by week of year and lag-52 autocorrelation), rising and falling keywords, correlations of weekly changes, the distribution of 4-week changes (to choose the "rising" threshold), a spike-week check, a sensitivity check without spike weeks, a year-by-year seasonality view, STL decomposition, class balance of the "rising" label by year, and a stability check that re-pulls three keywords.
5. **Saves** the cleaned tables for later modelling.

### Inputs

`google_trends_keywords.xlsx` must be in the same folder as the notebook, with a sheet named `Keywords` and two columns:

| Column | Meaning |
| --- | --- |
| `Keyword` | The search term to pull (for example `cargo pants`) |
| `Category` | The category it belongs to (for example jeans, trousers, shoes, outerwear, aesthetics) |

The current list has 137 keywords.

### Settings

Edit the settings cell near the top of the notebook:

| Setting | Default | Meaning |
| --- | --- | --- |
| `GEO` | `""` | Region for every pull (`""` = worldwide). Keep it the same for every pull. |
| `RECENT_WINDOW` | `"today 5-y"` | Weekly window covering the last 5 years |
| `OLD_WINDOW` | `"2017-06-04 2022-04-30"` | Earlier weekly window; must overlap the recent window by roughly 28 weeks |
| `TEST_RUN` | `False` | `True` pulls one keyword per category (about 11 keywords) as a quick check |
| `SLEEP_SECONDS` | `8` | Pause between requests, to avoid rate limits |
| `SAVE_DIR` | `"raw_pulls"` | Where each pulled keyword is cached |

### How to run

**Option A: Google Colab (the notebook was developed this way)**

1. Open `google_trends_eda.ipynb` in Colab.
2. Upload `google_trends_keywords.xlsx` to the session (folder icon on the left, then the upload button).
3. Keep `TEST_RUN = True` for the first run to check that everything works, then set it to `False` for the full pull.
4. Run all cells. Download the generated CSVs (and `raw_pulls/`) before the session ends, because Colab storage is temporary.

**Option B: locally**

```bash
git clone <repo-url>
cd <repo-folder>

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

jupyter lab                        # then open google_trends_eda.ipynb
```

Make sure `google_trends_keywords.xlsx` is in the same folder as the notebook, because the notebook uses relative paths. The first code cell runs `!pip install pytrends`, which is harmless if it is already installed.

**Run time.** A full pull makes about 274 requests (137 keywords, two windows) with an 8-second pause each, so allow at least 40 minutes, more if Google rate-limits you.

### Rate limits and re-runs

- Google may block you with an HTTP 429 error if you pull too fast. The code waits 60 seconds and retries up to 3 times per keyword. If a keyword still fails, wait a few minutes and re-run the pull cell.
- Every pulled keyword is saved in `raw_pulls/`. A re-run skips keywords that are already cached, so only failed or new keywords are requested again. Delete `raw_pulls/` to force a completely fresh pull.
- Cached files from a `TEST_RUN = True` run are reused by the full pull.
- To skip the pull entirely when reopening the notebook, load the saved table:
  ```python
  df = pd.read_csv("trends_weekly_raw.csv", index_col=0, parse_dates=True)
  ```
  (there is a commented-out line for this in section 4 of the notebook).
- **Reproducibility.** `RECENT_WINDOW = "today 5-y"` moves with the calendar and Google's sampling changes the numbers slightly between pulls. To work with exactly the data used in the analysis, use the committed `raw_pulls/` and `trends_weekly_*.csv` files instead of pulling again. If you do re-pull on a later date, check that the recent and old windows still overlap, and that both come back with a 7-day step (the notebook prints this check).

### Outputs

| File | Contents |
| --- | --- |
| `raw_pulls/` | One CSV per keyword and window (cache of the raw pulls) |
| `trends_weekly_raw.csv` | Stitched weekly table, all keywords (489 weeks by 137 keywords in the last full pull) |
| `trends_weekly_clean.csv` | Same, with low-volume keywords removed |
| `trends_weekly_nospike.csv` | Cleaned table with flagged spike weeks blanked and short gaps interpolated |
| `trends_spike_weeks.csv` | True/False flag per week for the spike weeks |

### Notebook map

| Section | What it does |
| --- | --- |
| Settings, keyword list, pull | Loads the keywords and pulls each one for both windows |
| 3b to 3c: stitch and checks | Scales the old window to the recent one, lists weak stitches, plots a few series with the seam marked |
| 4: first look | Shape, date range, head, missing values |
| 5: basic cleaning | Summary table (zero share, unique values, peak-to-mean) and the zero-share filter |
| 6.2 to 6.6 | Category trends, seasonality, rising and falling keywords, correlations, the "rising" threshold |
| 7 to 8 | Spring 2026 spike check and the sensitivity of seasonality to it |
| 9 to 10 | Year-by-year seasonality and STL decomposition for one keyword |
| 11 to 12 | Class balance of the "rising" label by year; stability of repeated pulls |
| 13 | Saves the cleaned files |
| Final markdown cell | Written analysis of the full pull and a list of next steps |

### Main findings so far (full pull, 137 keywords, 2017-06 to 2026-10)

These come from the analysis cell at the end of the notebook and are preliminary.

- **Coverage.** 489 weekly observations for all 137 keywords. Both windows came back weekly and the 28-week overlap stitched without errors. The only missing values come from `mob wife aesthetic`, which has no data in the older window. Six keywords have an unreliable stitch factor because of low volume in the overlap (`barrel jeans`, `balloon skirt`, `oversized sunglasses`, `floral print`, `quiet luxury`, `balletcore`).
- **Zero-share filter removes the wrong keywords.** The 30% cut-off dropped `balletcore`, `clean girl aesthetic` and `gorpcore`. These are emerging aesthetics whose zeros reflect when the term appeared, not low volume today, and they are exactly the kind of trend the project wants to forecast.
- **Trends.** `ballet flats` rose strongly from 2023 and stays high after the 2026 spike, which looks like a sustained revival. `cargo pants` rose to about 2023 to 2024 and then fell back. `skinny jeans` declined slowly.
- **Seasonality.** Outerwear is the only clearly seasonal category (peak around mid-November). Lag-52 autocorrelation is high mostly for strongly trending keywords, so a detrended measure is needed before ranking keywords by seasonality.
- **Market-wide movement.** Nearly every keyword went up in the last year, and even unrelated keywords correlate positively. A market-wide factor (or a change in how Google scales the data) is mixed in with style-specific changes.
- **Spring 2026 spike.** Many unrelated keywords jumped together in several weeks of 2026. With `SPIKE_SHARE = 0.5`, only 4 weeks were flagged, so the "no spike" version still contains most of the spike. The cause is unknown.
- **"Rising" threshold.** Share of keyword-weeks above each threshold: above 1.1 is 24.1%, above 1.2 is 11.9%, above 1.3 is 6.9%, above 1.5 is 2.9%.

### Open items from the notebook analysis

1. `mob wife aesthetic`: fill the weeks before it appears with 0, or start its series at 2021-10, and log the choice.
2. Replace the zero-share filter with one measured over the last 104 weeks (plus a minimum number of distinct values), and re-include `balletcore`, `clean girl aesthetic` and `gorpcore` with an "emerging" flag.
3. Lower `SPIKE_SHARE` to about 0.25 so all spike weeks are flagged; check non-fashion control keywords and a single-country region for the same weeks.
4. Add a market-wide index and relative-strength features.
5. Use a detrended seasonality measure (STL seasonal strength) and consider working with logs or ratios.
6. For weak-stitch keywords, use only the recent window or leave them out of long-history experiments; look at the `blazer` seam.
7. Extend the correlation heatmap beyond the first 20 keywords and check COVID effects on `leggings`, `joggers` and `sweatpants`.
8. Review the 2023 to 2026 class balance and the stability check, then choose between a 1.1 and 1.2 "rising" threshold.

---

## 7. Known limitations and differences from the original plan

The project brief was written before the Google Trends pull. Where the notebook differs, the proposal and the notebook should be aligned before submission:

The decisions in section 3 have been updated to reflect what the notebook implements. The main differences from the original brief were:

| Topic | Original brief | Implemented |
| --- | --- | --- |
| History window | ~5 years of weekly data | Two overlapping weekly windows stitched into ~9 years (2017-06 to present) |
| Anchor terms | Pull keywords in batches with a shared anchor; rescale through it | Each keyword pulled alone, no anchor; values comparable within a keyword only |
| Keyword count | 50–100 keywords | 137 keywords |
| Cleaning | Zero-share cut-off, anchor rescaling, flag outliers | Zero-share cut-off (30%), window stitching with overlap rescaling, spike-week flagging |

Other limitations:
- Google Trends is relative (0 to 100), sampled, and measures attention, not purchases. Low-volume keywords return many zeros, and some keywords have non-fashion meanings.
- F1 is anonymized, so no style can be named, and its dates and license are unconfirmed.
- VISUELLE covers one Italian brand over about three years; H&M covers about two years that include the COVID-19 shock.
- The datasets cover different periods and cannot be pooled, so each result stands alone.
- Results describe the chosen region and language only.

Risks and fallbacks: if Google Trends access fails, use cached pulls or Wikipedia Pageviews; if the search signal is weak, report that as a finding and shift weight to F1; if the tag-to-keyword mapping is too noisy, match at category level; if a dataset license blocks use, swap in another from the candidate list. Minimum scope is Google Trends plus VISUELLE, with F1 and H&M as extensions.

---

## 8. Plan of work

1. Confirm the *(proposed)* decisions in section 3.
2. Download all datasets and check licenses and file formats.
3. Pull and clean the Google Trends keyword set (done for the first full pull; open items above).
4. Run EDA and cleaning for F1, VISUELLE and (if kept) H&M, with one notebook per dataset and the same layout: load, inspect, clean, EDA, save.
5. Collect figures and a cleaning log (dataset, issue, rows or series affected, action, reason).
6. Write the report sections: problem statement, data preparation, model selection, experimental design, analysis plan, additional considerations.
7. Build the slide deck from the report.
8. Review everything together for consistency, then rehearse the presentation.

Deliverables: a PDF proposal report and a slide deck (PPT/PPTX), submitted on the course platform before the deadline.

---

## 9. Team, credits and licenses

**Team:** add team members here.

**Credits.**
- F1 / HERMES dataset: David, Le Corff and Bellot, *HERMES: Hybrid Error-Corrector Model with inclusion of External Signal for non-stationary time series* (<https://arxiv.org/abs/2202.03224>).
- VISUELLE 2.0: Skenderi et al., *The Multi-Modal Universe of Fast-Fashion: the Visuelle 2.0 Benchmark* (CVPR Workshops 2022).
- H&M Personalized Fashion Recommendations: Kaggle competition hosted by H&M.
- Google Trends data is accessed through the unofficial `pytrends` library.

**Licenses.** Each dataset keeps its own license and terms of use; check them before redistributing any data. Add a license for this repository's code here.
