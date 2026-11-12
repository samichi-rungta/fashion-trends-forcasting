"""The buyer page: KPI bar, item cards or a merchandising table, item details and an order plan.

Drawn on the server as HTML. The item details (search chart, SHAP breakdown, ordering bar)
and the order plan are drawn in the browser from a small JSON block, so the page needs no
JavaScript framework. Pictures are original drawings (see pictures.py).
"""
import json
from datetime import date
from html import escape
from urllib.parse import urlencode

import numpy as np
import pandas as pd

from app.data import GROUPS
from app.pictures import picture

# Buyer actions. "Stock up" is the model's rising alert; the other bands describe the expected change.
GROWING, COOLING = 1.05, 0.95
ACTIONS = {
    "stock": "Stock up", "check": "Check first", "consider": "Consider", "steady": "Keep steady", "hold": "Hold off",
}
ADVICE = {
    "stock": "Order now, so the stock arrives while interest is climbing.",
    "check": "Look at your own sales before ordering more. The model expects a rise, but this week the whole "
             "market moved outside anything it saw in training, so its forecasts are less reliable.",
    "consider": "A small top-up is reasonable, especially if it already sells well for you.",
    "steady": "Keep your current stock level and reorder as usual.",
    "hold": "Avoid large new orders for now; extra stock may be slow to sell.",
}
GROUP_LABELS = {
    "recent_level": "Recent search level", "momentum": "Momentum", "season": "Last year's season",
    "market": "Market trend", "category": "Category",
}


def action(row) -> str:
    if row["rising"]:
        return "stock"
    if row["held_back"]:
        return "check"
    g = row["predicted_growth"]
    return "consider" if g >= GROWING else ("steady" if g > COOLING else "hold")


def date_label(iso) -> str:
    day = pd.Timestamp(iso)
    return f"{day.day} {day.strftime('%b %Y')}"  # no %-d: it does not work on Windows


def pct(ratio: float, decimals: int = 0) -> str:
    change = (ratio - 1) * 100
    if round(change, decimals) == 0:
        return "0%"
    text = f"{abs(change):.{decimals}f}%"
    return ("+" if change > 0 else "\u2212") + text


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def explanation(s, market: float, total: int, horizon: int, earlier: float | None) -> str:
    """Plain-language summary: what will happen, why, and what to do."""
    name = escape(s["style"])
    change = round((s["predicted_growth"] - 1) * 100)
    if abs(change) < 1:
        what = f"Searches for “{name}” are expected to stay about the same over the next {horizon} weeks."
    else:
        what = (f"Searches for “{name}” are expected to {'rise' if change > 0 else 'fall'} about {abs(change)}% "
                f"over the next {horizon} weeks, compared with the last 4 weeks.")
    why = [f"It ranks {ordinal(int(s['rank']))} of {total} items for this period."]
    m, vs = round((market - 1) * 100), round((s["growth_vs_market"] - 1) * 100)
    market_text = "stay about the same" if abs(m) < 1 else f"{'rise' if m > 0 else 'fall'} about {abs(m)}%"
    why.append(f"Fashion searches overall should {market_text}, so this item is "
               + ("in line with the average item." if abs(vs) < 1 else
                  f"{'ahead of' if vs > 0 else 'behind'} the average item by {abs(vs)}%."))
    if earlier is not None:
        diff = round((s["predicted_growth"] - earlier) * 100)
        why.append(f"Its forecast has strengthened over the past month (it was {pct(earlier)} four weeks ago)." if diff >= 5 else
                   f"Its forecast has weakened over the past month (it was {pct(earlier)} four weeks ago)." if diff <= -5 else
                   "Its forecast has held steady over the past month.")
    key = action(s)
    return (f"<p>{what}</p><h4>Why</h4><ul>{''.join(f'<li>{w}</li>' for w in why)}</ul>"
            f"<h4>What to do: {ACTIONS[key]}</h4><p>{ADVICE[key]}</p>")


def kpis(all_rows: pd.DataFrame, data: dict, lead: int, latest_week: str) -> str:
    horizon, week, threshold = data["horizon"], data["week"], data["rising_threshold"]
    market = data["market_growth"]
    above = int((all_rows["predicted_growth"] > threshold).sum())
    board = all_rows.groupby("category")["predicted_growth"].mean()
    lead_cat, lead_g = board.idxmax(), board.max()

    start = pd.Timestamp(week)
    arrives = start + pd.DateOffset(weeks=lead)
    ends = start + pd.DateOffset(weeks=horizon)
    if lead < horizon:
        window, window_class = (f"Orders placed on {date_label(start)} arrive {date_label(arrives)}, "
                                f"in time for the last {horizon - lead} of the {horizon} forecast weeks."), "ok"
    elif lead == horizon:
        window, window_class = f"Orders placed on {date_label(start)} arrive {date_label(arrives)}, just as the window ends.", "warn"
    else:
        window, window_class = (f"A {lead}-week lead time misses this {horizon}-week window (ends {date_label(ends)}). "
                                f"Plan orders with the 8-week view."), "late"
    age = (pd.Timestamp(date.today()) - pd.Timestamp(latest_week)).days // 7
    stale = (f'<span class="kpi-warn">Latest data is {age} weeks old: refresh it before ordering.</span>'
             if age >= 2 and week == latest_week else "")

    breakout_note = ("Alerts held back: unusual market week" if data["alerts_held_back"]
                     else f"Expected growth above {pct(threshold)}")
    return f"""<section class="kpis" aria-label="Key figures">
  <div class="kpi"><span class="kpi-label">Overall market trend</span>
    <b class="kpi-value {'down' if market < 1 else 'up'}">{pct(market, 1)}</b>
    <span class="kpi-note">All {len(all_rows)} items, next {horizon} weeks</span></div>
  <div class="kpi"><span class="kpi-label">High-conviction breakouts</span>
    <b class="kpi-value">{above}</b><span class="kpi-note">{breakout_note}</span></div>
  <div class="kpi"><span class="kpi-label">Leading category</span>
    <b class="kpi-value small">{escape(lead_cat)}</b><span class="kpi-note">Average {pct(lead_g, 1)} expected growth</span></div>
  <div class="kpi window {window_class}"><span class="kpi-label">Factory order window ({lead}-week lead time)</span>
    <span class="kpi-text">{window}</span>{stale}</div>
</section>"""


