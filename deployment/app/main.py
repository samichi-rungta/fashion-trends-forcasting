"""Small web API that serves weekly style rankings and ordering windows to buyers.

Run locally (from the deployment/ folder):
    uvicorn app.main:app --reload
Then open http://localhost:8000 (buyer page) or http://localhost:8000/docs (API docs).
"""
import logging
import os
import time
from html import escape
from urllib.parse import quote_plus

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import page
from app.data import (
    APP_VERSION,
    load_explanations,
    load_history,
    load_rankings,
    order_lead_weeks,
    rankings_path,
    rising_threshold,
)

# Logs go to standard output, where Docker and Azure Container Apps collect them.
# LOG_LEVEL can be set as an environment variable (DEBUG, INFO, WARNING, ERROR).
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("fashion_trends")

# Version of the code inside the container (the commit ID, set when the image is built).
APP_VERSION = os.environ.get("APP_VERSION", "dev")

app = FastAPI(
    title="Before the Hype: Fashion Trend Rankings & Ordering Windows",
    description="Serves 4- and 8-week growth forecasts for fashion styles, ranked for buyers with supplier ordering windows.",
    version="0.3.0",
)

# The file is read once when the app starts. A new file means a restart (or a new container).
RANKINGS = load_rankings()
WEEKS = sorted(RANKINGS["week"].unique(), reverse=True)  # newest first
CATEGORIES = sorted(RANKINGS["category"].dropna().unique())
HISTORY = load_history()            # optional: weekly searches, for the chart in the item details
EXPLANATIONS = load_explanations()  # optional: SHAP contributions, for the explanation in the item details
logger.info(
    "startup version=%s source=%s rows=%d weeks=%d latest_week=%s rising_threshold=%s history=%s explanations=%s",
    APP_VERSION, rankings_path().name, len(RANKINGS), len(WEEKS), WEEKS[0], rising_threshold(),
    HISTORY is not None, EXPLANATIONS is not None,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with its status and duration, and turn unexpected errors into a clean 500."""
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("error method=%s path=%s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    duration_ms = (time.perf_counter() - start) * 1000
    # Health checks arrive every few seconds from Azure, so they are logged only at DEBUG level.
    if request.url.path == "/health":
        level = logging.DEBUG
    elif response.status_code >= 400:
        level = logging.WARNING
    else:
        level = logging.INFO
    logger.log(
        level, "request method=%s path=%s status=%d duration_ms=%.1f",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


def make_sparkline_svg(values: list[float], is_rising: bool = True) -> str:
    """Generate a compact inline SVG sparkline for table rows."""
    if not values or len(values) < 2:
        return ""
    w, h = 76, 20
    pad = 3
    min_v, max_v = min(values), max(values)
    rng = max(max_v - min_v, 1.0)
    pts = []
    n = len(values)
    for i, v in enumerate(values):
        x = pad + (i / (n - 1)) * (w - 2 * pad)
        y = (h - pad) - ((v - min_v) / rng) * (h - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    pts_str = " ".join(pts)
    color = "#1e6b35" if is_rising else "#8a8a85"
    lx, ly = pts[-1].split(",")
    return (
        f'<svg width="{w}" height="{h}" class="sparkline" viewBox="0 0 {w} {h}">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" points="{pts_str}"/>'
        f'<circle cx="{lx}" cy="{ly}" r="2.5" fill="{color}"/>'
        f'</svg>'
    )


def compute_ordering_window(
    origin_week: str,
    horizon: int,
    lead_time_weeks: int,
    predicted_growth: float,
    threshold: float,
) -> dict:
    """Calculates supplier ordering deadlines and buyer urgency status."""
    origin_dt = pd.to_datetime(origin_week)
    target_dt = origin_dt + pd.Timedelta(weeks=horizon)
    target_week = target_dt.strftime("%Y-%m-%d")

    deadline_dt = target_dt - pd.Timedelta(weeks=lead_time_weeks)
    order_deadline = deadline_dt.strftime("%Y-%m-%d")
    lead_cushion_weeks = horizon - lead_time_weeks

    if predicted_growth > threshold:
        if lead_cushion_weeks < 0:
            urgency = "Window Closed"
            action = f"Need {abs(lead_cushion_weeks)}w faster lead time"
            badge_class = "badge-danger"
        elif lead_cushion_weeks == 0:
            urgency = "Order Now"
            action = "Order this week for peak"
            badge_class = "badge-critical"
        elif lead_cushion_weeks <= 2:
            urgency = "Order Soon"
            action = f"Window closes in {lead_cushion_weeks}w"
            badge_class = "badge-warning"
        else:
            urgency = "Window Open"
            action = f"Order by {order_deadline}"
            badge_class = "badge-success"
    else:
        if predicted_growth < 0.95:
            urgency = "Cooling Down"
            action = "Hold reorders"
            badge_class = "badge-neutral"
        else:
            urgency = "Steady"
            action = "Replenish as normal"
            badge_class = "badge-neutral"

    return {
        "target_week": target_week,
        "order_deadline": order_deadline,
        "lead_cushion_weeks": lead_cushion_weeks,
        "ordering_urgency": urgency,
        "ordering_action": action,
        "badge_class": badge_class,
    }


def get_rankings(
    week: str | None,
    horizon: int,
    top_k: int,
    category: str | None,
    lead_time_weeks: int = 4,
) -> dict:
    """Shared logic for the JSON endpoint and the HTML page."""
    if horizon not in (4, 8):
        raise HTTPException(422, "horizon must be 4 or 8")
    week = week or WEEKS[0]
    if week not in WEEKS:
        raise HTTPException(404, f"No rankings for week {week}. Available: {WEEKS}")

    all_rows = RANKINGS[(RANKINGS["week"] == week) & (RANKINGS["horizon"] == horizon)]
    rows = all_rows
    if category:
        rows = rows[rows["category"].str.lower() == category.lower()]
        if rows.empty:
            raise HTTPException(404, f"Unknown category: {category}")

    rows = rows.sort_values("rank").head(top_k)
    thresh = rising_threshold()

    styles_list = []
    # Find recent weeks preceding current week for sparkline trajectory
    week_idx = WEEKS.index(week)
    recent_weeks = list(reversed(WEEKS[week_idx : min(week_idx + 6, len(WEEKS))]))

    for _, s in rows.iterrows():
        style_name = s["style"]
        style_history = RANKINGS[(RANKINGS["style"] == style_name) & (RANKINGS["horizon"] == horizon)]
        history_map = dict(zip(style_history["week"], style_history["last4_avg"])) if "last4_avg" in style_history.columns else {}
        fallback_val = float(s["last4_avg"]) if "last4_avg" in s and pd.notna(s["last4_avg"]) else 50.0
        spark_vals = [history_map.get(w, fallback_val) for w in recent_weeks]
        if "predicted" in s and pd.notna(s["predicted"]):
            spark_vals.append(float(s["predicted"]))

        growth = float(s["predicted_growth"])
        is_rising = bool(s["rising"])
        order_info = compute_ordering_window(week, horizon, lead_time_weeks, growth, thresh)

        item = {
            "rank": int(s["rank"]),
            "style": style_name,
            "category": s["category"],
            "predicted_growth": growth,
            "growth_vs_market": float(s["growth_vs_market"]) if "growth_vs_market" in s and pd.notna(s["growth_vs_market"]) else round(growth, 4),
            "rising": is_rising,
            "held_back": bool(s["held_back"]) if "held_back" in s else False,
            "target_week": order_info["target_week"],
            "order_deadline": order_info["order_deadline"],
            "lead_cushion_weeks": order_info["lead_cushion_weeks"],
            "ordering_urgency": order_info["ordering_urgency"],
            "ordering_action": order_info["ordering_action"],
            "badge_class": order_info["badge_class"],
            "sparkline_svg": make_sparkline_svg(spark_vals, is_rising),
        }
        styles_list.append(item)

    origin_dt = pd.to_datetime(week)
    target_dt = origin_dt + pd.Timedelta(weeks=horizon)
    deadline_dt = target_dt - pd.Timedelta(weeks=lead_time_weeks)

    return {
        "week": week,
        "horizon": horizon,
        "lead_time_weeks": lead_time_weeks,
        "target_week": target_dt.strftime("%Y-%m-%d"),
        "order_deadline": deadline_dt.strftime("%Y-%m-%d"),
        "rising_threshold": thresh,
        # Week-level facts, always about all styles (not only the chosen category).
        "market_growth": round(float(all_rows["market_growth"].iloc[0]), 4) if "market_growth" in all_rows.columns else 1.0,
        "alerts_held_back": bool(all_rows["inputs_out_of_range"].any()) if "inputs_out_of_range" in all_rows.columns else False,
        "rising_count": int(all_rows["rising"].sum()) if "rising" in all_rows.columns else 0,
        "style_count": len(all_rows),
        "count": len(styles_list),
        "styles": styles_list,
    }


@app.get("/health")
def health() -> dict:
    """Used by the CI pipeline and by Azure/AWS to check the app is alive."""
    return {
        "status": "ok",
        "version": APP_VERSION,
        "rows": len(RANKINGS),
        "weeks": len(WEEKS),
        "source": rankings_path().name,
    }


@app.get("/weeks")
def weeks() -> dict:
    """Forecast weeks available in the file, newest first."""
    return {"weeks": WEEKS}


@app.get("/rankings")
def rankings(
    week: str | None = Query(None, description="Forecast week (YYYY-MM-DD). Default: latest."),
    horizon: int = Query(4, description="Weeks ahead: 4 or 8."),
    top_k: int = Query(10, ge=1, le=200, description="How many styles to return."),
    category: str | None = Query(None, description="Optional category filter, e.g. Shoes."),
    lead_time_weeks: int = Query(4, ge=1, le=12, description="Supplier lead time in weeks."),
) -> dict:
    """Top-ranked styles for one week and horizon. Rank 1 = highest expected growth."""
    return get_rankings(week, horizon, top_k, category, lead_time_weeks)


def generate_style_view_html(style: str, horizon: int, lead_time_weeks: int, week: str | None) -> str:
    """Generate interactive SVG forecast curve and ordering timeline view for a single style."""
    rows = RANKINGS[RANKINGS["style"].str.lower() == style.lower()]
    if rows.empty:
        raise HTTPException(404, f"Unknown style: {style}")

    target_week = week or WEEKS[0]
    h_rows = rows[rows["horizon"] == horizon].sort_values("week")
    current_row = h_rows[h_rows["week"] == target_week]
    if current_row.empty:
        current_row = h_rows.tail(1)
        target_week = current_row["week"].iloc[0]

    growth = float(current_row["predicted_growth"].iloc[0])
    category = current_row["category"].iloc[0]
    thresh = rising_threshold()
    order_info = compute_ordering_window(target_week, horizon, lead_time_weeks, growth, thresh)

    # Historical values
    past_subset = h_rows[h_rows["week"] <= target_week].tail(10)
    has_levels = "last4_avg" in past_subset.columns and past_subset["last4_avg"].notna().any()
    if has_levels:
        y_hist = [float(v) for v in past_subset["last4_avg"]]
        pred_val = float(current_row["predicted"].iloc[0]) if "predicted" in current_row.columns and pd.notna(current_row["predicted"].iloc[0]) else y_hist[-1] * growth
    else:
        y_hist = [float(g) * 50.0 for g in past_subset["predicted_growth"]]
        pred_val = growth * 50.0

    all_vals = y_hist + [pred_val]
    min_v, max_v = min(all_vals), max(all_vals)
    rng = max(max_v - min_v, 1.0)

    w, h = 680, 240
    pad_l, pad_r, pad_t, pad_b = 50, 40, 30, 40
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    def to_coords(idx, total_pts, val):
        x = pad_l + (idx / (total_pts - 1)) * plot_w
        y = (h - pad_b) - ((val - min_v) / rng) * plot_h
        return x, y

    total_pts = len(y_hist) + 1
    pts = [to_coords(i, total_pts, v) for i, v in enumerate(y_hist)]
    fc_pt = to_coords(total_pts - 1, total_pts, pred_val)

    pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    fc_line_str = f"{pts[-1][0]:.1f},{pts[-1][1]:.1f} {fc_pt[0]:.1f},{fc_pt[1]:.1f}"

    # Shaded supplier ordering window
    lead_ratio = (horizon - lead_time_weeks) / horizon
    window_x1 = pts[-1][0]
    window_x2 = window_x1 + max(0.0, lead_ratio) * (fc_pt[0] - window_x1)
    window_rect = (
        f'<rect x="{window_x1:.1f}" y="{pad_t}" width="{window_x2 - window_x1:.1f}" height="{plot_h}" '
        f'fill="#10b981" fill-opacity="0.12" stroke="#10b981" stroke-dasharray="3,3" stroke-width="1"/>'
        f'<text x="{(window_x1 + window_x2)/2:.1f}" y="{pad_t + 16}" fill="#047857" font-size="11" font-weight="600" text-anchor="middle">Ordering Window</text>'
    ) if lead_ratio > 0 else (
        f'<rect x="{window_x1:.1f}" y="{pad_t}" width="{fc_pt[0] - window_x1:.1f}" height="{plot_h}" fill="#ef4444" fill-opacity="0.1" stroke="#ef4444" stroke-dasharray="3,3" stroke-width="1"/>'
        f'<text x="{(window_x1 + fc_pt[0])/2:.1f}" y="{pad_t + 16}" fill="#b91c1c" font-size="11" font-weight="600" text-anchor="middle">Window Closed</text>'
    )

    svg_chart = f"""
    <svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="width:100%; max-width:{w}px; background:#fff; border:1px solid #e5e7eb; border-radius:8px;">
      {window_rect}
      <line x1="{pad_l}" y1="{h-pad_b}" x2="{w-pad_r}" y2="{h-pad_b}" stroke="#9ca3af" stroke-width="1"/>
      <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{h-pad_b}" stroke="#9ca3af" stroke-width="1"/>
      <polyline fill="none" stroke="#2563eb" stroke-width="2.5" points="{pts_str}"/>
      <polyline fill="none" stroke="#059669" stroke-width="2.5" stroke-dasharray="5,5" points="{fc_line_str}"/>
      {''.join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#2563eb"/>' for x, y in pts[:-1])}
      <circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="4.5" fill="#1d4ed8"/>
      <circle cx="{fc_pt[0]:.1f}" cy="{fc_pt[1]:.1f}" r="5" fill="#059669"/>
      <text x="{pts[-1][0]:.1f}" y="{h-pad_b+18}" font-size="11" fill="#4b5563" text-anchor="middle">{target_week}</text>
      <text x="{fc_pt[0]:.1f}" y="{h-pad_b+18}" font-size="11" fill="#059669" font-weight="600" text-anchor="middle">+{horizon}w Peak ({order_info["target_week"]})</text>
      <text x="{pad_l-8}" y="{pts[-1][1]+4:.1f}" font-size="10" fill="#4b5563" text-anchor="end">{y_hist[-1]:.0f}</text>
      <text x="{w-pad_r+8}" y="{fc_pt[1]+4:.1f}" font-size="10" fill="#059669" font-weight="600" text-anchor="start">{pred_val:.0f}</text>
    </svg>
    """

    all_forecasts = rows.sort_values(["horizon", "week"], ascending=[True, False])
    history_rows = "".join(
        f'<tr><td>{r["week"]}</td><td>{r["horizon"]}w</td><td>{r["rank"]}</td>'
        f'<td>{r["predicted_growth"]:.2f}×</td><td>{"Rising" if r["rising"] else "Normal"}</td></tr>'
        for _, r in all_forecasts.iterrows()
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(style.title())} — Forecast & Ordering Window</title>
<style>
  body {{ font-family:system-ui, -apple-system, sans-serif; background:#f9fafb; color:#111827; margin:0; padding:1.5rem; }}
  main {{ max-width:800px; margin:0 auto; background:#ffffff; padding:2rem; border-radius:12px; border:1px solid #e5e7eb; box-shadow:0 1px 3px rgba(0,0,0,0.05); }}
  h1 {{ margin:0 0 0.5rem 0; font-size:1.6rem; }}
  .meta {{ color:#6b7280; font-size:0.95rem; margin-bottom:1.5rem; }}
  .kpi-row {{ display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1.5rem; }}
  .kpi-card {{ flex:1; min-width:140px; padding:1rem; background:#f3f4f6; border-radius:8px; border-left:4px solid #2563eb; }}
  .kpi-val {{ font-size:1.3rem; font-weight:700; margin-top:0.25rem; }}
  .badge {{ display:inline-block; padding:3px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }}
  .badge-success {{ background:#d1fae5; color:#065f46; }}
  .badge-warning {{ background:#fef3c7; color:#92400e; }}
  .badge-critical {{ background:#fee2e2; color:#991b1b; font-weight:700; }}
  .badge-danger {{ background:#fee2e2; color:#b91c1c; }}
  .badge-neutral {{ background:#e5e7eb; color:#374151; }}
  table {{ width:100%; border-collapse:collapse; margin-top:1rem; }}
  th, td {{ text-align:left; padding:0.5rem; border-bottom:1px solid #e5e7eb; font-size:0.875rem; }}
  th {{ background:#f9fafb; font-weight:600; }}
  a {{ color:#2563eb; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
</style></head>
<body><main>
<p><a href="/?week={target_week}&horizon={horizon}">← Back to Trend Dashboard</a></p>
<h1>{escape(style.title())} <span class="badge {order_info["badge_class"]}">{order_info["ordering_urgency"]}</span></h1>
<div class="meta">Category: <b>{escape(category)}</b> | Origin Week: <b>{target_week}</b> | Horizon: <b>{horizon} weeks</b></div>

<div class="kpi-row">
  <div class="kpi-card">
    <div>Predicted Growth</div>
    <div class="kpi-val">{growth:.2f}×</div>
  </div>
  <div class="kpi-card">
    <div>Supplier Lead Time</div>
    <div class="kpi-val">{lead_time_weeks} weeks</div>
  </div>
  <div class="kpi-card">
    <div>Latest Order Deadline</div>
    <div class="kpi-val" style="color:#047857;">{order_info["order_deadline"]}</div>
  </div>
  <div class="kpi-card">
    <div>Target Peak Week</div>
    <div class="kpi-val">{order_info["target_week"]}</div>
  </div>
</div>

<h3>Actionable Buyer Recommendation</h3>
<p style="padding:0.75rem 1rem; background:#ecfdf5; border-left:4px solid #10b981; border-radius:4px; font-weight:500;">
  {order_info["ordering_action"]}
</p>

<h3>Trajectory & Ordering Window Timeline</h3>
{svg_chart}

<h3 style="margin-top:2rem;">Historical Forecasts for {escape(style.title())}</h3>
<div style="max-height:240px; overflow-y:auto; border:1px solid #e5e7eb; border-radius:6px;">
  <table>
    <thead><tr><th>Week</th><th>Horizon</th><th>Rank</th><th>Growth</th><th>Status</th></tr></thead>
    <tbody>{history_rows}</tbody>
  </table>
</div>
</main></body></html>"""


@app.get("/styles/{style}")
def style_history(
    style: str,
    format: str = Query("json", description="Output format: json or html"),
):
    """All forecasts for one style across the available weeks."""
    rows = RANKINGS[RANKINGS["style"].str.lower() == style.lower()]
    if rows.empty:
        raise HTTPException(404, f"Unknown style: {style}")
    if format == "html":
        return HTMLResponse(generate_style_view_html(style, 4, 4, None))
    rows = rows.sort_values(["horizon", "week"])
    columns = ["week", "horizon", "predicted_growth", "growth_vs_market", "rank", "rising", "held_back"]
    return {
        "style": rows["style"].iloc[0],
        "category": rows["category"].iloc[0],
        "forecasts": rows[columns].to_dict(orient="records"),
    }


@app.get("/style-view", response_class=HTMLResponse)
def style_view(
    style: str = Query(..., description="Style keyword (e.g. ballet flats, jorts)."),
    horizon: int = Query(4, description="Horizon weeks: 4 or 8."),
    lead_time_weeks: int = Query(4, ge=1, le=12, description="Supplier lead time in weeks."),
    week: str | None = Query(None, description="Forecast origin week."),
):
    """Visual page displaying SVG forecast curve and supplier ordering window timeline."""
    return generate_style_view_html(style, horizon, lead_time_weeks, week)


# ---------------------------------------------------------------- buyer page

@app.get("/", response_class=HTMLResponse)
def home(
    week: str | None = None,
    horizon: int = 4,
    category: str | None = None,
    top_k: int = Query(200, ge=1, le=200),
):
    """The buyer page: the week's trend report, with charts and the full ranking."""
    category = category or None
    lead_weeks = order_lead_weeks()
    data = get_rankings(week, horizon, top_k, category, lead_time_weeks=lead_weeks)
    same_period = RANKINGS["horizon"] == horizon
    all_rows = RANKINGS[same_period & (RANKINGS["week"] == data["week"])]
    shown = all_rows[all_rows["category"].str.lower() == category.lower()] if category else all_rows
    history = RANKINGS[same_period & (RANKINGS["week"] <= data["week"])]
    return page.render(
        data,
        all_rows,
        shown,
        history,
        WEEKS,
        CATEGORIES,
        category,
        APP_VERSION,
        search_history=HISTORY,
        explanations=EXPLANATIONS,
        lead_weeks=lead_weeks,
    )
