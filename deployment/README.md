# Deployment

The deployment folder packages the trend rankings into a small web application,
tests it automatically, builds a Docker image and deploys it to Azure Container
Apps on every push to `main`.

A buyer opens the app in a browser to see which styles are rising, which
category is leading, whether the whole market is moving, and when to place
orders.

## Architecture

```text
                  GitHub Actions (CI/CD)
                            │
               pytest ───► docker build ───► ghcr.io
                                                │
                                                ▼
     Browser / Buyer ───────────────► Azure Container Apps
  http://.../ (buyer page)                (FastAPI app)
  http://.../docs (API)                         │
                                                ▼
                                         rankings.csv
                                         (from LightGBM)
```

## Files

| File | Purpose |
| --- | --- |
| `app/main.py` | The FastAPI app: API endpoints, ordering windows, request logging, and error handling |
| `app/page.py` | The buyer page: KPI bar, item cards and table, item details, and order plan export |
| `app/pictures.py` | Original drawings for every item (no copyrighted photos) |
| `app/data.py` | Loads the rankings file and checks its format |
| `data/rankings.csv` | Real weekly rankings: 137 styles, 2025-01-05 to 2026-10-11, horizons 4 and 8 |
| `data/search_history.csv` | Weekly search interest per style, for the chart in the item details (optional) |
| `data/explanations.csv` | SHAP contributions for every forecast, for the item details (optional) |
| `data/rankings_fake.csv` | Fake rankings: 55 example styles, 6 weeks, horizons 4 and 8 |
| `scripts/refresh_rankings.py` | Automated refresh script to re-score, validate, and update rankings |
| `scripts/make_fake_rankings.py` | Recreates the fake file |
| `tests/test_api.py` | Automatic checks (30 tests covering API, ordering windows, and charts) |
| `Dockerfile` | Recipe for the container image |
| `azure/containerapp.yaml` | Azure settings: resources, environment variables, health probes, scaling |
| `../.github/workflows/deployment-ci.yml` | CI/CD pipeline on GitHub Actions (Azure Container Apps) |
| `../.github/workflows/weekly-refresh.yml` | Scheduled weekly cron job to auto-refresh rankings |

## Endpoints

| Address | Returns |
| --- | --- |
| `/` | Buyer page: KPI bar, every item as a card or in a sortable table, item details on click, and an order plan exported as CSV |
| `/docs` | Interactive API documentation (made by FastAPI) |
| `/health` | `{"status": "ok", "version": ..., "rows": ..., "weeks": ...}`; used by the pipeline and Azure |
| `/weeks` | Forecast weeks in the file, newest first |
| `/rankings?horizon=4&top_k=10&week=2026-10-11&category=Shoes&lead_time_weeks=4` | Top styles with growth, growth vs market, alerts, supplier order deadlines and urgency |
| `/styles/{style}` | All forecasts for one style (JSON for API, HTML report when visited with `?format=html`) |
| `/style-view?style=ballet+flats&horizon=4&lead_time_weeks=4` | Visual style forecast page with SVG curve and shaded ordering window |

`version` in `/health` is the commit ID the running image was built from
(`dev` when run locally).

## Features for Fast Fashion Retail Buyers

1. **Trend Rankings:** 137 styles ranked by expected growth ratio (forecast average ÷ last 4-week average).
2. **Trajectory Sparklines:** Compact inline SVG sparklines showing each style's recent trajectory.
3. **Supplier Ordering Windows:** Computes target peak week and latest order deadline based on the retailer's lead time (e.g., 2, 4, 6, 8 weeks).
4. **Buyer Urgency Badges:**
   - **Window Open (Green):** Sufficient lead-time cushion to plan production.
   - **Order Soon (Amber):** Order deadline approaching within 1–2 weeks.
   - **Order Now (Red Bold):** Critical deadline this week to catch predicted peak.
   - **Window Closed:** Lead time exceeds horizon; requires express replenishment.
   - **Monitor / Steady (Grey):** Style stable/declining; maintain base replenishment.
5. **Interactive Forecast Curves:** Clicking any style shows a timeline chart displaying historical search interest, 4w/8w forecast trajectory, and the shaded supplier ordering window.
6. **Order Plan CSV Export:** Export current buying recommendations and quantities directly to CSV.

## Running locally

From the `deployment/` folder:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then visit:

- `http://localhost:8000` for the buyer page
- `http://localhost:8000/docs` for the interactive API documentation

Run the automated checks with:

```bash
pytest -v
```

## Running with Docker locally

```bash
docker build -t fashion-trends-api .
docker run -p 8000:8000 fashion-trends-api
```

## Continuous deployment

The workflow `.github/workflows/deployment-ci.yml` runs on every pull request
and push to `main`. It has four jobs:

1. **test**: installs packages and runs the tests.
2. **build** (only if tests pass): builds the Docker image, starts it, and
   calls `/health` and `/rankings`. A failure here shows the container logs.