def item_data(s, key: str, i: int, explain_html: str, history, explanations, horizon: int, week: str):
    """Everything the item details need, sent to the browser as JSON."""
    item = {"i": i, "style": s["style"], "cat": s["category"], "rank": int(s["rank"]), "g": round(float(s["predicted_growth"]), 4),
            "alpha": round(float(s["growth_vs_market"]) - 1, 4), "action": key, "label": ACTIONS[key],
            "oor": bool(s["inputs_out_of_range"]), "text": explain_html}
    if history is not None and s["style"] in history.columns:
        series = history[s["style"]]
        past = series[series.index <= week].dropna().tail(8)
        if len(past) >= 4:
            level = float(series[series.index <= week].tail(4).mean())
            item["hist"] = [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in past.items()]
            item["fc"] = round(level * float(s["predicted_growth"]), 2)
            after = series[(series.index > week)].head(horizon).dropna()
            item["after"] = [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in after.items()]
    if explanations is not None:
        key_ = (week, s["style"], horizon)
        if key_ in explanations.index:
            row = explanations.loc[key_]
            item["shap"] = {g: round(float(np.exp(row[g]) - 1), 4) for g in GROUPS}
            item["shap"]["base"] = round(float(np.exp(row["base"]) - 1), 4)
    return item


def render(data: dict, all_rows: pd.DataFrame, shown: pd.DataFrame, history: pd.DataFrame,
           weeks: list[str], categories: list[str], category: str | None, version: str,
           search_history: pd.DataFrame | None = None, explanations: pd.DataFrame | None = None,
           lead_weeks: int = 6) -> str:
    """all_rows: every item for the chosen week and period; shown: filtered to the category;
    history: earlier forecasts for the same period (for 'four weeks ago')."""
    horizon, week = data["horizon"], data["week"]
    market, total = data["market_growth"], len(all_rows)
    month_ago = (pd.Timestamp(week) - pd.DateOffset(weeks=4)).strftime("%Y-%m-%d")
    earlier = history[history["week"] == month_ago].set_index("style")["predicted_growth"]

    items = shown.sort_values("rank").copy()
    items["action"] = items.apply(action, axis=1)
    counts = items["action"].value_counts()

    def link(h: int) -> str:
        query = {"week": week, "horizon": h} | ({"category": category} if category else {})
        current = ' aria-current="true"' if h == horizon else ""
        return f'<a href="{escape("?" + urlencode(query))}"{current}>Next {h} weeks</a>'

    week_options = "".join(f'<option value="{w}"{" selected" if w == week else ""}>{date_label(w)}</option>' for w in weeks)
    category_options = '<option value="">All categories</option>' + "".join(
        f'<option value="{escape(c)}"{" selected" if category and c.lower() == category.lower() else ""}>{escape(c)}</option>'
        for c in categories)
    chips = f'<button type="button" class="chip" data-filter="all" aria-pressed="true">All <b>{len(items)}</b></button>'
    for key in ACTIONS:
        if counts.get(key, 0):
            chips += (f'<button type="button" class="chip" data-filter="{key}" aria-pressed="false">'
                      f'<i class="dot {key}"></i>{ACTIONS[key]} <b>{counts[key]}</b></button>')

    cards, rows, payload = "", "", []
    for i, (_, s) in enumerate(items.iterrows()):
        key = s["action"]
        prior = earlier.get(s["style"])
        text = explanation(s, market, total, horizon, None if pd.isna(prior) else float(prior))
        payload.append(item_data(s, key, i, text, search_history, explanations, horizon, week))
        name, cat = escape(cap(s["style"])), escape(s["category"])
        growth, alpha = pct(s["predicted_growth"]), pct(s["growth_vs_market"], 1)
        attrs = f'data-i="{i}" data-action="{key}" data-style="{escape(s["style"].lower())}"'
        cards += (
            f'<li class="card{" more" if i >= 24 else ""}" {attrs}>'
            f'<button type="button" class="open" data-i="{i}" aria-haspopup="dialog">'
            f'<span class="pic">{picture(s["style"], s["category"])}</span><span class="rank">#{s["rank"]}</span>'
            f'<span class="name">{name}</span><span class="cat">{cat}</span></button>'
            f'<div class="row"><span class="interest">{growth}<small> interest</small></span>'
            f'<span class="status {key}">{ACTIONS[key]}</span></div>'
            f'<button type="button" class="add" data-i="{i}">+ Add to order plan</button></li>'
        )
        rows += (
            f'<tr {attrs} data-rank="{s["rank"]}" data-growth="{s["predicted_growth"]:.4f}" '
            f'data-alpha="{s["growth_vs_market"]:.4f}" data-cat="{cat}" data-order="{list(ACTIONS).index(key)}">'
            f'<td class="num">{s["rank"]}</td><td><button type="button" class="link open" data-i="{i}">{name}</button></td>'
            f'<td>{cat}</td><td class="num">{pct(s["predicted_growth"], 1)}</td><td class="num">{alpha}</td>'
            f'<td><span class="status {key}">{ACTIONS[key]}</span></td>'
            f'<td><button type="button" class="add small" data-i="{i}" aria-label="Add {name} to order plan">+ Plan</button></td></tr>'
        )

    m = round((market - 1) * 100)
    market_text = "stay about the same" if abs(m) < 1 else f"{'rise' if m > 0 else 'fall'} about {abs(m)}%"
    stock_n = int(counts.get("stock", 0))
    summary = (f"{'No' if stock_n == 0 else stock_n} {'item' if stock_n == 1 else 'items'} to stock up"
               f"{f' in {escape(category)}' if category else ''}, based on the forecast made on {date_label(week)}. "
               f"Fashion searches overall should {market_text}.")
    held_note = ""
    if data["alerts_held_back"]:
        held_note = ('<p class="note"><b>Unusual market week.</b> Searches across all of fashion moved outside anything '
                     "the model saw in training, so items it expects to rise are marked <b>Check first</b> instead of Stock up.</p>")
    page_data = {"week": week, "horizon": horizon, "lead": lead_weeks, "threshold": data["rising_threshold"], "items": payload}
    page_json = json.dumps(page_data, separators=(",", ":")).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>Before the Hype: what to stock next</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --ink: #191716; --muted: #75706b; --line: #e8e4df; --tile: #f4f1ed; --page: #ffffff;
    --stock: #1f6b47; --stock-bg: #e3f0e8; --check: #8a5a00; --check-bg: #fbefd2;
    --consider: #4a5a78; --consider-bg: #e8edf5; --steady: #5f5a55; --steady-bg: #efedea;
    --hold: #9a3b33; --hold-bg: #f6e4e1; --focus: #3b5bdb;
  }}
  * {{ box-sizing: border-box; }}
  html {{ background: var(--page); }}
  body {{ margin: 0; color: var(--ink); font: 400 15px/1.6 "Poppins", "Segoe UI", system-ui, sans-serif; min-width: 1024px; }}
  button {{ font: inherit; color: inherit; }}
  :focus-visible {{ outline: 3px solid var(--focus); outline-offset: 2px; }}
  .wrap {{ max-width: 1180px; margin: 0 auto; padding: 0 2rem; }}

  .top {{ border-bottom: 1px solid var(--line); position: sticky; top: 0; background: rgba(255,255,255,.96); z-index: 5; }}
  .top .wrap {{ display: flex; justify-content: space-between; align-items: center; gap: 1rem; padding-block: .9rem; }}
  .brand {{ font-weight: 600; font-size: 1.15rem; letter-spacing: .02em; }}
  .fresh {{ color: var(--muted); font-size: .85rem; margin-left: auto; }}
  .plan-btn {{ background: var(--ink); color: #fff; border: 0; border-radius: 999px; padding: .45rem 1rem; cursor: pointer; font-size: .875rem; }}
  .plan-btn b {{ background: #fff; color: var(--ink); border-radius: 999px; padding: 0 .45rem; margin-left: .35rem; font-size: .78rem; }}

  .intro {{ padding: 2.25rem 0 1.25rem; }}
  .intro h1 {{ font-weight: 600; font-size: 2.6rem; line-height: 1.15; margin: 0 0 .4rem; letter-spacing: -.02em; }}
  .intro p {{ margin: 0; color: var(--muted); font-size: 1.02rem; }}

  .kpis {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1.6fr; gap: 1rem; margin: .5rem 0 1.5rem; }}
  .kpi {{ border: 1px solid var(--line); border-radius: 14px; padding: 1rem 1.1rem; display: grid; align-content: start; gap: .15rem; }}
  .kpi-label {{ font-size: .8rem; color: var(--muted); }}
  .kpi-value {{ font-size: 1.9rem; font-weight: 600; line-height: 1.2; letter-spacing: -.01em; }}
  .kpi-value.small {{ font-size: 1.25rem; padding: .3rem 0 .15rem; }}
  .kpi-value.down {{ color: var(--hold); }} .kpi-value.up {{ color: var(--stock); }}
  .kpi-note {{ font-size: .8rem; color: var(--muted); }}
  .kpi-text {{ font-size: .9rem; line-height: 1.45; margin-top: .2rem; }}
  .kpi.window {{ border-left-width: 4px; }}
  .kpi.window.ok {{ border-left-color: var(--stock); }} .kpi.window.warn {{ border-left-color: #d99a17; }} .kpi.window.late {{ border-left-color: var(--hold); }}
  .kpi-warn {{ font-size: .78rem; color: var(--check); background: var(--check-bg); border-radius: 6px; padding: .2rem .5rem; margin-top: .4rem; justify-self: start; }}

  .controls {{ display: flex; gap: 1rem; align-items: center; padding: .9rem 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }}
  .seg {{ display: inline-flex; border: 1px solid var(--ink); border-radius: 999px; overflow: hidden; }}
  .seg a, .seg button {{ white-space: nowrap; padding: .4rem .95rem; color: var(--ink); text-decoration: none; font-size: .875rem; background: none; border: 0; cursor: pointer; }}
  .seg [aria-current="true"], .seg [aria-pressed="true"] {{ background: var(--ink); color: #fff; }}
  .controls label {{ white-space: nowrap; display: flex; align-items: center; gap: .45rem; font-size: .85rem; color: var(--muted); }}
  select, input {{ font: inherit; font-size: .875rem; color: var(--ink); background: #fff; border: 1px solid var(--line); border-radius: 999px; padding: .4rem .85rem; }}
  .push {{ margin-left: auto; }}
  input[type=search] {{ width: 13rem; }}

  .chips {{ display: flex; align-items: center; gap: .5rem; margin: 1.4rem 0 1rem; }}
  .chip-set {{ display: flex; flex-wrap: wrap; gap: .5rem; }}
  .chip {{ border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: .3rem .85rem; cursor: pointer; font-size: .85rem; }}
  .chip b {{ font-weight: 600; margin-left: .2rem; }}
  .chip[aria-pressed="true"] {{ background: var(--ink); color: #fff; border-color: var(--ink); }}
  .dot {{ display: inline-block; width: .55rem; height: .55rem; border-radius: 50%; margin-right: .4rem; }}
  .dot.stock {{ background: var(--stock); }} .dot.check {{ background: #d99a17; }} .dot.consider {{ background: var(--consider); }}
  .dot.steady {{ background: #9b958f; }} .dot.hold {{ background: var(--hold); }}
  .note {{ background: var(--check-bg); color: var(--check); border-radius: 10px; padding: .8rem 1rem; margin: 0 0 1rem; }}

  .grid {{ list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1.5rem 1.25rem; }}
  .grid:not(.open-all) .card.more:not(.match), .card.hide, tr.hide {{ display: none; }}
  .card {{ display: grid; gap: .1rem; }}
  .open {{ width: 100%; text-align: left; background: none; border: 0; padding: 0; cursor: pointer; display: grid; gap: .05rem; position: relative; }}
  .pic {{ display: grid; place-items: center; aspect-ratio: 1 / 1; background: var(--tile); border-radius: 12px; margin-bottom: .55rem; transition: background .15s; }}
  .pic svg {{ width: 66%; height: 66%; }}
  .open:hover .pic {{ background: #ece7e1; }}
  .rank {{ position: absolute; top: .55rem; left: .7rem; font-size: .78rem; font-weight: 500; color: var(--muted); }}
  .name {{ font-weight: 500; font-size: 1rem; line-height: 1.3; }}
  .cat {{ color: var(--muted); font-size: .8rem; }}
  .row {{ display: flex; justify-content: space-between; align-items: center; gap: .5rem; margin-top: .3rem; }}
  .interest {{ font-weight: 600; font-size: 1.05rem; }}
  .interest small {{ font-weight: 400; color: var(--muted); font-size: .78rem; }}
  .status {{ display: inline-block; font-size: .76rem; font-weight: 500; padding: .12rem .6rem; border-radius: 999px; white-space: nowrap; }}
  .status.stock {{ background: var(--stock-bg); color: var(--stock); }} .status.check {{ background: var(--check-bg); color: var(--check); }}
  .status.consider {{ background: var(--consider-bg); color: var(--consider); }} .status.steady {{ background: var(--steady-bg); color: var(--steady); }}
  .status.hold {{ background: var(--hold-bg); color: var(--hold); }}
  .add {{ margin-top: .5rem; border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: .3rem .8rem; font-size: .8rem; cursor: pointer; justify-self: start; }}
  .add:hover {{ border-color: var(--ink); }}
  .add.in {{ background: var(--ink); color: #fff; border-color: var(--ink); }}
  .add.small {{ margin: 0; padding: .15rem .6rem; }}
  .empty {{ display: none; color: var(--muted); padding: 1rem 0; }}
  .more-btn {{ display: block; margin: 2rem auto 0; background: var(--ink); color: #fff; border: 0; border-radius: 999px; padding: .55rem 1.4rem; cursor: pointer; }}

  .table-wrap {{ border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
  th {{ text-align: left; font-weight: 500; font-size: .8rem; color: var(--muted); background: #faf8f6; border-bottom: 1px solid var(--line); padding: 0; }}
  th button {{ background: none; border: 0; width: 100%; text-align: inherit; padding: .7rem .9rem; cursor: pointer; color: inherit; font-weight: 500; }}
  th button::after {{ content: " \\2195"; opacity: .35; }}
  th[aria-sort="ascending"] button::after {{ content: " \\2191"; opacity: 1; }} th[aria-sort="descending"] button::after {{ content: " \\2193"; opacity: 1; }}
  th.num, td.num {{ text-align: right; }}
  td {{ padding: .55rem .9rem; border-bottom: 1px solid #f0ece8; }}
  tr:last-child td {{ border-bottom: 0; }}
  tbody tr:hover {{ background: #fbfaf8; }}
  .link {{ background: none; border: 0; padding: 0; cursor: pointer; font-weight: 500; text-align: left; }}
  .link:hover {{ text-decoration: underline; }}
  .table-help {{ font-size: .8rem; color: var(--muted); margin: .6rem 0 0; }}

  dialog {{ border: 0; border-radius: 18px; padding: 0; width: 720px; max-height: 92vh; color: var(--ink); }}
  dialog::backdrop {{ background: rgba(25, 23, 22, .45); }}
  .d-body {{ padding: 1.6rem 1.8rem 1.8rem; }}
  .d-head {{ display: grid; grid-template-columns: 7rem 1fr auto; gap: 1.2rem; align-items: center; margin-bottom: .9rem; }}
  .d-head .pic {{ margin: 0; }}
  .d-head h3 {{ margin: .05rem 0 .35rem; font-size: 1.5rem; font-weight: 600; line-height: 1.2; }}
  .d-num {{ margin: .45rem 0 0; font-weight: 600; font-size: 1.3rem; }}
  .d-num small {{ font-weight: 400; font-size: .8rem; color: var(--muted); }}
  .flag {{ background: var(--check-bg); color: var(--check); border-radius: 10px; padding: .6rem .85rem; font-size: .85rem; margin: 0 0 1rem; }}
  .d-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.4rem; }}
  .panel h4, .d-text h4 {{ margin: 0 0 .45rem; font-size: .9rem; font-weight: 600; }}
  .d-text h4 {{ margin-top: .9rem; }}
  .d-text p {{ margin: 0; }} .d-text ul {{ margin: 0; padding-left: 1.1rem; color: #3d3935; }}
  .panel {{ border: 1px solid var(--line); border-radius: 12px; padding: .9rem 1rem; }}
  .panel.wide {{ grid-column: 1 / -1; }}
  .panel p.hint {{ font-size: .76rem; color: var(--muted); margin: .45rem 0 0; }}
  .chart svg {{ width: 100%; height: auto; display: block; overflow: visible; }}
  .legend {{ display: flex; white-space: nowrap; gap: 1rem; font-size: .76rem; color: var(--muted); margin-top: .3rem; }}
  .legend i {{ display: inline-block; width: 1.2rem; border-top: 2px solid var(--ink); vertical-align: middle; margin-right: .35rem; }}
  .legend i.fc {{ border-top-style: dashed; }} .legend i.after {{ border-top-color: #b8b2ac; }}
  .shap-row {{ display: grid; grid-template-columns: 9.5rem 1fr 3.4rem; gap: .6rem; align-items: center; font-size: .82rem; margin: .3rem 0; }}
  .shap-row .track {{ position: relative; height: 10px; background: linear-gradient(#d8d2cc, #d8d2cc) center / 1px 100% no-repeat; }}
  .shap-row .bar {{ position: absolute; top: 0; height: 100%; border-radius: 3px; }}
  .shap-row .bar.up {{ left: 50%; background: var(--stock); }} .shap-row .bar.down {{ right: 50%; background: var(--hold); }}
  .shap-row .v {{ text-align: right; font-weight: 500; }}
  .shap-row.total {{ border-top: 1px solid var(--line); padding-top: .35rem; font-weight: 600; }}
  .lead svg {{ width: 100%; height: auto; display: block; }}
  .lead-msg {{ font-size: .85rem; margin: .5rem 0 0; }}
  .lead-msg.ok {{ color: var(--stock); }} .lead-msg.warn {{ color: var(--check); }} .lead-msg.late {{ color: var(--hold); }}
  .close {{ position: absolute; top: .9rem; right: 1rem; background: #fff; border: 1px solid var(--line); border-radius: 999px; width: 2.2rem; height: 2.2rem; cursor: pointer; font-size: 1.2rem; line-height: 1; }}
  .d-foot {{ margin-top: 1rem; display: flex; justify-content: space-between; align-items: center; font-size: .76rem; color: var(--muted); }}
  .d-foot .add {{ margin: 0; font-size: .85rem; padding: .45rem 1rem; }}
  #tip {{ position: fixed; pointer-events: none; background: var(--ink); color: #fff; font-size: .76rem; padding: .25rem .55rem; border-radius: 6px; opacity: 0; z-index: 20; white-space: nowrap; }}

  .drawer {{ position: fixed; top: 0; right: 0; bottom: 0; width: 420px; background: #fff; border-left: 1px solid var(--line);
            box-shadow: -12px 0 40px rgba(0,0,0,.08); transform: translateX(105%); transition: transform .25s ease; z-index: 10; display: grid; grid-template-rows: auto 1fr auto; }}
  .drawer.open {{ transform: none; }}
  .drawer header {{ padding: 1.2rem 1.4rem; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center; }}
  .drawer h2 {{ margin: 0; font-size: 1.15rem; font-weight: 600; }}
  .drawer ul {{ list-style: none; margin: 0; padding: .5rem 1.4rem; overflow-y: auto; }}
  .drawer li {{ display: grid; grid-template-columns: 1fr 5.5rem 1.8rem; gap: .6rem; align-items: center; padding: .7rem 0; border-bottom: 1px solid #f0ece8; }}
  .drawer li small {{ display: block; color: var(--muted); font-size: .76rem; }}
  .drawer input {{ width: 100%; border-radius: 8px; text-align: right; }}
  .drawer .rm {{ background: none; border: 0; cursor: pointer; font-size: 1.1rem; color: var(--muted); }}
  .drawer footer {{ padding: 1rem 1.4rem 1.3rem; border-top: 1px solid var(--line); display: grid; gap: .7rem; }}
  .drawer .total {{ display: flex; justify-content: space-between; font-weight: 500; }}
  .drawer .actions {{ display: flex; gap: .6rem; }}
  .drawer .actions button {{ flex: 1; border-radius: 999px; padding: .55rem; cursor: pointer; border: 1px solid var(--ink); background: #fff; }}
  .drawer .actions .primary {{ background: var(--ink); color: #fff; }}
  .drawer .empty-plan {{ color: var(--muted); padding: 1.5rem 0; }}

  footer.page {{ margin: 3.5rem 0 0; padding: 1.25rem 0 2.5rem; border-top: 1px solid var(--line); font-size: .82rem; color: var(--muted); }}
  footer.page a {{ color: var(--ink); }}
</style></head>
<body>
<header class="top"><div class="wrap">
  <span class="brand">Before the Hype</span>
  <span class="fresh">Google searches up to {date_label(weeks[0])}</span>
  <button type="button" class="plan-btn" id="plan-open">Order plan <b id="plan-count">0</b></button>
</div></header>

<main class="wrap">
  <section class="intro">
    <h1>What to stock for the next {horizon} weeks</h1>
    <p>{summary}</p>
  </section>

  {kpis(all_rows, data, lead_weeks, weeks[0])}

  <form class="controls" method="get">
    <div class="seg" role="group" aria-label="Forecast period">{link(4)}{link(8)}</div>
    <input type="hidden" name="horizon" value="{horizon}">
    <label>Forecast date <select name="week" onchange="this.form.submit()">{week_options}</select></label>
    <label>Category <select name="category" onchange="this.form.submit()">{category_options}</select></label>
    <noscript><button type="submit">Show</button></noscript>
    <input class="push" type="search" id="find" placeholder="Search items" aria-label="Search items" autocomplete="off">
  </form>

  <div class="chips"><div class="chip-set" role="group" aria-label="Filter by action">{chips}</div>
    <div class="seg push" role="group" aria-label="View">
      <button type="button" data-view="cards" aria-pressed="true">Cards</button><button type="button" data-view="table" aria-pressed="false">Table</button>
    </div></div>
  {held_note}

  <div id="view-cards">
    <ul class="grid" id="grid">{cards}</ul>
    {f'<button type="button" class="more-btn" id="more">Show all {len(items)} items</button>' if len(items) > 24 else ""}
  </div>
  <div id="view-table" hidden>
    <div class="table-wrap"><table id="table">
      <thead><tr>
        <th class="num" data-key="rank" aria-sort="ascending"><button type="button">Rank</button></th>
        <th data-key="style"><button type="button">Style</button></th>
        <th data-key="cat"><button type="button">Category</button></th>
        <th class="num" data-key="growth"><button type="button" title="Expected change in search interest over the period, compared with the last 4 weeks">Predicted growth</button></th>
        <th class="num" data-key="alpha"><button type="button" title="How much faster (+) or slower (−) than the average item">Alpha vs. market</button></th>
        <th data-key="order"><button type="button">Action</button></th><th></th>
      </tr></thead>
      <tbody id="rows">{rows}</tbody>
    </table></div>
    <p class="table-help"><b>Predicted growth</b>: expected change in searches over the next {horizon} weeks, compared with the last 4 weeks.
      <b>Alpha vs. market</b>: how much faster (+) or slower (−) the item should grow than the average item. Click a column to sort.</p>
  </div>
  <p class="empty" id="empty">No items match. Try another word or action.</p>

  <footer class="page">Forecasts come from Google searches, which show what people are curious about, not what they buy.
    Use them alongside your own sales. Developers can use the same data through the <a href="/docs">API</a>. Version {escape(version)}.</footer>
</main>

<dialog id="detail" aria-label="Item details"><div class="d-body">
  <button type="button" class="close" aria-label="Close">&times;</button><div id="d-content"></div>
</div></dialog>

<aside class="drawer" id="drawer" aria-label="Order plan">
  <header><h2>Order plan</h2><button type="button" class="close" id="plan-close" aria-label="Close order plan" style="position:static">&times;</button></header>
  <ul id="plan-list"></ul>
  <footer>
    <div class="total"><span>Total units</span><span id="plan-total">0</span></div>
    <div class="actions"><button type="button" id="plan-clear">Clear</button><button type="button" class="primary" id="plan-export">Export CSV</button></div>
  </footer>
</aside>
<div id="tip" role="tooltip"></div>

<script id="page-data" type="application/json">{page_json}</script>
<script>
const DATA = JSON.parse(document.getElementById("page-data").textContent);
const ITEMS = DATA.items;
const fmt = r => {{ const c = Math.round(r * 100); return c === 0 ? "0%" : (c > 0 ? "+" : "\\u2212") + Math.abs(c) + "%"; }};
const esc = s => String(s).replace(/[&<>"]/g, c => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}})[c]);
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
const dayLabel = iso => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", {{ day: "numeric", month: "short" }});
const tip = document.getElementById("tip");
function showTip(e, text) {{ tip.textContent = text; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY - 32 + "px"; tip.style.opacity = 1; }}
function hideTip() {{ tip.style.opacity = 0; }}

/* ---------- filters, search, views ---------- */
const grid = document.getElementById("grid"), cards = [...grid.children];
const tbody = document.getElementById("rows"), trs = [...tbody.children];
const find = document.getElementById("find"), more = document.getElementById("more"), empty = document.getElementById("empty");
let status = "all", view = "cards";
function apply() {{
  const q = find.value.trim().toLowerCase(), filtering = q !== "" || status !== "all";
  let shown = 0;
  for (const el of [...cards, ...trs]) {{
    const hit = el.dataset.style.includes(q) && (status === "all" || el.dataset.action === status);
    el.classList.toggle("hide", !hit); el.classList.toggle("match", filtering && hit);
    if (el.tagName === "LI") shown += hit;
  }}
  empty.style.display = shown ? "none" : "block";
  if (more) more.style.display = filtering ? "none" : "block";
}}
find.addEventListener("input", apply);
document.querySelectorAll(".chip").forEach(b => b.addEventListener("click", () => {{
  document.querySelectorAll(".chip").forEach(x => x.setAttribute("aria-pressed", x === b));
  status = b.dataset.filter; apply();
}}));
if (more) more.addEventListener("click", () => {{
  const open = grid.classList.toggle("open-all");
  more.textContent = open ? "Show fewer" : "Show all " + cards.length + " items";
}});
document.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => {{
  view = b.dataset.view;
  document.querySelectorAll("[data-view]").forEach(x => x.setAttribute("aria-pressed", x === b));
  document.getElementById("view-cards").hidden = view !== "cards";
  document.getElementById("view-table").hidden = view !== "table";
}}));

/* ---------- sortable table ---------- */
document.querySelectorAll("#table th[data-key]").forEach(th => th.querySelector("button").addEventListener("click", () => {{
  const key = th.dataset.key, numeric = ["rank", "growth", "alpha", "order"].includes(key);
  const dir = th.getAttribute("aria-sort") === "ascending" ? "descending" : (th.getAttribute("aria-sort") === "descending" ? "ascending" : (numeric && key !== "rank" && key !== "order" ? "descending" : "ascending"));
  document.querySelectorAll("#table th").forEach(x => x.removeAttribute("aria-sort"));
  th.setAttribute("aria-sort", dir);
  const val = tr => numeric ? parseFloat(tr.dataset[key]) : tr.dataset[key];
  trs.sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * (dir === "ascending" ? 1 : -1));
  trs.forEach(tr => tbody.appendChild(tr));
}}));

/* ---------- item details ---------- */
function chart(it) {{
  if (!it.hist) return "";
  const W = 320, H = 190, P = {{ l: 30, r: 8, t: 10, b: 22 }};
  const past = it.hist, n = past.length, h = DATA.horizon, total = n + h;
  const after = it.after || [];
  const maxV = Math.max(it.fc, ...past.map(p => p[1]), ...after.map(p => p[1])) * 1.15 || 1;
  const x = i => P.l + i * (W - P.l - P.r) / (total - 1), y = v => H - P.b - v / maxV * (H - P.t - P.b);
  let s = `<svg viewBox="0 0 ${{W}} ${{H}}" role="img" aria-label="Weekly searches and forecast">`;
  for (const g of [0, .5, 1]) s += `<line x1="${{P.l}}" x2="${{W - P.r}}" y1="${{y(maxV / 1.15 * g)}}" y2="${{y(maxV / 1.15 * g)}}" stroke="#eee9e4"/><text x="${{P.l - 5}}" y="${{y(maxV / 1.15 * g) + 3}}" font-size="8" text-anchor="end" fill="#8a847e">${{Math.round(maxV / 1.15 * g)}}</text>`;
  s += `<rect x="${{x(n - 1)}}" y="${{P.t}}" width="${{x(total - 1) - x(n - 1)}}" height="${{H - P.t - P.b}}" fill="#f6f3ef"/>`;
  s += `<text x="${{(x(n - 1) + x(total - 1)) / 2}}" y="${{H - 6}}" font-size="8" text-anchor="middle" fill="#8a847e">next ${{h}} weeks</text>`;
  s += `<text x="${{(x(0) + x(n - 1)) / 2}}" y="${{H - 6}}" font-size="8" text-anchor="middle" fill="#8a847e">last ${{n}} weeks</text>`;
  if (after.length) s += `<polyline fill="none" stroke="#b8b2ac" stroke-width="1.6" points="${{[[n - 1, past[n - 1][1]], ...after.map((p, i) => [n + i, p[1]])].map(([i, v]) => x(i) + "," + y(v)).join(" ")}}"/>`;
  s += `<polyline fill="none" stroke="#191716" stroke-width="2" points="${{past.map((p, i) => x(i) + "," + y(p[1])).join(" ")}}"/>`;
  s += `<polyline fill="none" stroke="#191716" stroke-width="2" stroke-dasharray="5 4" points="${{x(n - 1)}},${{y(past[n - 1][1])}} ${{x(n)}},${{y(it.fc)}} ${{x(total - 1)}},${{y(it.fc)}}"/>`;
  past.forEach((p, i) => s += `<circle class="pt" cx="${{x(i)}}" cy="${{y(p[1])}}" r="3.2" fill="#191716" data-tip="Week of ${{dayLabel(p[0])}}: ${{p[1].toFixed(1)}}"/>`);
  after.forEach((p, i) => s += `<circle class="pt" cx="${{x(n + i)}}" cy="${{y(p[1])}}" r="2.6" fill="#b8b2ac" data-tip="Actual, week of ${{dayLabel(p[0])}}: ${{p[1].toFixed(1)}}"/>`);
  s += `<circle class="pt" cx="${{x(total - 1)}}" cy="${{y(it.fc)}}" r="4" fill="#fff" stroke="#191716" stroke-width="2" data-tip="Forecast average, next ${{h}} weeks: ${{it.fc.toFixed(1)}}"/>`;
  return s + "</svg>";
}}
function shap(it) {{
  if (!it.shap) return "";
  const labels = {json.dumps(GROUP_LABELS)};
  const rows = Object.keys(labels).map(k => [labels[k], it.shap[k]]);
  const scale = Math.max(...rows.map(r => Math.abs(r[1])), .05);
  const bar = v => `<span class="track"><span class="bar ${{v >= 0 ? "up" : "down"}}" style="width:${{Math.min(Math.abs(v) / scale, 1) * 50}}%"></span></span>`;
  return `<div class="shap-row"><span>Typical item</span>${{bar(0)}}<span class="v">${{fmt(it.shap.base)}}</span></div>` +
    rows.map(([l, v]) => `<div class="shap-row"><span>${{l}}</span>${{bar(v)}}<span class="v">${{fmt(v)}}</span></div>`).join("") +
    `<div class="shap-row total"><span>Forecast</span><span></span><span class="v">${{fmt(it.g - 1)}}</span></div>`;
}}
function leadBar(it) {{
  const h = DATA.horizon, lead = DATA.lead, span = Math.max(h, lead) + 1, W = 320, H = 54;
  const x = w => 8 + w * (W - 16) / span;
  const start = new Date(DATA.week + "T00:00:00"), at = w => {{ const d = new Date(start); d.setDate(d.getDate() + 7 * w); return d.toLocaleDateString("en-GB", {{ day: "numeric", month: "short" }}); }};
  let s = `<svg viewBox="0 0 ${{W}} ${{H}}" aria-hidden="true"><line x1="${{x(0)}}" x2="${{x(span)}}" y1="24" y2="24" stroke="#d8d2cc" stroke-width="2"/>`;
  s += `<rect x="${{x(0)}}" y="17" width="${{x(h) - x(0)}}" height="14" rx="4" fill="${{lead <= h ? "#e3f0e8" : "#f6e4e1"}}"/>`;
  s += `<text x="${{(x(0) + x(h)) / 2}}" y="27.5" font-size="8.5" text-anchor="middle" fill="#3d3935">forecast window (${{h}} weeks)</text>`;
  s += `<circle cx="${{x(0)}}" cy="24" r="4" fill="#191716"/><text x="${{x(0)}}" y="46" font-size="8.5" fill="#75706b">Order ${{at(0)}}</text>`;
  s += `<line x1="${{x(lead)}}" x2="${{x(lead)}}" y1="10" y2="38" stroke="${{lead < h ? "#1f6b47" : lead === h ? "#d99a17" : "#9a3b33"}}" stroke-width="2.5"/>`;
  s += `<text x="${{x(lead)}}" y="8" font-size="8.5" text-anchor="middle" fill="#191716">Arrives ${{at(lead)}}</text></svg>`;
  let msg, cls;
  if (it.action === "hold" || it.action === "steady") {{ msg = "No new order suggested for this item."; cls = "warn"; }}
  else if (it.action === "check") {{ msg = lead <= h ? `The lead time fits this window (stock arrives in week ${{lead}}), but check your own sales first: this is an unusual market week.` : `A ${{lead}}-week lead time arrives after this ${{h}}-week window, and this is an unusual market week.`; cls = "warn"; }}
  else if (lead < h) {{ msg = `Safe to order now: stock arrives in week ${{lead}}, leaving ${{h - lead}} of the ${{h}} forecast weeks to sell.`; cls = "ok"; }}
  else if (lead === h) {{ msg = "Tight: stock would arrive just as the forecast window ends."; cls = "warn"; }}
  else {{ msg = `Window passed for this period: a ${{lead}}-week lead time arrives after the ${{h}}-week window. Check the 8-week view.`; cls = "late"; }}
  return s + `<p class="lead-msg ${{cls}}">${{msg}}</p>`;
}}
const dialog = document.getElementById("detail"), content = document.getElementById("d-content");
function openItem(i) {{
  const it = ITEMS[i], card = grid.querySelector(`.card[data-i="${{i}}"]`);
  const flag = it.oor ? `<p class="flag"><b>Unusual market swing.</b> The market's recent growth is outside anything the model saw in training, so this forecast is less reliable and its alert is held back.</p>` : "";
  content.innerHTML = `
    <div class="d-head"><span class="pic">${{card.querySelector(".pic").innerHTML}}</span>
      <div><span class="cat">${{esc(it.cat)}}</span><h3>${{esc(cap(it.style))}}</h3><span class="status ${{it.action}}">${{it.label}}</span>
        <p class="d-num">${{fmt(it.g - 1)}}<small> predicted growth, next ${{DATA.horizon}} weeks (rank ${{it.rank}})</small></p></div></div>
    ${{flag}}
    <div class="d-grid">
      <div class="d-text">${{it.text}}</div>
      <div class="panel chart"><h4>Weekly searches and forecast</h4>${{chart(it) || "<p class='hint'>Search history is not available.</p>"}}
        <div class="legend"><span><i></i>Searches</span><span><i class="fc"></i>Forecast average</span>${{(it.after || []).length ? '<span><i class="after"></i>What happened</span>' : ""}}</div></div>
      <div class="panel"><h4>What drove the forecast</h4>${{shap(it) || "<p class='hint'>Explanation not available.</p>"}}
        <p class="hint">SHAP values: how much each group of model inputs pushed the forecast up or down from a typical item.</p></div>
      <div class="panel"><h4>Ordering window (${{DATA.lead}}-week lead time)</h4>${{leadBar(it)}}</div>
    </div>
    <div class="d-foot"><span>Based on Google searches up to the forecast date. A forecast, not a guarantee.</span>
      <button type="button" class="add" data-i="${{i}}">+ Add to order plan</button></div>`;
  content.querySelectorAll(".pt").forEach(c => {{ c.addEventListener("mousemove", e => showTip(e, c.dataset.tip)); c.addEventListener("mouseleave", hideTip); }});
  bindAdd(content); refreshAdd();
  dialog.showModal();
}}
document.querySelectorAll(".open").forEach(b => b.addEventListener("click", () => openItem(+b.dataset.i)));
dialog.querySelector(".close").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", e => {{ if (e.target === dialog) dialog.close(); }});

/* ---------- order plan ---------- */
const KEY = "before-the-hype-order-plan";
let plan = {{}};
try {{ plan = JSON.parse(localStorage.getItem(KEY)) || {{}}; }} catch (e) {{ plan = {{}}; }}
function save() {{ try {{ localStorage.setItem(KEY, JSON.stringify(plan)); }} catch (e) {{}} renderPlan(); refreshAdd(); }}
function toggle(i) {{
  const it = ITEMS[i];
  if (plan[it.style]) delete plan[it.style];
  else plan[it.style] = {{ category: it.cat, action: it.label, growth: fmt(it.g - 1), forecast_date: DATA.week, horizon_weeks: DATA.horizon, units: 100 }};
  save();
}}
function bindAdd(root) {{ root.querySelectorAll(".add").forEach(b => b.addEventListener("click", e => {{ e.stopPropagation(); toggle(+b.dataset.i); }})); }}
function refreshAdd() {{
  document.querySelectorAll(".add").forEach(b => {{
    const inPlan = !!plan[ITEMS[+b.dataset.i].style]; b.classList.toggle("in", inPlan);
    b.textContent = inPlan ? "\\u2713 In order plan" : (b.classList.contains("small") ? "+ Plan" : "+ Add to order plan");
  }});
}}
function renderPlan() {{
  const list = document.getElementById("plan-list"), names = Object.keys(plan);
  document.getElementById("plan-count").textContent = names.length;
  list.innerHTML = names.length ? names.map(n => `<li><span>${{esc(cap(n))}}<small>${{esc(plan[n].category)}}, ${{esc(plan[n].action)}}, ${{esc(plan[n].growth)}}</small></span>
    <input type="number" min="0" step="10" value="${{plan[n].units}}" data-n="${{esc(n)}}" aria-label="Units of ${{esc(n)}}">
    <button type="button" class="rm" data-n="${{esc(n)}}" aria-label="Remove ${{esc(n)}}">&times;</button></li>`).join("")
    : `<li class="empty-plan">No items yet. Use “Add to order plan” on any item.</li>`;
  document.getElementById("plan-total").textContent = names.reduce((t, n) => t + (+plan[n].units || 0), 0).toLocaleString("en-GB");
  list.querySelectorAll("input").forEach(inp => inp.addEventListener("change", () => {{ plan[inp.dataset.n].units = Math.max(0, +inp.value || 0); save(); }}));
  list.querySelectorAll(".rm").forEach(b => b.addEventListener("click", () => {{ delete plan[b.dataset.n]; save(); }}));
}}
document.getElementById("plan-open").addEventListener("click", () => document.getElementById("drawer").classList.add("open"));
document.getElementById("plan-close").addEventListener("click", () => document.getElementById("drawer").classList.remove("open"));
document.getElementById("plan-clear").addEventListener("click", () => {{ plan = {{}}; save(); }});
document.getElementById("plan-export").addEventListener("click", () => {{
  const cols = ["style", "category", "action", "growth", "forecast_date", "horizon_weeks", "units"];
  const cell = v => /[",\\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v);
  const csv = [cols.join(","), ...Object.keys(plan).map(n => [n, ...cols.slice(1).map(c => plan[n][c])].map(cell).join(","))].join("\\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {{ type: "text/csv" }})); a.download = "order-plan-" + DATA.week + ".csv"; a.click();
  URL.revokeObjectURL(a.href);
}});
bindAdd(document); renderPlan(); refreshAdd();
</script>
</body></html>"""
