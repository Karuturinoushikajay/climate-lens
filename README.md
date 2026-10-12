# Climate Lens: Climate Hazard Trend Analyzer

Climate Lens detects heatwaves in historical daily maximum temperature data and analyses how their frequency, duration, and intensity have changed for a chosen place and period. It was built for the Dygnify Ventures Full-Stack Developer case study.

- **Frontend:** React 19, TypeScript, Vite, Recharts, React Leaflet, Lucide icons
- **Backend:** Python, FastAPI, Pydantic, HTTPX, NumPy, ReportLab
- **Storage:** MongoDB with TTL indexes, falling back to an in-process cache
- **Data:** [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), daily `temperature_2m_max` from ERA5 / ERA5-Land reanalysis

**Live demo:** https://climate-lens-gamma.vercel.app
**API:** https://climate-lens-api.onrender.com/api/health (interactive docs at [/docs](https://climate-lens-api.onrender.com/docs))

The backend is on Render's free tier and sleeps when idle, so the first request after a pause can take up to a minute.

> **Status, stated honestly**
> - **Implemented and tested:** the full analysis pipeline, the API, CSV and PDF exports, the dashboard, and the map. 89 backend tests and 32 frontend tests pass.
> - **Verified locally:** the backend and frontend dev servers, run against the live Open-Meteo API.
> - **Not yet verified:** the Docker Compose stack. Docker Desktop's Linux engine could not start on the development machine because WSL has no distributions installed. The Compose file validates with `docker compose config`, but the containers were not built or run.
> - **Deployed and verified live (12 October 2026):** frontend on Vercel, backend on Render, cache on MongoDB Atlas (free M0). Live checks passed for CORS from the Vercel origin, a Hyderabad 1990-2025 analysis, the CSV download, and the PDF download. `/api/health` reports `"mode": "mongodb"`, and a repeated Delhi 2000-2024 analysis went from a cache miss (3.9 s) to a MongoDB cache hit (1.1 s).