3. **publish** (only on the default branch): pushes the image to GitHub
   Container Registry as `ghcr.io/<owner>/<repo>/fashion-trends-api`, tagged
   with `latest` and the commit id.
4. **deploy** (only on default branch): updates Azure Container Apps using OpenID Connect
   and verifies the live health endpoint serves the new SHA version.

## Azure setup

The app runs on Azure Container Apps in the West Europe region, in a resource
group named `rg-fashion-trends`.

### Initial creation (run once)

Install the Azure CLI, sign in, and run from a PowerShell or bash prompt:

```powershell
# Log in and choose the subscription
az login
az account set --subscription "<subscription-id>"

# Register the resource providers (takes a minute the first time)
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

# Resource group and log workspace
az group create --name rg-fashion-trends --location westeurope
az monitor log-analytics workspace create --resource-group rg-fashion-trends --workspace-name log-fashion-trends

# Container Apps environment (standard "WorkloadProfiles" mode)
az containerapp env create `
  --name env-fashion-trends `
  --resource-group rg-fashion-trends `
  --location westeurope `
  --logs-workspace-id (az monitor log-analytics workspace show --resource-group rg-fashion-trends --workspace-name log-fashion-trends --query customerId -o tsv) `
  --logs-workspace-key (az monitor log-analytics workspace get-shared-keys --resource-group rg-fashion-trends --workspace-name log-fashion-trends --query primarySharedKey -o tsv)

# Create the Container App
az containerapp create `
  --name fashion-trends-api `
  --resource-group rg-fashion-trends `
  --environment env-fashion-trends `
  --image mcr.microsoft.com/azuredocs/aci-helloworld:latest `
  --target-port 8000 `
  --ingress external `
  --cpu 0.5 --memory 1.0Gi `
  --min-replicas 1 --max-replicas 1
```

### GitHub Actions sign-in (OIDC)

The pipeline authenticates to Azure without stored passwords, using OpenID
Connect:

```powershell
az identity create --name id-github-deploy --resource-group rg-fashion-trends
$ID_PRINCIPAL = az identity show --name id-github-deploy --resource-group rg-fashion-trends --query principalId -o tsv
$RG_ID = az group show --name rg-fashion-trends --query id -o tsv
az role assignment create --assignee-object-id $ID_PRINCIPAL --assignee-principal-type ServicePrincipal --role Contributor --scope $RG_ID
az identity federated-credential create --name github-main --identity-name id-github-deploy --resource-group rg-fashion-trends --issuer https://token.actions.githubusercontent.com --subject 'repo:samichi-rungta@64314150/fashion-trends-forcasting@1429854542:ref:refs/heads/main' --audiences api://AzureADTokenExchange
```

Then add the three repository secrets (Settings → Secrets and variables →
Actions) with the identity's client ID, the tenant ID and the subscription ID.

### Changing settings

Edit `azure/containerapp.yaml` and apply it from the repository root:

```powershell
az containerapp update --name fashion-trends-api --resource-group rg-fashion-trends --yaml deployment/azure/containerapp.yaml
```

The file sets the image to `latest`; the pipeline sets the exact commit tag on
the next deployment.

### Health checks, logs and monitoring

- **Health probes:** Azure calls `/health` to decide when a new version is
  ready (startup), whether to send it traffic (readiness) and whether to
  restart it (liveness). A new version only receives traffic once it is ready,
  so updates happen without downtime.
- **App logs:** one line at startup (version, rows, weeks, threshold) and one
  per request (path, status code, duration). Errors are logged with the full
  traceback, while visitors only see `Internal server error`.

```powershell
# The app's own log, live
az containerapp logs show --name fashion-trends-api --resource-group rg-fashion-trends --type console --tail 20
# Azure's events (image pulls, starts, failed probes)
az containerapp logs show --name fashion-trends-api --resource-group rg-fashion-trends --type system --tail 30
# Versions and their health
az containerapp revision list --name fashion-trends-api --resource-group rg-fashion-trends -o table
```

Older logs are in the Log Analytics workspace (Azure portal → `log-fashion-trends`
→ Logs).

### Troubleshooting notes

- **Deploy hangs or the new version never goes live:** check the environment
  mode with
  `az containerapp env show --name env-fashion-trends --resource-group rg-fashion-trends --query properties.environmentMode`.
  The preview "Express" mode did not finish updates; the standard
  `WorkloadProfiles` mode does.
- **Sign-in fails with AADSTS700213:** the trusted subject must match the one
  GitHub sends, including the ID numbers (see above).
- **"stream timeout" in the browser:** the app has not started yet, usually
  because the image is still downloading; check the system events.

## Completed Production Capabilities

- Real rankings served from LightGBM model for 137 styles across 2025–2026.
- Continuous deployment pipeline active to Azure Container Apps.
- Supplier lead-time ordering window calculation and urgency badges.
- Trend trajectory sparklines in buyer table and responsive SVG forecast timeline charts per style.
- Scheduled weekly refresh workflow configured in GitHub Actions (`.github/workflows/weekly-refresh.yml`).
