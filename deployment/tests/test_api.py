"""Automatic checks for the API. Run from the deployment/ folder:
    python -m pytest -v
"""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data import check_rankings
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


def test_rising_flag_matches_threshold():
    data = client.get("/rankings", params={"top_k": 200}).json()
    for s in data["styles"]:
        assert s["rising"] == (s["predicted_growth"] > data["rising_threshold"])


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


def test_home_page_shows_a_table():
    response = client.get("/")
    assert response.status_code == 200
    assert "<table>" in response.text


# Checks on the file format itself, so a broken results file is caught before deployment.
def make_file():
    return pd.DataFrame({
        "week": ["2026-10-11"] * 2, "style": ["a", "b"], "category": ["X", "X"],
        "horizon": [4, 4], "predicted_growth": [1.3, 0.9], "rank": [1, 2],
    })


def test_good_file_passes_check():
    check_rankings(make_file())


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
