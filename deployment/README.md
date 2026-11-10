# Deployment: Before the Hype rankings app

A small web app that serves weekly style rankings to buyers. It reads a saved
rankings file made by the modelling code; it does not train models itself.

**Current status:** live on Azure Container Apps at
https://fashion-trends-api.salmonsky-bf89d2c7.eastasia.azurecontainerapps.io/

It serves the real weekly rankings from the LightGBM model
(`data/rankings.csv`, 137 styles, January 2025 – October 2026) with a rising
threshold of 1.2. Every merge into `main` that changes `deployment/` is tested,
built and deployed automatically. The fake file `data/rankings_fake.csv` is kept
for reference.

## What each file does

| File | Purpose |
| --- | --- |
| `app/main.py` | The FastAPI app: buyer page, API endpoints, request logging and error handling |
| `app/data.py` | Loads the rankings file and checks its format |
| `data/rankings.csv` | Real rankings from the LightGBM model |
| `data/rankings_fake.csv` | Fake rankings: 55 example styles, 6 weeks, horizons 4 and 8 |
| `scripts/make_fake_rankings.py` | Recreates the fake file |
| `tests/test_api.py` | Automatic checks (18 tests) |
| `Dockerfile` | Recipe for the container image |
| `azure/containerapp.yaml` | Azure settings: resources, environment variables, health probes, scaling |
| `../.github/workflows/deployment-ci.yml` | CI/CD pipeline on GitHub Actions |

## Endpoints

| Address | Returns |
| --- | --- |
| `/` | Buyer page: ranked table with week and horizon pickers |
| `/docs` | Interactive API documentation (made by FastAPI) |
| `/health` | `{"status": "ok", "version": ..., "rows": ..., "weeks": ...}`; used by the pipeline and Azure |
| `/weeks` | Forecast weeks in the file, newest first |
| `/rankings?horizon=4&top_k=10&week=2026-10-11&category=Shoes` | Top styles; all parameters optional |
| `/styles/{style}` | Every forecast for one style, e.g. `/styles/ballet flats` |

`version` in `/health` is the commit ID the running image was built from
(`dev` when run locally), so you can always tell which code is live.

## Settings (environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `RANKINGS_PATH` | `data/rankings.csv` | Rankings file to serve |
| `RISING_THRESHOLD` | `1.1` (live app: `1.2`) | Predicted growth above which a style is flagged as rising |
| `LOG_LEVEL` | `INFO` | `DEBUG` also logs every `/health` call |
| `APP_VERSION` | `dev` | Set automatically by the pipeline when the image is built |

No passwords or keys are needed by the app itself.

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

## The rankings file format

The file needs these columns (extra columns are fine):

| Column | Meaning |
| --- | --- |
| `week` | Week the forecast was made, `YYYY-MM-DD` |
| `style` | Keyword, e.g. `ballet flats` |
| `category` | One of the 11 categories |
| `horizon` | 4 or 8 |
| `predicted_growth` | Forecast average ÷ last 4-week average (1.0 = no change) |
| `rank` | 1 = highest expected growth, within each week and horizon |

The app refuses to start if the file breaks the format (missing columns,
horizon not 4 or 8, ranks not 1..n, duplicates), so problems show up in the
pipeline, not in front of users.

## The pipeline

On every push or pull request that touches `deployment/` or the workflow file:

1. **test**: installs packages and runs the 18 tests.
2. **build** (only if tests pass): builds the Docker image stamped with the
   commit ID, starts it, and calls `/health` and `/rankings`. A failure here
   shows the container logs. On `main` only, it then pushes the image to GitHub
   Container Registry as
   `ghcr.io/samichi-rungta/fashion-trends-forcasting/fashion-trends-api`,
   tagged with `latest` and the commit ID.
3. **deploy** (only on `main`, only if build passed): signs in to Azure,
   switches the container app to the new image, and waits until the live
   `/health` reports the new commit ID, then calls the live `/rankings`. If the
   new version is not live within about 20 minutes, the run fails.

