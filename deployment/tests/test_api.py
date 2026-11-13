"""Automatic checks for the API. Run from the deployment/ folder:
    python -m pytest -v
"""
import json
import logging

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.data import add_market_columns, check_rankings
from app.main import app

client = TestClient(app)


def test_health_reports_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["rows"] > 0


def test_rankings_default_to_latest_week_in_rank_order():
    latest = client.get("/weeks").json()["weeks"][0]
    data = client.get("/rankings").json()
    assert data["week"] == latest
    ranks = [s["rank"] for s in data["styles"]]
    assert ranks == sorted(ranks)
    assert ranks[0] == 1


def test_top_k_limits_the_number_of_styles():
    data = client.get("/rankings", params={"top_k": 5, "horizon": 8}).json()
    assert data["count"] == 5
    assert data["horizon"] == 8


def test_rising_flag_matches_threshold_and_market_flag():
    for week in client.get("/weeks").json()["weeks"][:40]:
        data = client.get("/rankings", params={"top_k": 200, "week": week}).json()
        for s in data["styles"]:
            above = s["predicted_growth"] > data["rising_threshold"]
            assert s["rising"] == (above and not data["alerts_held_back"])
            assert s["held_back"] == (above and data["alerts_held_back"])


def test_flagged_weeks_hold_back_all_alerts():
    flagged = main.RANKINGS.loc[main.RANKINGS["inputs_out_of_range"], "week"].unique()
    if len(flagged) == 0:
        pytest.skip("this rankings file has no out-of-range weeks")
    data = client.get("/rankings", params={"week": flagged[0], "top_k": 200}).json()
    assert data["alerts_held_back"] is True
    assert data["rising_count"] == 0
    assert "Unusual week." in client.get("/", params={"week": flagged[0]}).text


def test_market_columns_are_consistent():
    data = client.get("/rankings", params={"top_k": 200}).json()
    for s in data["styles"]:
        assert s["growth_vs_market"] == pytest.approx(s["predicted_growth"] / data["market_growth"], rel=1e-3)


def test_category_filter_keeps_only_that_category():
    data = client.get("/rankings", params={"category": "shoes", "top_k": 50}).json()
    assert data["count"] > 0
    assert {s["category"] for s in data["styles"]} == {"Shoes"}


def test_invalid_horizon_is_rejected():
    assert client.get("/rankings", params={"horizon": 6}).status_code == 422


def test_unknown_week_and_category_return_404():
    assert client.get("/rankings", params={"week": "1999-01-01"}).status_code == 404
    assert client.get("/rankings", params={"category": "spacesuits"}).status_code == 404


def test_style_lookup_ignores_capitals():
    response = client.get("/styles/Ballet Flats")
    assert response.status_code == 200
    assert response.json()["style"] == "ballet flats"
    assert client.get("/styles/not-a-style").status_code == 404


def test_health_reports_the_code_version():
    assert client.get("/health").json()["version"] == main.APP_VERSION


def test_requests_are_logged(caplog):
    with caplog.at_level(logging.INFO, logger="fashion_trends"):
        client.get("/rankings")
        client.get("/rankings", params={"horizon": 6})
    messages = [r.getMessage() for r in caplog.records]
    assert any("path=/rankings status=200" in m for m in messages)
    assert any("path=/rankings status=422" in m for m in messages)


