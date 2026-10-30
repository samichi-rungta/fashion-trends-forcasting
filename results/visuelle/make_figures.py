import matplotlib
matplotlib.use('Agg')
display = lambda x: print(x.to_string())
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

FIG = "results/visuelle/figures"
os.makedirs(FIG, exist_ok=True)
pred = pd.read_csv("results/visuelle/predictions.csv", parse_dates=["date"])
pred["abs_err"] = (pred["actual"] - pred["predicted"]).abs()

MODELS = ["last_value", "mean_last_4w", "ridge", "ridge_search", "xgboost", "xgboost_search"]
COLORS = {"last_value": "#999999", "mean_last_4w": "#c9c9c9", "ridge": "#6baed6", "ridge_search": "#08519c",
          "xgboost": "#fd8d3c", "xgboost_search": "#a63603"}

# 1. Forecast comparison: MAE of every model, by horizon and period.
mae = pred.groupby(["period", "horizon", "model"])["abs_err"].mean().unstack("model")[MODELS]
fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
for ax, period in zip(axes, ["validation", "test"]):
    sub = mae.loc[period]
    x = np.arange(len(sub))
    width = 0.13
    for i, m in enumerate(MODELS):
        ax.bar(x + (i - 2.5) * width, sub[m], width, label=m, color=COLORS[m])
    ax.set_xticks(x, [f"{h} weeks ahead" for h in sub.index])
    ax.set_title(f"{period.capitalize()} MAE (units per in-stock listing-week)")
axes[0].set_ylabel("MAE (lower is better)")
axes[1].legend(ncol=2, fontsize=8)
plt.tight_layout()
plt.savefig(f"{FIG}/01_model_comparison_mae.png", dpi=150)
plt.show()

# 2. Example forecasts on the test season: items with the most weeks, 4 weeks ahead.
h = 4
test_h = pred[(pred["period"] == "test") & (pred["horizon"] == h)]
examples = test_h.groupby("item")["date"].nunique().sort_values(ascending=False).index
examples = [i for i in examples if i.startswith("category:")][:4]
fig, axes = plt.subplots(2, 2, figsize=(13, 7), sharex=True)
for ax, it in zip(axes.ravel(), examples):
    d = test_h[test_h["item"] == it]
    act = d[d["model"] == "xgboost"].sort_values("date")
    ax.plot(act["date"], act["actual"], color="black", lw=2.2, label="actual")
    for m in ["last_value", "xgboost", "xgboost_search"]:
        s = d[d["model"] == m].sort_values("date")
        ax.plot(s["date"], s["predicted"], color=COLORS[m], lw=1.4, ls="--" if m == "last_value" else "-", label=m)
    ax.set_title(it)
    ax.tick_params(axis="x", rotation=30)
axes[0, 0].legend(fontsize=8)
fig.suptitle(f"Test season (AW19): {h}-week-ahead forecasts vs actual (units per in-stock listing)")
plt.tight_layout()
plt.savefig(f"{FIG}/02_example_forecasts_test_4w.png", dpi=150)
plt.show()

# 3. Search contribution: each model vs its own no-search twin on exactly the same rows.
rng = np.random.default_rng(0)
rows, by_item = [], []
for fam in ["ridge", "xgboost"]:
    for period in ["validation", "test"]:
        for h in [4, 8]:
            a = pred[(pred["model"] == fam) & (pred["period"] == period) & (pred["horizon"] == h)]
            b = pred[(pred["model"] == fam + "_search") & (pred["period"] == period) & (pred["horizon"] == h)]
            j = a.merge(b, on=["date", "item"], suffixes=("_ns", "_s"))
            j["diff"] = j["abs_err_s"] - j["abs_err_ns"]  # negative = search helped
            per_week = j.groupby("date")["diff"].mean().to_numpy()
            boot = [per_week[rng.integers(0, len(per_week), len(per_week))].mean() for _ in range(2000)]
            rows.append({
                "family": fam, "period": period, "horizon": h, "n": len(j),
                "MAE_no_search": j["abs_err_ns"].mean(), "MAE_with_search": j["abs_err_s"].mean(),
                "MAE_change": j["diff"].mean(), "pct_change": 100 * j["diff"].mean() / j["abs_err_ns"].mean(),
                "CI_low": np.percentile(boot, 2.5), "CI_high": np.percentile(boot, 97.5),
                "share_rows_search_better": (j["diff"] < 0).mean(),
            })
            if fam == "xgboost" and period == "test":
                g = j.groupby("item")["diff"].mean().rename("MAE_change").reset_index()
                g["horizon"] = h
                by_item.append(g)
contrib = pd.DataFrame(rows)
contrib["significant"] = np.where((contrib["CI_low"] > 0) | (contrib["CI_high"] < 0), "yes", "no")
contrib.to_csv("results/visuelle/search_contribution.csv", index=False)
display(contrib.round(4))

fig, ax = plt.subplots(figsize=(9, 4.5))
lab = contrib["family"] + " " + contrib["period"].str[:4] + " " + contrib["horizon"].astype(str) + "w"
err = np.vstack([contrib["MAE_change"] - contrib["CI_low"], contrib["CI_high"] - contrib["MAE_change"]])
ax.barh(lab, contrib["MAE_change"], xerr=err, color=np.where(contrib["MAE_change"] < 0, "#2ca25f", "#de2d26"), capsize=3)
ax.axvline(0, color="black", lw=1)
ax.set_xlabel("Change in MAE when search is added (negative = search helps), 95% CI over weeks")
ax.invert_yaxis()
plt.tight_layout()
plt.savefig(f"{FIG}/03_search_contribution.png", dpi=150)
plt.show()

# 4. Where does search help or hurt? Test, XGBoost, per item.
bi = pd.concat(by_item)
fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharex=True)
for ax, h in zip(axes, [4, 8]):
    s = bi[bi["horizon"] == h].sort_values("MAE_change")
    s = pd.concat([s.head(8), s.tail(8)])
    ax.barh(s["item"], s["MAE_change"], color=np.where(s["MAE_change"] < 0, "#2ca25f", "#de2d26"))
    ax.axvline(0, color="black", lw=1)
    ax.set_title(f"{h} weeks ahead: 8 best / 8 worst items")
    ax.set_xlabel("Change in MAE with search (negative = helps)")
plt.tight_layout()
plt.savefig(f"{FIG}/04_search_by_item_xgboost_test.png", dpi=150)
plt.show()
bi.to_csv("results/visuelle/search_contribution_by_item_xgboost_test.csv", index=False)

# 5. Does search help items that have a series at all? Compare tags with a VISUELLE series vs others.
vis_cols = set(pd.read_csv("data/visuelle2/vis2_gtrends_data.csv", nrows=1).columns)
bi["has_search_series"] = bi["item"].str.split(":", n=1).str[1].isin(vis_cols)
cov = bi.groupby(["horizon", "has_search_series"])["MAE_change"].agg(["mean", "count"]).round(4)
display(cov)