Pull requests run steps 1 and 2 only, so changes are checked before they can
reach the live app.

## Cloud deployment (Azure)

| Part | Name | Purpose |
| --- | --- | --- |
| Resource group | `rg-fashion-trends` | Holds everything; deleting it removes all resources |
| Container Apps environment | `env-fashion-trends` (East Asia, standard `WorkloadProfiles` mode) | Where the container runs; provides HTTPS and the public address |
| Container app | `fashion-trends-api` | Runs the image; 0.5 CPU, 1 GB memory, 1–2 copies |
| Log Analytics workspace | `log-fashion-trends` | Collects the app's logs and Azure's events (kept 30 days) |
| Managed identity | `id-github-deploy` | The account GitHub Actions deploys with; allowed to manage this resource group only |

### Secure sign-in from GitHub (no stored password)

GitHub Actions signs in with OpenID Connect: for each run, GitHub issues a
short-lived token, and Azure accepts it only for runs from the `main` branch of
this repository. The repository secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`
and `AZURE_SUBSCRIPTION_ID` only name the identity; none of them is a password.
GitHub identifies the repository with permanent ID numbers
(`repo:samichi-rungta@64314150/fashion-trends-forcasting@1429854542:ref:refs/heads/main`),
so a different repository created later with the same name could not deploy.

### One-time setup (already done; for reproducing the deployment)

Needs the Azure CLI and a subscription. Azure for Students only allows a few
regions; list them with
`az policy assignment list --query "[].parameters.listOfAllowedLocations.value"`.

```powershell
az login
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

az group create --name rg-fashion-trends --location southeastasia
az monitor log-analytics workspace create --resource-group rg-fashion-trends --workspace-name log-fashion-trends --location eastasia
$WS_ID = az monitor log-analytics workspace show --resource-group rg-fashion-trends --workspace-name log-fashion-trends --query customerId -o tsv
$WS_KEY = az monitor log-analytics workspace get-shared-keys --resource-group rg-fashion-trends --workspace-name log-fashion-trends --query primarySharedKey -o tsv

# Choose the standard mode explicitly; East Asia otherwise may create a preview "Express" environment.
az containerapp env create --name env-fashion-trends --resource-group rg-fashion-trends --location eastasia --environment-mode WorkloadProfiles --logs-destination log-analytics --logs-workspace-id $WS_ID --logs-workspace-key $WS_KEY

az containerapp create --name fashion-trends-api --resource-group rg-fashion-trends --environment env-fashion-trends --image ghcr.io/samichi-rungta/fashion-trends-forcasting/fashion-trends-api:latest --target-port 8000 --ingress external --cpu 0.5 --memory 1.0Gi --min-replicas 1 --max-replicas 2 --env-vars RISING_THRESHOLD=1.2
az containerapp update --name fashion-trends-api --resource-group rg-fashion-trends --yaml deployment/azure/containerapp.yaml

# Identity for GitHub Actions
az identity create --name id-github-deploy --resource-group rg-fashion-trends --location eastasia
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
→ Logs), for example:

```text
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "fashion-trends-api"
| project TimeGenerated, Log_s
| order by TimeGenerated desc
```

### Cost

The app uses the Consumption plan, charged per second of CPU and memory. One
copy always runs because pulling the image from GitHub Container Registry
takes several minutes, longer than Azure's 5-minute idle shutdown; with
scale-to-zero, the app could not finish starting. An idle copy is charged at a
lower rate. Logs are charged by volume and kept for 30 days. To stop all
charges after evaluation:

```powershell
az group delete --name rg-fashion-trends --yes
```

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

## Not done yet (remaining work)

- Retrained model and the "growth relative to the market" column.
- Automatic weekly update of the rankings file.
- The forecast curve per style and the ordering window from the proposal.