def test_unexpected_error_returns_500_and_is_logged(monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(main, "get_rankings", broken)
    with caplog.at_level(logging.ERROR, logger="fashion_trends"):
        response = TestClient(app, raise_server_exceptions=False).get("/rankings")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert any("error method=GET path=/rankings" in r.getMessage() for r in caplog.records)


def test_home_page_shows_category_cards_and_table():
    page = client.get("/").text
    assert "What to stock for the next 4 weeks" in page
    assert "Predicted growth in Google search interest." in page
    assert 'class="grid"' in page and '<table id="table">' in page
    # no technical labels on the page a buyer sees
    for jargon in ("High-conviction", "Alpha vs. market", "SHAP", "Overall market trend"):
        assert jargon not in page


def test_category_cards_follow_the_stock_up_items():
    from app import page as page_module
    data = main.get_rankings(None, 4, 200, None)
    rows = main.RANKINGS[(main.RANKINGS["week"] == data["week"]) & (main.RANKINGS["horizon"] == 4)].copy()
    rows["action"] = rows.apply(page_module.action, axis=1)
    html = page_module.top_section(rows, data, 6, data["week"], None)
    stock = rows[rows["action"] == "stock"]
    if stock.empty:
        assert "No items are expected to rise more than 20%" in html
    else:
        best = stock.groupby("category").size().sort_values(ascending=False)
        assert best.index[0] in html
        assert f"{best.iloc[0]} {'style' if best.iloc[0] == 1 else 'styles'} predicted to rise" in html
        assert html.count('class="cat-card"') == min(3, len(best))
    # with every alert held back, there are no cards, only the plain message
    rows["action"] = "check"
    assert "No items are expected to rise more than 20%" in page_module.top_section(rows, data, 6, data["week"], None)


def test_unusual_forecast_note():
    from app import page as page_module
    dates = pd.date_range("2017-06-04", "2026-11-01", freq="7D")
    flat = pd.DataFrame(50.0, index=dates, columns=[f"s{i}" for i in range(30)])  # nothing ever changes
    assert page_module.past_market_range(flat, "2026-11-01", 4) == pytest.approx((1.0, 1.0))
    rows = pd.DataFrame({"style": ["a"], "category": ["X"], "predicted_growth": [1.5], "action": ["stock"]})
    usual = {"horizon": 4, "week": "2026-11-01", "market_growth": 1.0}
    unusual = usual | {"market_growth": 1.25}
    assert "Unusual forecast" not in page_module.top_section(rows, usual, 6, "2026-11-01", flat)
    assert "Unusual forecast" in page_module.top_section(rows, unusual, 6, "2026-11-01", flat)


def test_home_page_category_filter():
    page = client.get("/", params={"category": "Shoes", "horizon": 8}).text
    assert "What to stock for the next 8 weeks" in page
    table = page.split('<tbody id="rows">')[1].split("</tbody>")[0]
    assert table.count("<tr") > 0
    assert "Outerwear" not in table  # only shoes in the table


# Checks on the file format itself, so a broken results file is caught before deployment.
def make_file():
    return pd.DataFrame({
        "week": ["2026-10-11"] * 2, "style": ["a", "b"], "category": ["X", "X"],
        "horizon": [4, 4], "predicted_growth": [1.3, 0.9], "rank": [1, 2],
    })


def test_good_file_passes_check():
    check_rankings(make_file())


def test_alerts_made_with_another_threshold_are_rejected():
    # The file's alerts must follow the app's threshold; a mismatch stops the app from starting.
    df = pd.DataFrame({
        "week": ["2026-01-04"] * 2, "style": ["a", "b"], "horizon": [4, 4],
        "predicted_growth": [1.15, 0.9], "inputs_out_of_range": [False, False],
        "alert": [True, False],  # made with threshold 1.1
    })
    with pytest.raises(ValueError, match="does not match"):
        add_market_columns(df, threshold=1.2)
    assert add_market_columns(df, threshold=1.1)["rising"].tolist() == [True, False]


def test_files_without_market_columns_still_work():
    df = pd.DataFrame({"week": ["2026-01-04"] * 2, "style": ["a", "b"], "horizon": [4, 4],
                       "predicted_growth": [1.3, 0.9]})
    out = add_market_columns(df, threshold=1.2)
    assert out["market_growth"].tolist() == pytest.approx([1.1, 1.1])
    assert out["rising"].tolist() == [True, False]


@pytest.mark.parametrize("change, message", [
    (lambda df: df.drop(columns="rank"), "missing columns"),
    (lambda df: df.assign(horizon=[4, 6]), "Horizon"),
    (lambda df: df.assign(rank=[1, 1]), "Ranks"),
    (lambda df: df.assign(predicted_growth=[1.3, -1]), "above 0"),
    (lambda df: df.assign(style=["a", "a"]), "once per week"),
])
def test_bad_files_are_rejected(change, message):
    with pytest.raises(ValueError, match=message):
        check_rankings(change(make_file()))


# Item details: the search history and SHAP explanations must match the rankings they describe.
def page_items(**params):
    page = client.get("/", params=params).text
    return json.loads(page.split('<script id="page-data" type="application/json">')[1].split("</script>")[0])


def test_explanations_cover_every_forecast():
    if main.EXPLANATIONS is None:
        pytest.skip("no explanations file")
    keys = set(main.EXPLANATIONS.index)
    missing = [k for k in main.RANKINGS[["week", "style", "horizon"]].itertuples(index=False, name=None) if k not in keys]
    assert not missing, f"{len(missing)} forecasts have no explanation, e.g. {missing[:3]}"


def test_history_covers_every_style():
    if main.HISTORY is None:
        pytest.skip("no search history file")
    assert set(main.RANKINGS["style"]) <= set(main.HISTORY.columns)


def test_item_details_add_up():
    data = page_items()
    item = data["items"][0]
    assert item["rank"] == 1 and item["label"]
    if "shap" in item:
        # SHAP contributions multiply up to the forecast (small differences from averaging over seeds).
        total = (1 + item["shap"]["base"])
        for g in ("recent_level", "momentum", "season", "market", "category"):
            total *= 1 + item["shap"][g]
        assert total == pytest.approx(item["g"], rel=0.05)
    if "hist" in item:
        assert len(item["hist"]) == 8 and item["fc"] > 0


def test_page_works_without_detail_files():
    from app import page
    data = main.get_rankings(None, 4, 200, None)
    rows = main.RANKINGS[(main.RANKINGS["week"] == data["week"]) & (main.RANKINGS["horizon"] == 4)]
    html = page.render(data, rows, rows, rows, main.WEEKS, main.CATEGORIES, None, "test")
    assert '"shap"' not in html and '"hist"' not in html and "What to stock" in html


@pytest.mark.parametrize("lead, horizon, text", [
    (6, 4, "so your order would arrive after this period. Check the 8-week forecast."),
    (6, 8, "2 weeks before this forecast period ends"),
    (8, 8, "just as this forecast period ends"),
])
def test_delivery_note(monkeypatch, lead, horizon, text):
    monkeypatch.setenv("ORDER_LEAD_WEEKS", str(lead))
    assert text in client.get("/", params={"horizon": horizon}).text


def test_every_item_has_its_own_picture():
    from app.pictures import picture
    styles = main.RANKINGS[["style", "category"]].drop_duplicates()
    pictures = {picture(s, c) for s, c in styles.itertuples(index=False)}
    assert len(pictures) == len(styles)