---

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [API](#api)
- [Methodology](#methodology)
- [Caching](#caching)
- [Security and performance](#security-and-performance)
- [Tests](#tests)
- [Deployment](#deployment)
- [Publishing to GitHub](#publishing-to-github)
- [Known limitations](#known-limitations)
- [Future improvements](#future-improvements)
- [AI-tool disclosure](#ai-tool-disclosure)

## Features

**Region selection**
- City presets (Hyderabad, Mumbai, Delhi, Bengaluru, Chennai, Visakhapatnam, Kolkata, Pune, Ahmedabad, Jaipur, Nagpur, Lucknow) are single points.
- State presets (Telangana, Andhra Pradesh, Tamil Nadu, Rajasthan, Maharashtra, Odisha) are approximate rectangles.
- On the map, click once to choose a point, or click two corners to draw a lat-lon box.
- Coordinates and box edges can be typed in manually, and you can set a custom label.

**Hazard:** Heatwave is selected by default. Drought and heavy rainfall appear in the list but are disabled, and the API rejects them.

**Baselines:** the 95th-percentile threshold comes either from the analysis period itself or from a fixed reference period such as 1991-2020.

**Dashboard**
- Summary cards
- Annual heatwave-day and event-count charts, each with a 5-year rolling mean and a linear fit
- An annual Tmax chart with the threshold line
- Data-driven trend interpretation
- A statistics panel with regression and Mann-Kendall results, including tooltips
- A methodology and data-quality panel
- A year-by-year table
- Sources and limitations

**Exports:** server-generated CSV and PDF reports for exactly the analysis shown on screen.

**Robustness**
- Validation, rate limiting, timeouts, and bounded retries
- Uniform JSON errors
- Loading, empty, error, and retry states in the UI
- Protection against stale results being shown for a different selection

## Architecture

```mermaid
flowchart LR
  UI[React dashboard] -->|"GET /api/*"| API[FastAPI routes]
  API --> RL[Rate limiter]
  API --> SVC[AnalysisService]
  SVC --> CACHE[Cache store]
  CACHE --> MONGO[(MongoDB TTL)]
  CACHE --> MEM[In-memory fallback]
  SVC --> WX[Open-Meteo client]
  SVC --> CLIM[Climate logic]
  API --> CSV[CSV export]
  API --> PDF[PDF report]
```

The dashboard JSON, the CSV, and the PDF all come from one `AnalysisService.analyze()` call, so their numbers cannot drift apart. See [docs/architecture.md](docs/architecture.md) for the data flow and [docs/requirements-traceability.md](docs/requirements-traceability.md) for the mapping from requirements to code and tests.

```
.
├── backend/
│   ├── app/
│   │   ├── api/routes.py           # HTTP endpoints
│   │   ├── cache/store.py          # MongoDB + in-memory cache
│   │   ├── climate/                # pure analysis: heatwave.py, trends.py, mann_kendall.py
│   │   ├── exports/                # csv_export.py, pdf_report.py
│   │   ├── models/schemas.py       # Pydantic request/response models
│   │   ├── security/rate_limit.py
│   │   ├── services/               # weather.py (Open-Meteo), analysis.py, regions.py
│   │   ├── config.py, errors.py, main.py
│   ├── tests/                      # pytest: unit, API, integration (weather API mocked)
│   ├── Dockerfile, requirements*.txt, pytest.ini
├── frontend/
│   ├── src/                        # App, components/, api/, hooks/, state/, test/
│   ├── Dockerfile, nginx.conf, vercel.json
├── docs/                           # architecture.md, requirements-traceability.md
├── docker-compose.yml, render.yaml, .env.example
```

Tests live next to each application (`backend/tests`, `frontend/src/**/*.test.ts(x)`) rather than in a top-level `tests/` folder, so each toolchain finds its own tests.

## Quick start

### Docker (MongoDB + backend + frontend)

```bash
cp .env.example .env    # optional
docker compose up --build
```

| Service | URL |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

If those ports are already taken, override them. CORS and the frontend's API URL follow automatically:

```bash
FRONTEND_PORT=5181 BACKEND_PORT=8011 docker compose up --build
```

> Not yet verified. On the development machine the Docker engine failed to start, so this command has not been run end to end; see [Known limitations](#known-limitations). `docker compose config` resolves correctly, including the port overrides.

### Local development without Docker

**Backend** (Python 3.12+; developed on 3.14):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Without `MONGODB_URI` the backend uses the in-memory cache, and `/api/health` reports `"mode": "memory"`.

**Frontend** (Node 20+):

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173 (uses VITE_API_BASE_URL, default http://localhost:8000)
```

## Configuration

All settings come from environment variables; see [.env.example](.env.example). Never commit real credentials.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MONGODB_URI` | empty | MongoDB connection string. Empty means in-memory cache. |
| `MONGODB_DATABASE` | `climate_lens` | Database name |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated CORS allow-list. Set this to the deployed frontend origin. |
| `ALLOWED_ORIGIN_REGEX` | empty | Optional full-match regex for additional origins, such as Vercel's per-deployment URLs (`https://climate-lens(-[a-z0-9]+)?-<team>\.vercel\.app`) |
| `OBSERVATION_CACHE_TTL_HOURS` | `720` | TTL for raw provider series |
| `ANALYSIS_CACHE_TTL_HOURS` | `168` | TTL for derived analyses |
| `RATE_LIMIT_ANALYZE_PER_MINUTE` | `30` | Per-IP limit for `/api/analyze` |
| `RATE_LIMIT_EXPORT_PER_MINUTE` | `10` | Per-IP limit for exports |
| `TRUST_PROXY_HEADERS` | `false` | Use `X-Forwarded-For` for the client IP. Enable only behind a trusted proxy such as Render. |
| `UPSTREAM_TIMEOUT_SECONDS` | `30` | Open-Meteo request timeout |
| `UPSTREAM_MAX_RETRIES` | `2` | Retries on timeouts, transport errors, and 5xx responses. 429 responses are never retried. |
| `ENVIRONMENT` | `development` | Informational |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend, set at build time: the API base URL |

## API

Interactive OpenAPI documentation is served at `/docs`.

| Method and path | Description |
| --- | --- |
| `GET /api/health` | Status, version, algorithm version, cache mode and health, data source, limits |
| `GET /api/regions` | Preset cities (points) and states (boxes) |
| `GET /api/analyze` | Full analysis as JSON |
| `GET /api/export.csv` | Annual indicators as CSV for the same query |
| `GET /api/export.pdf` | PDF report for the same query |

Query parameters, shared by the last three endpoints:

| Parameter | Notes |
| --- | --- |
| `latitude`, `longitude` | A point, **or** ... |
| `south`, `west`, `north`, `east` | ... a box. Each side may be at most 10°; boxes crossing the antimeridian are not supported. |
| `start_year`, `end_year` | From 1940 to the last complete calendar year; the window may span at most 60 years. |
| `label` | Optional. Control characters are stripped and the result is truncated to 80 characters. |
| `hazard` | `heatwave`. Anything else returns `422`. |
| `baseline` | `analysis_period` (default) or `fixed_reference` |
| `reference_start_year`, `reference_end_year` | Defaults 1991 and 2020. Used only with `fixed_reference`; the period must be 10 to 60 years. |

Every error has the shape `{"error": {"code", "message", "details?"}}`, with these status codes:

| Status | Meaning |
| --- | --- |
| 422 | Validation failed |
| 429 | Rate limit exceeded (`Retry-After` header set) |
| 502 | Provider returned a malformed response or rejected the request |
| 503 | Provider is down or its quota is exhausted |
| 504 | Provider timed out |
| 500 | Unexpected error (no stack trace is exposed) |

Example request:

```
GET /api/analyze?latitude=17.385&longitude=78.4867&label=Hyderabad&start_year=1990&end_year=2025
```

The response contains `region`, `period`, `hazard`, `baseline` (including `threshold_c`), `source` (provider, dataset, timezone, retrieval time, grid points), `cache`, `summary`, `annual[]`, `events[]`, `trends` (`heatwave_days`, `event_count`, `mean_tmax`, each with `regression`, `mann_kendall`, and `period_change`), `data_quality`, `insights[]`, `caveats[]`, and `algorithm_version`.

## Methodology

Each item below is either **[Brief]**, a requirement taken from the case-study brief, or **[Assumption]**, a choice made here and documented because the brief does not specify it.

### Data source [Assumption]

- **Provider:** Open-Meteo Historical Weather API, `daily=temperature_2m_max`, `temperature_unit=celsius`, `timezone=auto`. Daily maxima therefore use the location's local calendar day.
- **Underlying data:** ERA5 / ERA5-Land reanalysis, which is model-based and gridded. It is not station data.
- **Spatial meaning:** a point query describes the reanalysis grid cell it falls in, not a whole city.
- **Box queries:** the daily value is the mean of up to a 2x2 grid of cell-centre points inside the box. A day is treated as missing unless every sampled point has a valid value. The grid is capped at 2x2 to stay within the provider's free quota (see [Known limitations](#known-limitations)). It is a coarse sample, not an area-weighted average.

### Missing data and outliers [Assumption]

- The provider series is re-indexed onto a complete calendar from 1 January of the start year to 31 December of the end year.
- Missing dates, nulls, NaN or non-numeric values, and implausible values (outside -60 to 60 °C) are all kept as **missing**. Nothing is interpolated or zero-filled. Each category is counted and reported.
- Duplicate dates keep the first value and are counted.
- Unexpected units, misaligned arrays, or invalid dates cause the whole response to be rejected with a `502`.
- A year is used in trend statistics only if at least 80% of its days are valid. Excluded years are listed in the response, the UI, and the PDF.

### Heatwave definition [Brief]

A heatwave is **at least 3 consecutive valid days** with daily maximum temperature **strictly greater than** the 95th-percentile threshold. Any missing day breaks a run.

### Percentile baseline [Assumption]

- **Method:** `numpy.percentile(..., method="linear")`, which is Hyndman & Fan type 7, applied to all valid daily values in the baseline period. No seasonal (day-of-year) percentile is used, so heatwaves are absolute hot spells for the location.
- **`analysis_period` (default):** the threshold depends on the selected years. Results for different periods use different thresholds and should not be compared directly.
- **`fixed_reference`:** the threshold comes from separate reference years (for example 1991-2020) and is applied to the analysis years. The baseline mode and its years are echoed in every output and are part of the cache key.

### Annual accounting [Assumption]

- An event is counted **once, in the year it starts**.
- Its days are attributed to **the calendar year each day falls in**. An event from 30 December to 3 January adds 2 days to the first year and 3 days to the next.
- A year's **longest event** is the longest contribution any single event makes to that year.
- Events touching the first or last day of the window may be truncated by the window.

### Trend statistics [Brief: regression, rolling averages, Mann-Kendall]

The indicators are annual heatwave days, annual event counts, and annual mean daily maximum temperature.

**Rolling mean.** A trailing 5-year mean, left empty when the window contains an excluded year.

**Linear regression (OLS).**
- Reports the slope (per year and per decade), the intercept, R², and the number of years used.
- Needs at least 3 years. A constant series gives a slope of 0 with R² undefined.
- It describes the observed record; it is not a forecast and not a significance test.

**Mann-Kendall test.**
- Formulas:
  - \(S=\sum_{i<j}\operatorname{sgn}(x_j-x_i)\)
  - \(\operatorname{Var}(S)=\frac{n(n-1)(2n+5)-\sum_g t_g(t_g-1)(2t_g+5)}{18}\), which includes the tie correction
  - \(Z=(S\mp1)/\sqrt{\operatorname{Var}(S)}\), with a continuity correction
  - Two-sided \(p=\operatorname{erfc}(|Z|/\sqrt2)\), with \(\alpha=0.05\)
- Sen's slope is reported alongside.
- Needs at least 4 values. Results with fewer than 10 values are flagged, because the normal approximation is weak at small sample sizes. Missing or invalid values are dropped and counted.
- A constant series has \(\operatorname{Var}(S)=0\), so Z and p are reported as undefined.
- The p-value is checked against hand-computed reference values in `tests/test_mann_kendall.py`.
- **Limitation:** the test assumes independent years. Positive serial autocorrelation inflates false positives. No pre-whitening or modified-variance correction (such as Hamed-Rao or Yue-Wang) is applied.

**Interpretation wording.** Results are described with one of these phrases:
- "Increasing monotonic trend detected, with the significance criterion met."
- "Decreasing monotonic trend detected, with the significance criterion met."
- "Trend direction estimated, but statistical evidence is insufficient at the selected threshold."
- "No statistically detectable monotonic trend under this test."
- "Insufficient data for reliable testing."

A non-significant result is never presented as proof of no trend, and neither method is presented as evidence of causation.

**Percentage change in insights.**
- The mean of the first 5 qualifying years is compared with the mean of the last 5.
- With fewer than 10 years, half the record is used for each period.
- The percentage is omitted, with an explanation, when the early mean is zero.

## Caching

- **`observations` collection:** raw provider series, keyed by sample points, date range, variable, and schema version. TTL is 30 days by default.
- **`analyses` collection:** full responses. The key covers points, years, hazard, percentile, minimum duration, baseline mode and reference years, the completeness rule, the label, and `ALGORITHM_VERSION`. TTL is 7 days. A cached analysis is used only if its algorithm version matches the running code.
- **Fewer provider requests:**
  - Overlapping analysis and reference ranges are fetched in one request.
  - Changing only the label reuses the cached observations.
  - Exports reuse the cached analysis.
- **Expiry:** MongoDB TTL indexes remove expired documents, and reads also re-check `expires_at`.
- **Fallback:** if MongoDB is unreachable at startup, the app uses a process-local LRU+TTL memory cache, and `/api/health` reports which mode is active. If a MongoDB operation fails at runtime, it is treated as a cache miss.
- **Scaling caveat:** the memory cache and the rate limiter are **per process**, so separate instances don't share them. For horizontal scaling, use Redis for a shared cache and a coordinated rate limiter; see [docs/architecture.md](docs/architecture.md).

## Security and performance

**Input handling**
- Strict validation of coordinates, box size, year range and span, reference period, hazard, and label length, with control characters stripped.
- Extra query parameters are rejected.

**Rate limiting:** a per-IP sliding window, configurable, returning `429` with `Retry-After`. Analysis and export requests have separate buckets.

**Calls to Open-Meteo**
- 30 s timeout.
- At most 2 retries with exponential backoff, only on timeouts, transport errors, and 5xx responses.
- A 429 from the provider is never retried.
- Request size is bounded by the 60-year span and the 4-point box grid.

**Outputs**
- CSV cells starting with `= + - @ \t \r` get an apostrophe prefix (formula-injection guard), and filenames are slugified.
- PDF text is XML-escaped, so ReportLab markup in labels is not interpreted.

**HTTP**
- CORS is restricted to `ALLOWED_ORIGINS` (plus the optional `ALLOWED_ORIGIN_REGEX`) and only `GET` is allowed.
- Security headers include `nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy`.
- Error responses never include stack traces.

**Deployment**
- No secrets are committed. `.env` and the confidential brief PDF are git-ignored.
- The frontend is served as a static production build (nginx in Docker, a CDN on Vercel), not by the Vite dev server.
- Authentication is not implemented, because the brief does not require user accounts and all data is public.

## Tests

Run them yourself:

```bash
cd backend && python -m pytest          # 89 tests
cd frontend && npm test                 # 32 tests (Vitest + React Testing Library)
cd frontend && npm run build            # type-check + production build
```

Results recorded on 12 October 2026 (Windows 11, Python 3.14.4, Node 25.9):

| Suite | Result |
| --- | --- |
| Backend `pytest` | **89 passed** |
| Frontend `vitest run` | **32 passed** (4 files) |
| Frontend `tsc -b && vite build` | Passed |
| Frontend `oxlint` | No warnings |
| Live smoke test against the real Open-Meteo API | Passed. Point analyses for Hyderabad (1990-2025) and Delhi (1995-2024) returned complete data, a valid CSV, and a valid 5-page PDF. A Telangana box (2015-2024) sampled 4 grid points with no excluded years. |
| `docker compose config` | Valid |
| `docker compose up --build` | **Not run.** The Docker engine was unavailable (see limitations). |

What the backend tests cover (Open-Meteo is mocked with `respx`, so no network is needed):

- **Heatwave detection:**
  - 2-day runs vs exactly 3-day runs, long events, and multiple events
  - Cooler-day interruptions, missing dates, and missing or implausible values
  - Leap days and events spanning a year boundary
  - Threshold equality
  - Percentile interpolation, repeated values, and empty or single-value datasets
  - Separation of annual event counts from annual heatwave days
- **Regression:** zero-baseline percentage handling, insufficient points, and constant series.
- **Mann-Kendall:** increasing, decreasing, and constant series; ties; missing values; too few points; invalid values; hand-computed p-values; and the effect of alpha.
- **API:**
  - Health and regions endpoints, and valid point, box, and fixed-baseline analyses
  - Validation of coordinates, reversed years, over-long windows, unsupported hazards, conflicting point and box input, and over-long labels
  - Provider 500, timeout, 429, 400, and malformed responses, plus not caching failed fetches
  - Cache hits and misses, rate limits, and CORS
  - CSV headers and content, the formula-injection guard, PDF validity and page numbers, and PDF markup escaping
  - **A cross-check that dashboard JSON, CSV rows, and PDF text agree for the same request**
- **Cache:** MongoDB TTL index, expiry, and failure fallback (with mongomock); memory-cache LRU and TTL.

What the frontend tests cover:
- Rendering of API data, preset selection, and state presets that select boxes
- Map click selection and drawing a box with two clicks
- Debounced manual coordinate entry that never triggers an analysis by itself
- Year validation, the fixed baseline, and loading and disabled states
- The API error banner and Retry
- CSV and PDF downloads that use the displayed analysis, and export failures
- Disabled unsupported hazards
- Superseded-request handling in `useAnalysis`
- Client helpers and selection validation

## Deployment

The live demo was deployed with the steps below, including MongoDB Atlas.

### 1. MongoDB Atlas (free M0 cluster)

1. Create a free M0 cluster at https://cloud.mongodb.com.
2. Create a database user with a strong password.
3. Under **Network Access**, allow the backend host. Render's free tier has no static IPs, so use `0.0.0.0/0` with a strong password, or use a paid static-IP option.
4. Copy the connection string, for example `mongodb+srv://USER:PASS@cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority`.

### 2. Backend on Render (free web service, Docker)

1. Push the repository to GitHub (see below).
2. In Render, choose **New**, then **Blueprint**, and select the repository. `render.yaml` defines `climate-lens-api` with `healthCheckPath: /api/health`. Alternatively, create a web service by hand with root directory `backend` and runtime Docker.
3. Set the secret environment variables:
   - `MONGODB_URI`: the Atlas connection string
   - `ALLOWED_ORIGINS`: the frontend origin, for example `https://climate-lens.vercel.app` (no trailing slash)
4. Deploy, then open `https://<service>.onrender.com/api/health`. It should report `"cache": {"mode": "mongodb", "healthy": true}`.

### 3. Frontend on Vercel

1. Import the repository in Vercel and set the **Root Directory** to `frontend`. The framework is Vite and `vercel.json` is included.
2. Add the environment variable `VITE_API_BASE_URL=https://<service>.onrender.com`.
3. Deploy. Then update `ALLOWED_ORIGINS` on Render to the exact Vercel production URL and redeploy the backend. Vercel also gives every deployment its own URL; `ALLOWED_ORIGIN_REGEX` in `render.yaml` allows those for this project's Vercel team.

Netlify works too: base directory `frontend`, build command `npm run build`, publish directory `dist`, the same environment variable, and a SPA redirect `/* /index.html 200`.

### Service limits and costs

- **Render free tier:** the service sleeps after about 15 minutes idle, so the first request can take around a minute (cold start). The disk is ephemeral and memory is limited.
- **MongoDB Atlas M0:** free with 512 MB of storage. That is plenty for cached series, which are about 200 KB per 30-year point.
- **Open-Meteo free API:** **non-commercial use only**.
  - Limits are 600 calls per minute, 5,000 per hour, 10,000 per day, and 300,000 per month.
  - Requests spanning more than 2 weeks count as multiple calls, so an uncached 30-year point analysis can cost hundreds of call units, and a 4-point box costs about 4 times that.
  - Commercial use needs a paid plan.
  - Attribution (CC BY 4.0) is shown in the UI and the PDF.
- **OpenStreetMap tiles:** allowed for light use with attribution under the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/). Heavier traffic needs a commercial tile provider. OpenTopoMap is the automatic fallback.
- **Vercel Hobby:** free for personal, non-commercial projects.

## Publishing to GitHub

The code is published at https://github.com/Karuturinoushikajay/climate-lens. Vercel and Render redeploy automatically on pushes to `main`. To publish a fork elsewhere:

```bash
git status                      # confirm the case-study PDF, .env, node_modules and .venv are NOT listed
gh repo create <name> --public --source . --remote origin --push
```

The brief asks that it not be published, so `*.pdf` is in `.gitignore`.

## Known limitations

**Docker verification is pending.** On the development machine, Docker Desktop's Linux engine returned HTTP 500 because WSL had no installed distributions, so the Compose stack was never built or run. To fix it:
- Repair Docker Desktop (Troubleshoot, then Reset), or run `wsl --install` and reboot.
- Then run `docker compose up --build`.

The MongoDB code path is covered by `mongomock` tests and has been verified against a real MongoDB Atlas cluster in the live deployment, but not against the Compose `mongo:7` container.

**Data**
- Reanalysis data is not station data.
- A point is one grid cell.
- A box uses at most 4 sampled points, because of the provider quota.
- State boxes are rectangles, not administrative boundaries.

**Thresholds**
- The analysis-period threshold changes with the selected years.
- An annual absolute threshold makes "heatwaves" mostly a pre-monsoon or summer phenomenon. A day-of-year percentile is a common alternative and is not implemented.
- A fixed reference period that overlaps the analysis period introduces some dependence between the two.

**Statistics**
- No autocorrelation correction for Mann-Kendall.
- No multiple-testing correction across the three indicators.
- Regression on count data assumes linear, homoscedastic behaviour.

**Scaling:** the in-memory cache and rate limits are per process.

**Provider quota:** heavy use of uncached multi-decade or box queries can exhaust Open-Meteo's free quota. The API then returns `503 upstream_rate_limited`.

**The year after it ends:** in the first days of January, the previous year may not yet be fully available from the provider. Its missing days are reported, and the year may be excluded from trends.

## Future improvements

- Day-of-year (seasonal) percentile thresholds and an optional Tmin or heat-index co-condition.
- A modified Mann-Kendall test with autocorrelation correction (Hamed-Rao or Yue-Wang pre-whitening), and confidence intervals for Sen's slope.
- Drought (SPI/SPEI) and heavy-rainfall (R95p, Rx1day) hazards behind the existing hazard parameter.
- Area-weighted box averages using the provider's native grid, plus administrative boundary polygons (GeoJSON).
- Redis for a shared cache and rate limiting, and background prefetching of preset regions.
- End-to-end browser tests (Playwright) and visual regression tests for the PDF.

## AI-tool disclosure

This project was built with the help of an **AI coding assistant**, an LLM-based tool working inside the IDE.

- **What the agent did:**
  - Read the brief and drafted the requirements checklist and implementation plan.
  - Wrote most of the backend, frontend, tests, Docker and deployment configuration, and documentation.
  - Ran the test suites, builds, and live API smoke tests, and fixed the failures they exposed.
- **What the agent changed after testing:**
  - Switched the basemap after a CARTO API-key placeholder was observed in the browser.
  - Corrected test expectations.
  - Fixed a lint warning.
- **The developer's role:** reviewing the methodology choices listed under [Methodology](#methodology), the scientific caveats, and the final code. All numbers shown in the app are computed at runtime from Open-Meteo data. Nothing is hard-coded.
- **Verification:** the statistical formulas were checked against hand-computed values in the tests rather than trusted from the model.
