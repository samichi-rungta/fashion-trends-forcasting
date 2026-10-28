"""Small web API that serves weekly style rankings to buyers.

Run locally (from the deployment/ folder):
    uvicorn app.main:app --reload
Then open http://localhost:8000 (buyer page) or http://localhost:8000/docs (API docs).
"""
from html import escape
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.data import load_rankings, rankings_path, rising_threshold

app = FastAPI(
    title="Before the Hype: Fashion Trend Rankings",
    description="Serves 4- and 8-week growth forecasts for fashion styles, ranked for buyers.",
    version="0.1.0",
)

# The file is read once when the app starts. A new file means a restart (or a new container).
RANKINGS = load_rankings()
WEEKS = sorted(RANKINGS["week"].unique(), reverse=True)  # newest first


def get_rankings(week: str | None, horizon: int, top_k: int, category: str | None) -> dict:
    """Shared logic for the JSON endpoint and the HTML page."""
    if horizon not in (4, 8):
        raise HTTPException(422, "horizon must be 4 or 8")
    week = week or WEEKS[0]
    if week not in WEEKS:
        raise HTTPException(404, f"No rankings for week {week}. Available: {WEEKS}")

    rows = RANKINGS[(RANKINGS["week"] == week) & (RANKINGS["horizon"] == horizon)]
    if category:
        rows = rows[rows["category"].str.lower() == category.lower()]
        if rows.empty:
            raise HTTPException(404, f"Unknown category: {category}")

    rows = rows.sort_values("rank").head(top_k)
    columns = ["rank", "style", "category", "predicted_growth", "rising"]
    return {
        "week": week,
        "horizon": horizon,
        "rising_threshold": rising_threshold(),
        "count": len(rows),
        "styles": rows[columns].to_dict(orient="records"),
    }


@app.get("/health")
def health() -> dict:
    """Used by the CI pipeline and by Azure/AWS to check the app is alive."""
    return {
        "status": "ok",
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
) -> dict:
    """Top-ranked styles for one week and horizon. Rank 1 = highest expected growth."""
    return get_rankings(week, horizon, top_k, category)


@app.get("/styles/{style}")
def style_history(style: str) -> dict:
    """All forecasts for one style across the available weeks."""
    rows = RANKINGS[RANKINGS["style"].str.lower() == style.lower()]
    if rows.empty:
        raise HTTPException(404, f"Unknown style: {style}")
    rows = rows.sort_values(["horizon", "week"])
    columns = ["week", "horizon", "predicted_growth", "rank", "rising"]
    return {
        "style": rows["style"].iloc[0],
        "category": rows["category"].iloc[0],
        "forecasts": rows[columns].to_dict(orient="records"),
    }


@app.get("/", response_class=HTMLResponse)
def home(week: str | None = None, horizon: int = 4, top_k: int = Query(20, ge=1, le=200)):
    """Simple page for buyers: a ranked table with week and horizon pickers."""
    data = get_rankings(week, horizon, top_k, None)

    week_options = "".join(
        f'<option value="{w}"{" selected" if w == data["week"] else ""}>{w}</option>' for w in WEEKS
    )
    horizon_options = "".join(
        f'<option value="{h}"{" selected" if h == horizon else ""}>{h} weeks</option>' for h in (4, 8)
    )
    table_rows = "".join(
        f'<tr class="{"up" if s["rising"] else ""}"><td>{s["rank"]}</td><td>{escape(s["style"])}</td>'
        f'<td>{escape(s["category"])}</td><td>{s["predicted_growth"]:.2f}×</td>'
        f'<td>{"Rising" if s["rising"] else ""}</td></tr>'
        for s in data["styles"]
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Before the Hype</title>
<style>
  :root {{ --bg:#fafaf7; --fg:#1d1d1b; --muted:#6b6b66; --line:#e3e3dd; --up:#e6f4ea; --upfg:#1e6b35; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#18181a; --fg:#ececea; --muted:#9a9a95; --line:#2e2e31; --up:#17311f; --upfg:#8fd6a4; }}
  }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.5 system-ui, sans-serif; }}
  main {{ max-width:760px; margin:0 auto; padding:2rem 1rem; }}
  p {{ color:var(--muted); }}
  form {{ display:flex; gap:.75rem; flex-wrap:wrap; align-items:center; margin:1.5rem 0; }}
  select, button {{ font:inherit; padding:.35rem .6rem; }}
  table {{ width:100%; border-collapse:collapse; }}
  th, td {{ text-align:left; padding:.5rem; border-bottom:1px solid var(--line); }}
  tr.up td:last-child {{ color:var(--upfg); font-weight:600; }}
  tr.up {{ background:var(--up); }}
</style></head>
<body><main>
<h1>Before the Hype</h1>
<p>Styles ranked by expected growth in search interest. Growth = forecast average ÷ last 4-week average.
Rising means growth above {data["rising_threshold"]}. Source file: {escape(rankings_path().name)}.</p>
<form method="get">
  <label>Week <select name="week">{week_options}</select></label>
  <label>Horizon <select name="horizon">{horizon_options}</select></label>
  <button type="submit">Show</button>
  <a href="/docs">API docs</a>
</form>
<table><thead><tr><th>Rank</th><th>Style</th><th>Category</th><th>Growth</th><th></th></tr></thead>
<tbody>{table_rows}</tbody></table>
</main></body></html>"""
