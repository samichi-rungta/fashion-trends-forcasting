# results/google_trends (Person 1)

Shared format agreed with the team. All dates are week start dates (Sundays).

| File | Content |
|---|---|
| predictions.csv | date (forecast-origin week, when the forecast was made), item (keyword), horizon (4 or 8), actual, predicted, model, period (validation/test). Models: last_value, avg_4w, seasonal_naive, ets, ridge, lasso |
| scores.csv | model, period, horizon, scope (all / 2025_only / no_spike / no_spike_window), n_rows, n_items, mae, rmse, mase, direction_acc |
| scores_by_category.csv | same scores for the test period by keyword category |
| prepared_dataset.csv.gz | shared prepared dataset (eligible rows). One row per origin week, keyword and horizon, with inputs, target and period label |
| feature_list.json | list of input columns, and how the target and predictions are scaled |
| splits.json | validation folds, test start and refit schedule |
| coefficients.csv / coefficients_summary.csv | Ridge and Lasso coefficients (standardised inputs) for every 4-weekly refit, and their mean over refits |
| tuning_results.csv | validation MAE for every alpha and fold; chosen = True marks the selected alpha |
| significance_tests.csv | paired Diebold-Mariano and forecast-origin block-bootstrap comparisons |
| seasonal_decomposition_summary.csv and seasonal_decomposition_*.csv | 52-week decomposition summaries and components for representative series |
| keyword_info.csv, spike_weeks.csv, trends_weekly_prepared.csv | cleaning flags per keyword, flagged spike weeks, cleaned weekly table |
| figures/ | forecast examples, score comparison, tuning curves, coefficients, seasonal decompositions |

Scaling used by the models: every input and the target are divided by the 4-week average at the origin week (base);
predicted = max(model output, 0) * base.

> **Important Note on Wed Nov 11 18:05:21 +07 2026:** In , Wed Nov 11 18:05:21 +07 2026 is the **week the forecast was made (the forecast origin)**,
> **NOT** the future week being predicted. The week being predicted is .
