"""Small web API that serves weekly style rankings to buyers.

Run locally (from the deployment/ folder):
    uvicorn app.main:app --reload
Then open http://localhost:8000 (buyer page) or http://localhost:8000/docs (API docs).
"""
import logging
import os
import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import page
from app.data import (load_explanations, load_history, load_rankings, order_lead_weeks, rankings_path,
                      rising_threshold)

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
    title="Before the Hype: Fashion Trend Rankings",
    description="Serves 4- and 8-week growth forecasts for fashion styles, ranked for buyers.",
    version="0.2.0",
)

# The file is read once when the app starts. A new file means a restart (or a new container).
RANKINGS = load_rankings()
WEEKS = sorted(RANKINGS["week"].unique(), reverse=True)  # newest first
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


def get_rankings(week: str | None, horizon: int, top_k: int, category: str | None) -> dict:
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
    columns = ["rank", "style", "category", "predicted_growth", "growth_vs_market", "rising", "held_back"]
    return {
        "week": week,
        "horizon": horizon,
        "rising_threshold": rising_threshold(),
        # Week-level facts, always about all styles (not only the chosen category).
        "market_growth": round(float(all_rows["market_growth"].iloc[0]), 4),
        "alerts_held_back": bool(all_rows["inputs_out_of_range"].any()),
        "rising_count": int(all_rows["rising"].sum()),
        "style_count": len(all_rows),
        "count": len(rows),
        "styles": rows[columns].to_dict(orient="records"),
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
    columns = ["week", "horizon", "predicted_growth", "growth_vs_market", "rank", "rising", "held_back"]
    return {
        "style": rows["style"].iloc[0],
        "category": rows["category"].iloc[0],
        "forecasts": rows[columns].to_dict(orient="records"),
    }


# ---------------------------------------------------------------- buyer page

CATEGORIES = sorted(RANKINGS["category"].unique())


@app.get("/", response_class=HTMLResponse)
def home(
    week: str | None = None,
    horizon: int = 4,
    category: str | None = None,
    top_k: int = Query(200, ge=1, le=200),
):
    """The buyer page: the week's trend report, with charts and the full ranking."""
    category = category or None
    data = get_rankings(week, horizon, top_k, category)
    same_period = RANKINGS["horizon"] == horizon
    all_rows = RANKINGS[same_period & (RANKINGS["week"] == data["week"])]
    shown = all_rows[all_rows["category"].str.lower() == category.lower()] if category else all_rows
    history = RANKINGS[same_period & (RANKINGS["week"] <= data["week"])]
    return page.render(data, all_rows, shown, history, WEEKS, CATEGORIES, category, APP_VERSION,
                       search_history=HISTORY, explanations=EXPLANATIONS, lead_weeks=order_lead_weeks())
