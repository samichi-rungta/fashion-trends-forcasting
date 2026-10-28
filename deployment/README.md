# Deployment: Before the Hype rankings app

A small web app that serves weekly style rankings to buyers. It reads a saved
rankings file made by the modelling code; it does not train models itself.

**Current status:** runs on a FAKE rankings file (`data/rankings_fake.csv`, model
name `fake_demo`). The numbers are random and must not appear as results.

## What each file does

| File | Purpose |
| --- | --- |
| `app/main.py` | The FastAPI app: buyer page and API endpoints |
| `app/data.py` | Loads the rankings file and checks its format |
| `data/rankings_fake.csv` | Fake rankings: 55 example styles, 6 weeks, horizons 4 and 8 |
| `scripts/make_fake_rankings.py` | Recreates the fake file |
| `tests/test_api.py` | Automatic checks (15 tests) |
| `Dockerfile` | Recipe for the container image |
| `../.github/workflows/deployment-ci.yml` | CI/CD pipeline on GitHub Actions |

## Endpoints

| Address | Returns |
| --- | --- |
| `/` | Buyer page: ranked table with week and horizon pickers |
| `/docs` | Interactive API documentation (made by FastAPI) |
| `/health` | `{"status": "ok", ...}`; used by the pipeline and the cloud |
| `/weeks` | Forecast weeks in the file, newest first |
| `/rankings?horizon=4&top_k=10&week=2026-10-11&category=Shoes` | Top styles; all parameters optional |
| `/styles/{style}` | Every forecast for one style, e.g. `/styles/ballet flats` |

## Run it on your computer

From this `deployment/` folder:

```bash
pip install -r requirements-dev.txt
python -m pytest -v               # run the tests
uvicorn app.main:app --reload     # start the app
```

Open http://localhost:8000 and http://localhost:8000/docs.

## Run it in Docker

Needs Docker Desktop. From this folder:

```bash
docker build -t fashion-trends-api .
docker run -p 8000:8000 fashion-trends-api
```

## Switching to the real rankings file

The real file needs these columns (extra columns are fine):

| Column | Meaning |
| --- | --- |
| `week` | Week the forecast was made, `YYYY-MM-DD` |
| `style` | Keyword, e.g. `ballet flats` |
| `category` | One of the 11 categories |
| `horizon` | 4 or 8 |
| `predicted_growth` | Forecast average ÷ last 4-week average (1.0 = no change) |
| `rank` | 1 = highest expected growth, within each week and horizon |

Steps: save it as `data/rankings.csv`, then either change `DEFAULT_PATH` in
`app/data.py` or set `RANKINGS_PATH=data/rankings.csv`. The app refuses to
start if the file breaks the format (missing columns, horizon not 4 or 8,
ranks not 1..n, duplicates), so problems show up in the pipeline, not in front
of users.

The rising flag uses growth above 1.1 by default. Once the team picks the
threshold on training data, set `RISING_THRESHOLD` (e.g. `1.2`).

## The pipeline

On every push or pull request that touches `deployment/`:

1. **test**: installs packages and runs the 15 tests.
2. **build** (only if tests pass): builds the Docker image, starts it, and
   calls `/health` and `/rankings`. A failure here shows the container logs.
3. **publish** (only on the default branch): pushes the image to GitHub
   Container Registry as `ghcr.io/<owner>/<repo>/fashion-trends-api`, tagged
   with `latest` and the commit id.

## Not done yet (remaining work)

- Real rankings file from Person 2.
- Deploying the published image to Azure Container Apps (or AWS App Runner).
- The forecast curve per style and the ordering window from the proposal.
