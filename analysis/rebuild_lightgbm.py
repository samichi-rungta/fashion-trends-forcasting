"""Recreate the LightGBM model from google_trends_models.ipynb, to explain specific weeks.

Same inputs, target, filters and tuned settings as the modelling notebook, so the
rebuilt model reproduces its seed-0 predictions. Used by 05_feature_importance.ipynb
to compute SHAP values for chosen periods (for example the months after the spike).
"""
import numpy as np
import pandas as pd
import lightgbm as lgb

from common import RESULTS, WEEKLY_FILE, KEYWORD_FILE

EPS, MIN_LEVEL = 1.0, 5.0
TUNING_FILE = RESULTS / "tuning_results_lightgbm_logistic.csv"


def _logratio(a, b):
    return np.log((a + EPS) / (b + EPS))


def build_table() -> tuple[pd.DataFrame, list]:
    """All inputs for every week and style, exactly as in the modelling notebook."""
    wide = pd.read_csv(WEEKLY_FILE, index_col=0, parse_dates=True).sort_index()
    category = dict(pd.read_csv(KEYWORD_FILE)[["item", "category"]].values)
    last4 = wide.rolling(4).mean()
    feats = {}
    for k in [0, 1, 2, 4, 8, 12, 26]:
        feats[f"lag{k}"] = _logratio(wide.shift(k), last4)
    for k in [4, 8, 12]:
        feats[f"growth{k}"] = _logratio(last4, last4.shift(k))
    feats["accel"] = feats["growth4"] - feats["growth4"].shift(4)
    feats["vol8"] = wide.rolling(8).std() / (last4 + EPS)
    feats["vol26"] = wide.rolling(26).std() / (wide.rolling(26).mean() + EPS)
    feats["lag52"] = _logratio(wide.shift(52), last4)
    for h in [4, 8]:
        feats[f"last_year_growth{h}"] = _logratio(last4.shift(52 - h), last4.shift(52))
    market = feats["growth4"].mean(axis=1)
    feats["market_growth4"] = pd.DataFrame({c: market for c in wide.columns})
    feats["rel_growth4"] = feats["growth4"].sub(market, axis=0)

    idx = pd.MultiIndex.from_product([wide.index, wide.columns], names=["date", "item"])
    table = pd.DataFrame({n: f.reindex(index=wide.index, columns=wide.columns).to_numpy().ravel()
                          for n, f in feats.items()}, index=idx)
    table["last4_avg"] = last4.to_numpy().ravel()
    for h in [4, 8]:
        table[f"actual_h{h}"] = last4.shift(-h).to_numpy().ravel()
    table = table.reset_index()
    week = table["date"].dt.isocalendar().week.astype(float)
    table["week_sin"] = np.sin(2 * np.pi * week / 52)
    table["week_cos"] = np.cos(2 * np.pi * week / 52)
    table["category"] = pd.Categorical(table["item"].map(category).fillna("Unknown"))
    numeric = list(feats.keys()) + ["week_sin", "week_cos"]
    return table, numeric


def rows_for(table: pd.DataFrame, numeric: list, h: int) -> pd.DataFrame:
    """Usable rows for horizon h, with the target (log growth)."""
    d = table.dropna(subset=numeric).copy()
    d = d[d["last4_avg"] >= MIN_LEVEL]
    d["actual"] = d[f"actual_h{h}"]
    d["target"] = _logratio(d["actual"], d["last4_avg"])
    d["target_date"] = d["date"] + pd.Timedelta(weeks=h)   # when the answer becomes known
    return d.reset_index(drop=True)


def tuned_settings(h: int) -> dict:
    """The LightGBM setting with the lowest average validation MAE."""
    t = pd.read_csv(TUNING_FILE)
    t = t[(t["model"] == "lightgbm") & (t["horizon"] == h)]
    row = t[t["setting"] == t.groupby("setting")["mae"].mean().idxmin()].iloc[0]
    return {"n_estimators": int(row["n_estimators"]), "learning_rate": float(row["learning_rate"]),
            "num_leaves": int(row["num_leaves"]), "min_child_samples": int(row["min_child_samples"])}


def fit_model(d: pd.DataFrame, features: list, h: int, cutoff, seed: int = 0):
    """Train on every row whose answer was known by `cutoff` (no peeking at the future)."""
    model = lgb.LGBMRegressor(**tuned_settings(h), subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.8, random_state=seed, verbose=-1)
    train = d[(d["target_date"] <= cutoff) & d["actual"].notna()]
    model.fit(train[features], train["target"])
    return model


def test_shap(h: int = 4, start: str = "2025-01-01") -> pd.DataFrame:
    """SHAP values (columns shap_<input>) for every test forecast, retraining every 4 weeks as in the final test."""
    table, numeric = build_table()
    features = numeric + ["category"]
    d = rows_for(table, numeric, h)
    dates = sorted(d.loc[d["date"] >= start, "date"].unique())
    parts = []
    for i in range(0, len(dates), 4):
        block = dates[i:i + 4]
        test = d[d["date"].isin(block) & d["actual"].notna()]
        if test.empty:
            continue
        model = fit_model(d, features, h, block[0])
        contrib = model.predict(test[features], pred_contrib=True)
        out = test[["date", "item", "last4_avg", "actual", "market_growth4"]].reset_index(drop=True)
        out["predicted_growth"] = (np.exp(contrib.sum(axis=1)) * (out["last4_avg"] + EPS) - EPS).clip(lower=0) / out["last4_avg"]
        shap = pd.DataFrame(contrib[:, :-1], columns=["shap_" + f for f in features])
        parts.append(pd.concat([out, shap], axis=1))
    return pd.concat(parts, ignore_index=True)
