# Climate Lens: Climate Hazard Trend Analyzer

[![CI](https://github.com/Karuturinoushikajay/climate-lens/actions/workflows/ci.yml/badge.svg)](https://github.com/Karuturinoushikajay/climate-lens/actions/workflows/ci.yml)

Climate Lens detects heatwaves, heavy-rainfall events and dry spells (drought) in historical daily weather data and analyses how their frequency, duration, and intensity have changed for a chosen place and period. It was built for the Dygnify Ventures Full-Stack Developer case study.

- **Frontend:** React 19, TypeScript, Vite, Recharts, React Leaflet, Lucide icons
- **Backend:** Python, FastAPI, Pydantic, HTTPX, NumPy, ReportLab
- **Storage:** MongoDB with TTL indexes, falling back to an in-process cache
- **Data:** [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), daily `temperature_2m_max` (heatwave) and `precipitation_sum` (heavy rainfall, drought) from the ECMWF ERA5 reanalysis (`models=era5`, 0.25° grid). The dataset is named in the results header, the CSV metadata and the PDF.

**Live demo:** https://climate-lens-gamma.vercel.app
**API:** https://climate-lens-api.onrender.com/api/health (interactive docs at [/docs](https://climate-lens-api.onrender.com/docs))

The backend is on Render's free tier, which sleeps after 15 idle minutes; a cold start measured on 14 October 2026 took 21 s. A scheduled GitHub Actions job ([`keep-warm.yml`](.github/workflows/keep-warm.yml)) is set to ping `/api/health` every 10 minutes, but GitHub runs schedules on a best-effort basis and in practice ran it only every 4-5 hours (14-15 October 2026), so it does not reliably keep the server awake. If a request takes longer than 3 s, the UI shows "Waking the server, this can take about 30 s".

> **Status, stated honestly**
> - **Implemented and tested:** the full analysis pipeline, the API, CSV and PDF exports, the dashboard, and the map, for all three hazards (heatwave, heavy rainfall, drought). 170 backend tests and 69 frontend tests pass.
> - **Verified locally:** the backend and frontend dev servers, run against the live Open-Meteo API.
> - **Not yet verified:** the Docker Compose stack. Docker Desktop's Linux engine could not start on the development machine because WSL has no distributions installed. The Compose file validates with `docker compose config`, but the containers were not built or run.
> - **Deployed and verified live (12 October 2026):** frontend on Vercel, backend on Render, cache on MongoDB Atlas (free M0). Live checks passed for CORS from the Vercel origin, a Hyderabad 1990-2025 analysis, the CSV download, and the PDF download. `/api/health` reports `"mode": "mongodb"`, and a repeated Delhi 2000-2024 analysis went from a cache miss (3.9 s) to a MongoDB cache hit (1.1 s).

---

## Contents

The seven numbered sections follow the order the brief asks for.

- [Features](#features)
- [1. Setup](#1-setup)
  - [Docker](#docker-mongodb--backend--frontend) · [Local development](#local-development-without-docker) · [Configuration](#configuration) · [Tests](#tests) · [Deployment](#deployment)
- [2. Architecture](#2-architecture)
  - [API](#api) · [Caching](#caching) · [Security and performance](#security-and-performance)
- [3. Data sources](#3-data-sources)
- [4. Hazard logic](#4-hazard-logic)
  - [Heatwave definition](#heatwave-definition) · [Heavy rainfall definition](#heavy-rainfall-definition) · [Drought definition](#drought-definition-dry-spells) · [Why these defaults](#why-these-defaults) · [Percentile baseline](#percentile-baseline) · [Data quality](#data-quality) · [Annual accounting](#annual-accounting) · [Trend statistics](#trend-statistics) · [How results are worded](#how-results-are-worded)
- [5. Assumptions](#5-assumptions)
- [6. Improvements](#6-improvements)
  - [Known limitations](#known-limitations) · [Future improvements](#future-improvements)
- [7. AI-tool disclosure](#7-ai-tool-disclosure)

## Features

**Region selection**
- City search: type any city or place name (at least 2 characters) and pick a match. Results come from the free [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api) (GeoNames data) through the backend, which caches them for 30 days and rate-limits searches to 60 per minute per client. Choosing a result sets the point, the label (for example "Phoenix, Arizona, United States") and the map. It never starts an analysis by itself.
- City presets (Hyderabad, Mumbai, Delhi, Bengaluru, Chennai, Visakhapatnam, Kolkata, Pune, Ahmedabad, Jaipur, Nagpur, Lucknow) are single points.
- State presets (Telangana, Andhra Pradesh, Tamil Nadu, Rajasthan, Maharashtra, Odisha) are approximate rectangles.
- On the map, click once to choose a point, or click two corners to draw a lat-lon box.
- Coordinates and box edges can be typed in manually, and you can set a custom label.

**Hazards:** Heatwave (selected by default), Heavy rainfall, and Drought (dry spells). Each has its own definition, labels, charts, CSV columns and PDF text; see [4. Hazard logic](#4-hazard-logic).

**Configurable definitions:** the settings are shown in the results header ("95th percentile · 3+ days"), the summary card, the CSV and the PDF.
- **Heatwave:** the threshold percentile (90th, 92.5th, 95th, 97.5th or 99th; default 95th) and the minimum number of consecutive hot days (2 to 10; default 3).
- **Heavy rainfall:** the same percentile choices, applied to wet days, and the minimum number of consecutive heavy-rain days (1 to 10; default 1).
- **Drought:** the minimum dry-spell length (5 to 60 days; default 15). A dry day is fixed at below 1 mm, so there is no percentile.

**Baselines:** the percentile threshold comes from the fixed 1991-2020 reference period by default, or optionally from the analysis period itself.

**Dashboard**
- A limitations note directly under the results header (reanalysis is not station data, percentile thresholds are relative to each location, significance is not causation)
- Summary cards
- A data-quality report: days received from the source, missing, implausible, duplicate, interpolated and outlier days, a check that the counts add up, a per-year breakdown, the filled days, and the most extreme flagged days (with "showing 20 of N" when the list is cut off)
- Annual hazard-day and event-count charts, each with a 5-year rolling mean and a linear fit
- An annual Tmax chart with the threshold line (heatwave), or an annual precipitation chart: total and rain on heavy-rain days with the wettest day (heavy rainfall), or total against the baseline normal (drought)
- Data-driven trend interpretation, with the p-value next to every headline change
- A statistics panel with regression and Mann-Kendall results, including tooltips
- A methodology panel, including "Why these defaults?"
- A year-by-year table, with a "Filled" column and a note on events that contain a filled day when gap fill is on
- Sources and limitations

**Exports:** server-generated CSV and PDF reports for exactly the analysis shown on screen, including the hazard settings and the data-quality counts (run totals and per year).

**Robustness**
- Validation, rate limiting, timeouts, and bounded retries
- Uniform JSON errors
- Loading, empty, error, and retry states in the UI, plus a "Waking the server" message for any request slower than 3 s
- Protection against stale results being shown for a different selection

## 1. Setup

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

### Configuration

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
| `RATE_LIMIT_GEOCODE_PER_MINUTE` | `60` | Per-IP limit for city search |
| `GEOCODE_CACHE_TTL_HOURS` | `720` | TTL for cached city-search results |
| `OPEN_METEO_GEOCODING_URL` | `https://geocoding-api.open-meteo.com/v1/search` | Geocoding endpoint |
| `CLIENT_IP_HEADER` | unset | Header holding the client IP, set by the edge proxy (on Render: `cf-connecting-ip`). Only safe if every request passes that proxy. Takes priority over `TRUSTED_PROXY_HOPS`. |
| `TRUSTED_PROXY_HOPS` | unset | Number of proxies in front of the app that append to `X-Forwarded-For`. The client IP is taken that many entries from the **right**, so values a client adds on the left are ignored. `0` uses the TCP peer address. |
| `TRUST_PROXY_HEADERS` | `false` | Legacy switch. When `TRUSTED_PROXY_HOPS` is unset, `true` means "behind Render and Cloudflare": `CLIENT_IP_HEADER=cf-connecting-ip` with 3 `X-Forwarded-For` hops as the fallback. `false` means neither. |
| `UPSTREAM_TIMEOUT_SECONDS` | `30` | Open-Meteo request timeout |
| `UPSTREAM_MAX_RETRIES` | `2` | Retries on timeouts, transport errors, and 5xx responses. 429 responses are never retried. |
| `ENVIRONMENT` | `development` | Informational |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend, set at build time: the API base URL |

### Tests

Run them yourself:

```bash
cd backend && python -m pytest          # 170 tests
cd frontend && npm test                 # 69 tests (Vitest + React Testing Library)
cd frontend && npm run build            # type-check + production build
```

Results recorded on 14 October 2026 (Windows 11, Python 3.14.4, Node 25.9):

| Suite | Result |
| --- | --- |
| Backend `pytest` | **170 passed** |
| Frontend `vitest run` | **69 passed** (5 files) |
| Frontend `tsc -b && vite build` | Passed |
| Frontend `oxlint` | No warnings |
| GitHub Actions [CI](.github/workflows/ci.yml) (Ubuntu, Python 3.12, Node 22, matching the Dockerfiles) | Runs on every push to `main` and on pull requests: backend `pytest`, then frontend lint, tests and build. Passed on its first run. |
| Live smoke test against the real Open-Meteo API | Passed. Point analyses for Hyderabad (1990-2025) and Delhi (1995-2024) returned complete data, a valid CSV, and a valid 5-page PDF. A Telangana box (2015-2024) sampled 4 grid points with no excluded years. Heavy rainfall for Mumbai (1990-2024) and drought for Jaipur (1990-2024) returned complete precipitation data, counts that add up, a valid CSV and a valid PDF. |
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
- **Heavy rainfall and drought:**
  - The wet-day threshold uses only days of at least 1 mm, and a heavy-rain day must be strictly above it
  - The 1 mm dry-day boundary, negative rainfall marked implausible, and a missing day never counted as dry
  - The longest dry run (CDD) split across a year boundary, annual totals, the baseline normal, and rain on event days
  - Both hazards through the API, a custom dry-spell length, per-hazard duration bounds, `fill_gaps` rejected for precipitation, percentile left out of the drought cache key, observations cached per variable, and a wrong precipitation unit from the provider returning `502`
  - CSV columns and PDF text for both hazards
- **Data quality:** the counts always add up (received = valid + null + implausible; calendar = valid + missing + implausible), with and without gap fill; days received never below valid days or negative, including a single year inside the reference period; gap fill off by default; single-day gaps filled and flagged, two-day gaps and edge gaps left missing; interpolated days excluded from the threshold and completeness; per-year interpolated, duplicate and implausible counts; outliers flagged but kept; small windows and zero-MAD windows skipped.
- **Regression:** zero-baseline percentage handling, insufficient points, and constant series.
- **Mann-Kendall:** increasing, decreasing, and constant series; ties; missing values; too few points; invalid values; hand-computed p-values; the effect of alpha; and the Hamed-Rao adjustment.
- **Insights:** every headline change (percentage, slope, mean Tmax change) carries "statistically significant" or "not statistically significant" with its p-value.
- **API:**
  - Health and regions endpoints, and valid point, box, and fixed-baseline analyses
  - Configurable percentile and minimum duration (thresholds, event lengths, definitions and cache keys follow the request)
  - Validation of coordinates, reversed years, reversed reference years, over-long windows, unsupported hazards, percentiles outside the allowed set, minimum durations outside each hazard's range, conflicting point and box input, and over-long labels
  - Provider 500, timeout, 429, 400, and malformed responses, plus not caching failed fetches
  - Cache hits and misses (including `fill_gaps` as a separate cache key), rate limits (spoofed X-Forwarded-For ignored, CF-Connecting-IP used when the forwarded chain varies, IPv6 grouped by /64, rate-limit headers, a limit shared by two app instances through MongoDB, and fallback when the store fails), and CORS
  - CSV headers and content (hazard settings, run and per-year data-quality counts), the formula-injection guard, PDF validity, page numbers, hazard labels and data-quality section, and PDF markup escaping
  - **A cross-check that dashboard JSON, CSV rows, and PDF text agree for the same request**
  - City search: parsing, empty results, case-insensitive caching, skipping results without valid coordinates, validation, provider failures (not cached), and its rate limit
- **Cache:** MongoDB TTL index, expiry, and failure fallback (with mongomock); memory-cache LRU and TTL.

What the frontend tests cover:
- Rendering of API data, preset selection, and state presets that select boxes
- Map click selection, drawing a box with two clicks, and re-measuring the map when the mode changes
- Debounced manual coordinate entry that never triggers an analysis by itself
- Year validation, reversed reference years (ordering error only), the fixed baseline, and loading and disabled states
- Percentile and minimum-days controls: values sent, results labelled, out-of-range days rejected
- The gap-fill checkbox (off by default, sent only when ticked), the "Filled" column and filled-event note, and the data-quality report (days received, the accounting check, "showing 2 of 22" for a cut-off outlier list)
- The "Waking the server" message after 3 s and its removal when the response arrives
- The "Why these defaults?" note
- The limitations note and its link to the sources list
- The API error banner and Retry
- CSV and PDF downloads that use the displayed analysis, and export failures
- Hazard switching: per-hazard duration defaults and bounds, the drought dry-day rule replacing the percentile, gap fill disabled for precipitation, and heavy-rainfall and drought results labelled in mm
- City search: choosing a result by mouse or keyboard sets the coordinates, label and map; no request under 2 characters; no-match and error messages
- Superseded-request handling in `useAnalysis`
- Client helpers, selection validation, and chart year ticks

### Deployment

The live demo was deployed with the steps below, including MongoDB Atlas.

**MongoDB Atlas (free M0 cluster)**

1. Create a free M0 cluster at https://cloud.mongodb.com.
2. Create a database user with a strong password.
3. Under **Network Access**, allow the backend host. Render's free tier has no static IPs, so use `0.0.0.0/0` with a strong password, or use a paid static-IP option.
4. Copy the connection string, for example `mongodb+srv://USER:PASS@cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority`.

**Backend on Render (free web service, Docker)**

1. Push the repository to GitHub (see below).
2. In Render, choose **New**, then **Blueprint**, and select the repository. `render.yaml` defines `climate-lens-api` with `healthCheckPath: /api/health`. Alternatively, create a web service by hand with root directory `backend` and runtime Docker.
3. Set the secret environment variables:
   - `MONGODB_URI`: the Atlas connection string
   - `ALLOWED_ORIGINS`: the frontend origin, for example `https://climate-lens.vercel.app` (no trailing slash)
4. Deploy, then open `https://<service>.onrender.com/api/health`. It should report `"cache": {"mode": "mongodb", "healthy": true}`.

**Frontend on Vercel**

1. Import the repository in Vercel and set the **Root Directory** to `frontend`. The framework is Vite and `vercel.json` is included.
2. Add the environment variable `VITE_API_BASE_URL=https://<service>.onrender.com`.
3. Deploy. Then update `ALLOWED_ORIGINS` on Render to the exact Vercel production URL and redeploy the backend. Vercel also gives every deployment its own URL; `ALLOWED_ORIGIN_REGEX` in `render.yaml` allows those for this project's Vercel team.

**Keeping the free backend awake.** [`.github/workflows/keep-warm.yml`](.github/workflows/keep-warm.yml) is scheduled every 10 minutes and requests `/api/health`, which touches neither Open-Meteo nor the rate limits. GitHub runs schedules on a best-effort basis and disables them after 60 days without repository activity; on 14-15 October 2026 it actually ran only every 4-5 hours, so it does not keep the server awake on its own. Its retries span about 4 minutes, so a brief Render restart does not fail the run. one always-on free service uses about 744 of Render's 750 free instance hours a month. A free external monitor such as UptimeRobot on the same URL is a more punctual alternative.

Netlify works too: base directory `frontend`, build command `npm run build`, publish directory `dist`, the same environment variable, and a SPA redirect `/* /index.html 200`.

**Publishing to GitHub.** The code is published at https://github.com/Karuturinoushikajay/climate-lens. Vercel redeploys automatically on pushes to `main`; the Render service is redeployed manually. To publish a fork elsewhere:

```bash
git status                      # confirm the case-study PDF, .env, node_modules and .venv are NOT listed
gh repo create <name> --public --source . --remote origin --push
```

The brief asks that it not be published, so `*.pdf` is in `.gitignore`.

## 2. Architecture

```mermaid
flowchart LR
  UI[React dashboard] -->|"GET /api/*"| API[FastAPI routes]
  API --> RL[Rate limiter]
  API --> SVC[AnalysisService]
  API --> GEO[GeocodingService]
  SVC --> CACHE[Cache store]
  GEO --> CACHE
  RL --> CACHE
  CACHE --> MONGO[(MongoDB TTL)]
  CACHE --> MEM[In-memory fallback]
  SVC --> WX[Open-Meteo client]
  GEO --> WX
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
│   │   ├── services/               # weather.py (Open-Meteo), geocoding.py, analysis.py, regions.py
│   │   ├── config.py, errors.py, main.py
│   ├── tests/                      # pytest: unit, API, integration (weather API mocked)
│   ├── Dockerfile, requirements*.txt, pytest.ini
├── frontend/
│   ├── src/                        # App, components/, api/, hooks/, state/, utils/, test/
│   ├── Dockerfile, nginx.conf, vercel.json
├── docs/                           # architecture.md, requirements-traceability.md
├── docker-compose.yml, render.yaml, .env.example
```

Tests live next to each application (`backend/tests`, `frontend/src/**/*.test.ts(x)`) rather than in a top-level `tests/` folder, so each toolchain finds its own tests.

### API

Interactive OpenAPI documentation is served at `/docs`.

| Method and path | Description |
| --- | --- |
| `GET /api/health` | Status, version, algorithm version, cache mode and health, data source, limits |
| `GET /api/regions` | Preset cities (points) and states (boxes) |
| `GET /api/geocode?name=Phoenix&count=5` | City search (Open-Meteo Geocoding, cached). `name` needs at least 2 characters; `count` is 1-10. No match returns an empty `results` list, not an error. |
| `GET /api/analyze` | Full analysis as JSON |
| `GET /api/export.csv` | Annual indicators and data-quality counts as CSV for the same query |
| `GET /api/export.pdf` | PDF report for the same query |

Query parameters, shared by the last three endpoints:

| Parameter | Notes |
| --- | --- |
| `latitude`, `longitude` | A point, **or** ... |
| `south`, `west`, `north`, `east` | ... a box. Each side may be at most 10°; boxes crossing the antimeridian are not supported. |
| `start_year`, `end_year` | From 1940 to the last complete calendar year; the window may span at most 60 years. |
| `label` | Optional. Control characters are stripped and the result is truncated to 80 characters. |
| `hazard` | `heatwave` (default), `heavy_rainfall` or `drought`. Anything else returns `422`. |
| `percentile` | Threshold percentile: `90`, `92.5`, `95` (default), `97.5` or `99`. Anything else returns `422`. Used by heatwave and heavy rainfall; ignored for drought. |
| `min_duration_days` | Minimum consecutive qualifying days for an event. Heatwave 2 to 10 (default 3), heavy rainfall 1 to 10 (default 1), drought 5 to 60 (default 15). Outside the range returns `422`. |
| `fill_gaps` | `false` (default) or `true`. Heatwave only: when true, isolated one-day gaps are filled and flagged; see [Data quality](#data-quality). With a precipitation hazard, `true` returns `422`, because rainfall gaps are never interpolated. |
| `baseline` | `fixed_reference` (default) or `analysis_period` |
| `reference_start_year`, `reference_end_year` | Defaults 1991 and 2020. Used only with `fixed_reference`; start must not be after end, and the period must be 10 to 60 years. |

Every error has the shape `{"error": {"code", "message", "details?"}}`, with these status codes:

| Status | Meaning |
| --- | --- |
| 422 | Validation failed |
| 429 | Rate limit exceeded (`Retry-After` header set). Every rate-limited endpoint also returns `X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset` (seconds). |
| 502 | Provider returned a malformed response or rejected the request |
| 503 | Provider is down or its quota is exhausted |
| 504 | Provider timed out |
| 500 | Unexpected error (no stack trace is exposed) |

Example request:

```
GET /api/analyze?latitude=17.385&longitude=78.4867&label=Hyderabad&start_year=1990&end_year=2025&percentile=90&min_duration_days=2
GET /api/analyze?latitude=19.076&longitude=72.8777&label=Mumbai&start_year=1990&end_year=2024&hazard=heavy_rainfall
GET /api/analyze?latitude=26.9124&longitude=75.7873&label=Jaipur&start_year=1990&end_year=2024&hazard=drought&min_duration_days=30
```

The response contains `region`, `period`, `hazard` (`type`, `name`, `variable`, `units`, `percentile`, `min_duration_days`, definition, and display `labels`), `baseline` (including `threshold_value` with `threshold_units`; `threshold_c` for heatwave; `normal_annual_total_mm` for precipitation hazards), `source` (provider, dataset, timezone, retrieval time, grid points), `cache`, `summary`, `annual[]` (including per-year `missing_days`, `interpolated_days`, `duplicate_dates`, `implausible_days` and `outlier_days`, plus `total_mm`, `max_daily_mm`, `event_total_mm` and `percent_of_normal` for precipitation hazards), `events[]`, `trends` (`heatwave_days`, `event_count`, `mean_tmax`, each with `regression`, `mann_kendall`, and `period_change`), `data_quality`, `insights[]`, `caveats[]`, and `algorithm_version`.

The trend keys keep their original names for every hazard, so clients need only one schema: `heatwave_days` holds the hazard's annual days (heavy-rain days or dry-spell days), and `mean_tmax` holds the third indicator, which is annual total precipitation (mm) for the precipitation hazards. Each trend block carries its own `indicator` name and units.

`data_quality` holds `analysis` and `reference` blocks (calendar, valid, missing, null, implausible, duplicate, interpolated and outlier day counts, plus completeness), `gap_fill` (`off` or `single-day linear`), `outlier_method`, `outlier_dates` (up to 20 most extreme flagged days with their value and robust z-score), `min_year_completeness` and `insufficient_years`.

### Caching

- **`observations` collection:** raw provider series, keyed by sample points, date range, variable, model and schema version. TTL is 30 days by default.
- **`analyses` collection:** full responses. The key covers points, years, hazard, percentile, minimum duration, gap fill, baseline mode and reference years, the completeness rule, the label, and `ALGORITHM_VERSION`. TTL is 7 days. A cached analysis is used only if its algorithm version matches the running code.
- **`places` collection:** city-search results, keyed case-insensitively. TTL is 30 days.
- **`rate_limits` collection:** shared rate-limit windows (see below).
- **Fewer provider requests:**
  - Overlapping analysis and reference ranges are fetched in one request.
  - Changing only the label, percentile, minimum duration or gap fill reuses the cached observations. Heavy rainfall and drought share the cached precipitation series.
  - Exports reuse the cached analysis.
- **Expiry:** MongoDB TTL indexes remove expired documents, and reads also re-check `expires_at`.
- **Fallback:** if MongoDB is unreachable at startup, the app uses a process-local LRU+TTL memory cache, and `/api/health` reports which mode is active. If a MongoDB operation fails at runtime, it is treated as a cache miss.
- **Scaling caveat:** the memory cache is **per process**. With MongoDB configured, the rate limiter is shared; without it, the limiter is also per process. See [docs/architecture.md](docs/architecture.md).

### Security and performance

**Input handling**
- Strict validation of coordinates, box size, year range and span, reference period, hazard, percentile, minimum duration, and label length, with control characters stripped.
- Extra query parameters are rejected.

**Rate limiting:** a per-IP 60-second sliding window, configurable, returning `429` with `Retry-After`. Analysis, export and city-search requests have separate buckets.
- **Shared store:** with MongoDB configured, hit times live in a `rate_limits` collection (TTL-indexed). Each request is checked and recorded in one atomic update, so the limit holds across several instances, overlapping deploys and restarts. If MongoDB fails, that request falls back to the per-process limiter. `/api/health` reports the scope in `limits.rate_limits_scope`.
- **Client identity:** on Render the client is taken from Cloudflare's `CF-Connecting-IP` header (`CLIENT_IP_HEADER`), which Cloudflare overwrites on every request, so a client cannot choose its own identity. Counting a fixed number of entries in `X-Forwarded-For` proved unreliable there, because the number of entries Render adds differs between network paths; it remains only as a fallback (`TRUSTED_PROXY_HOPS`). IPv6 clients are grouped by their /64 network, because many rotate temporary addresses inside it.
- **Visibility:** every rate-limited response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset`.

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

## 3. Data sources

| Source | Used for | Terms |
| --- | --- | --- |
| [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), ECMWF ERA5 reanalysis (Copernicus) | Daily maximum 2 m temperature and daily precipitation total, 1940 to the last complete year | CC BY 4.0, free for non-commercial use |
| [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api) (GeoNames) | City and place search | CC BY 4.0, free for non-commercial use |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) tiles, with OpenTopoMap as fallback | Basemap only; no analysis input | ODbL data, [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) |

**Weather request.** `daily=temperature_2m_max` with `temperature_unit=celsius` (heatwave) or `daily=precipitation_sum` with `precipitation_unit=mm` (heavy rainfall, drought), plus `models=era5` and `timezone=auto`, so daily values use the location's local calendar day. The returned unit is checked, and anything unexpected is rejected with a `502`. ERA5 is pinned explicitly rather than using Open-Meteo's `best_match`, which blends ERA5-Land and other models, so the dataset is the same for every year and every query. The model is part of the cache key.

**What the numbers represent.** ERA5 is a reanalysis: a weather model constrained by historical observations and gridded at 0.25° (roughly 28 km). It is not weather-station data, and it smooths local extremes, so absolute temperatures can differ from a nearby station. A point query describes the grid cell it falls in, not a whole city.

**Box queries.** The daily value is the mean of up to a 2x2 grid of cell-centre points inside the box. A day is treated as missing unless every sampled point has a valid value. The grid is capped at 2x2 to stay within the provider's free quota. It is a coarse sample, not an area-weighted average.

**Service limits and costs**
- **Open-Meteo free API:** **non-commercial use only**.
  - Limits are 600 calls per minute, 5,000 per hour, 10,000 per day, and 300,000 per month.
  - Requests spanning more than 2 weeks count as multiple calls, so an uncached 30-year point analysis can cost hundreds of call units, and a 4-point box costs about 4 times that.
  - Commercial use needs a paid plan.
  - Attribution (CC BY 4.0) is shown in the UI and the PDF.
- **OpenStreetMap tiles:** allowed for light use with attribution. Heavier traffic needs a commercial tile provider. OpenTopoMap is the automatic fallback.
- **Render free tier:** the service sleeps after about 15 minutes idle, so the first request can take around a minute (cold start). The disk is ephemeral and memory is limited.
- **MongoDB Atlas M0:** free with 512 MB of storage. That is plenty for cached series, which are about 200 KB per 30-year point.
- **Vercel Hobby:** free for personal, non-commercial projects.

## 4. Hazard logic

Each item below is either **[Brief]**, a requirement taken from the case-study brief, or **[Assumption]**, a choice made here; every assumption is also collected in [5. Assumptions](#5-assumptions).

### Heatwave definition

**[Brief]** A heatwave is **at least N consecutive valid days** with daily maximum temperature **strictly greater than** the P-th percentile threshold. The brief's example is N = 3 and P = 95, which are the defaults.

**[Assumption]** Both are configurable within fixed bounds: P is one of 90, 92.5, 95, 97.5 or 99, and N is 2 to 10. Other values return `422`, so every result corresponds to a definition that is stated in the output. The chosen P and N appear in the results header, the summary card, the CSV metadata (as separate rows and in the threshold label), the PDF, and the cache key.

A missing day breaks a run, unless the optional single-day gap fill is on (see [Data quality](#data-quality)).

### Heavy rainfall definition

**[Assumption]** Modelled on the ETCCDI R95p index. Variable: daily precipitation total (`precipitation_sum`, mm).
- **Wet day:** at least 1 mm. The threshold is the P-th percentile of the **wet days** in the baseline period (same percentile method and baseline modes as heatwave). Dry days are left out because they are the majority in most climates and would pull the percentile down to a trivial amount of rain.
- **Heavy-rain day:** precipitation **strictly greater than** the threshold.
- **Event:** at least N consecutive heavy-rain days. P is one of 90, 92.5, 95, 97.5 or 99 (default 95); N is 1 to 10 (default 1).
- **Per year:** heavy-rain days, events, longest run, annual total, wettest day, rain on heavy-rain event days, and the annual total as a percentage of the baseline normal.

### Drought definition (dry spells)

**[Assumption]** Modelled on the ETCCDI CDD (consecutive dry days) index. Variable: daily precipitation total (mm).
- **Dry day:** **below 1 mm**. This is a fixed rule, so no percentile is used.
- **Dry spell:** at least N consecutive dry days, with N from 5 to 60 (default 15).
- **Per year:** dry spells, dry-spell days, the longest dry run in the year (CDD, reported whatever its length, so it is defined even in years with no qualifying spell), annual total, wettest day, and the annual total as a percentage of the baseline normal.
- **Baseline normal:** the mean annual total over the baseline years that meet the completeness rule (1991-2020 by default).
- **What it is not:** a dry spell is a rainfall indicator, not a declared drought. Long dry spells are normal in a dry season (for example in India outside the monsoon), so the useful signal is the change against the baseline, not the raw count. Standardised indices (SPI, SPEI) are not used.

**Both precipitation hazards:** a missing day breaks a run and is **never treated as dry or as zero rain**. Gap fill is not available, and outlier screening is not applied, because rainfall is highly skewed with many zero days and genuine extremes would be flagged. Values outside 0 to 2000 mm/day are implausible and counted as missing.

### Why these defaults

- **95th percentile.** Keeps hot days rare (about 18 a year in the reference climate), so events describe extremes rather than ordinary summer heat. It is also the brief's example. The 90th percentile is common in the heatwave literature, which is why it is one of the selectable options.
- **3 consecutive days.** A common minimum duration in heatwave definitions and the brief's example. It separates sustained heat, which is what drives health and infrastructure impacts, from single hot days.
- **1991-2020 baseline.** The current WMO 30-year climate normal. A fixed baseline gives every analysis period the same threshold, so a 1966-1970 run and a 2015-2024 run can be compared directly.
- **What these defaults give up.** One annual threshold is simple and transparent but not seasonal, so heatwaves are mostly a pre-monsoon or summer phenomenon; a day-of-year threshold is listed under [Future improvements](#future-improvements).
- **Heavy rainfall, 95th percentile of wet days.** The standard R95p definition used in ETCCDI climate-extremes work, so results are comparable with published studies.
- **Heavy rainfall, 1 day.** A single very wet day already causes flooding, and multi-day heavy rain is rare at the 95th percentile; N can be raised to look for persistent events.
- **Drought, 1 mm dry day.** The ETCCDI convention, which also avoids counting drizzle and reanalysis noise as rain.
- **Drought, 15 days.** Long enough to describe a meaningful dry spell for crops and water supply, short enough to occur in most years; the per-year longest dry run (CDD) is reported independently of N.

The same note appears in the UI under "Why these defaults?" in the methodology panel.

### Percentile baseline

**[Assumption]**
- **Method:** `numpy.percentile(..., method="linear")`, which is Hyndman & Fan type 7, applied to all **observed** daily values in the baseline period. Interpolated days are never used. No seasonal (day-of-year) percentile is used, so heatwaves are absolute hot spells for the location.
- **`fixed_reference` (default, 1991-2020):** the threshold comes from the WMO climate-normal reference years and is applied to the analysis years, so results for different analysis periods share one threshold and can be compared. The reference years can be changed.
- **`analysis_period`:** the threshold depends on the selected years. Results for different periods use different thresholds and should not be compared directly.
- The baseline mode and its years are echoed in every output and are part of the cache key.

### Data quality

**[Assumption]** Every run reports its data quality in the API (`data_quality` and per-year fields in `annual[]`), the UI (data-quality report), the CSV (metadata rows and per-year columns) and the PDF (summary table and per-year table).

- **Calendar alignment:** the provider series is re-indexed onto a complete calendar from 1 January of the start year to 31 December of the end year.
- **Counts that add up.** "Days received" is the number of distinct dates the source returned inside the window (duplicate rows and dates outside the window are not counted), so it can never be negative or below the valid days. Two identities hold for every run and are checked in code: **received = valid + null + implausible**, and **calendar days = valid + missing (absent + null) + implausible**. The check is shown as a line in the data-quality panel, as an "Accounting check" row in the CSV and the PDF, and as `accounting_ok` / `accounting` in the API. Interpolated days are a subset of the missing and implausible days, not an extra category.
- **Missing:** dates absent from the provider, nulls, NaN or non-numeric values, and implausible values (outside -60 to 60 °C for temperature, 0 to 2000 mm for daily precipitation) all count as missing. Each category is counted separately. A missing temperature is **never** replaced with zero.
- **Duplicates:** duplicate dates keep the first value and are counted, in total and per year.
- **Gap fill (heatwave only, off by default):** with `fill_gaps=true` (the "Fill single-day gaps" checkbox), an isolated one-day gap between two observed days is set to the mean of its neighbours. Gaps of two or more days, and gaps at the start or end of the window, are left missing. Filled days are flagged `interpolated` and counted, in total and per year. They can complete a heatwave run, but they never enter the percentile threshold, completeness, or the annual mean and maximum. A caveat is added to the results whenever gap fill is on, and it has its own cache key. Filled days are visible wherever results appear: a "Filled" column in the year table, a note naming the heatwave events that contain a filled day (each event carries `filled_days`), the list of filled dates with their value and original flag (panel, CSV rows, PDF), and method text in the PDF that states the fill rule instead of "any missing day breaks the run".
- **Outliers (heatwave only; flagged, not removed):** each observed value is compared with all observed values within ±15 calendar days of the same date across the analysis period. The robust z-score is \(z = 0.6745\,(x-\tilde{x})/\mathrm{MAD}\); days with \(|z| > 4\) are flagged and counted, and the 20 most extreme are listed with their date, value and z. When more are flagged, the panel, CSV and PDF say so ("showing 20 of 22"). Windows with fewer than 30 values or zero MAD are skipped. Outliers stay in the analysis because genuine heat extremes are also unusual; the flag is for review.
- **Rejected responses:** unexpected units, misaligned arrays, or invalid dates cause the whole response to be rejected with a `502`.
- **Completeness rule:** a year is used in trend statistics only if at least 80% of its days have an observed value. Excluded years are listed in the response, the UI, and the PDF.

### Annual accounting

**[Assumption]**
- An event is counted **once, in the year it starts**.
- Its days are attributed to **the calendar year each day falls in**. An event from 30 December to 3 January adds 2 days to the first year and 3 days to the next.
- A year's **longest event** is the longest contribution any single event makes to that year.
- Events touching the first or last day of the window may be truncated by the window.

### Trend statistics

**[Brief: regression, rolling averages, Mann-Kendall]** The indicators are annual hazard days, annual event counts, and a third indicator: annual mean daily maximum temperature for heatwave, or annual total precipitation for heavy rainfall and drought.

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
- **Serial-correlation adjustment (Hamed & Rao 1998).** The series is detrended with Sen's slope and ranked; rank autocorrelations significant at \(\alpha\) are used to compute \(n/n^*=1+\frac{2}{n(n-1)(n-2)}\sum_k (n-k)(n-k-1)(n-k-2)\rho_k\), floored at 1 so the adjustment can only make the test more conservative. \(\operatorname{Var}(S)\) is multiplied by this factor. **The verdict uses the adjusted p-value.** The unadjusted Z and p are reported alongside for comparison.
- Sen's slope is reported with a \(1-\alpha\) confidence interval (Gilbert 1987) built from the adjusted variance.
- Needs at least 4 values. Results with fewer than 10 values are flagged, because the normal approximation is weak at small sample sizes. Missing or invalid values are dropped and counted.
- A constant series has \(\operatorname{Var}(S)=0\), so Z and p are reported as undefined.
- The p-value is checked against hand-computed reference values in `tests/test_mann_kendall.py`.

**Percentage change in insights.**
- The mean of the first 5 qualifying years is compared with the mean of the last 5.
- With fewer than 10 years, half the record is used for each period.
- The percentage is omitted, with an explanation, when the early mean is zero.

### How results are worded

Mann-Kendall verdicts use one of these phrases:
- "Increasing monotonic trend detected, with the significance criterion met."
- "Decreasing monotonic trend detected, with the significance criterion met."
- "Trend direction estimated, but statistical evidence is insufficient at the selected threshold."
- "No statistically detectable monotonic trend under this test."
- "Insufficient data for reliable testing."

**Every headline change is hedged.** The percentage change in heatwave days, the fitted slope, and the change in mean daily maximum temperature each carry the adjusted Mann-Kendall result for the same indicator, for example:

- "... were 56% lower than in 1990-1994 (7.2) (not statistically significant, p = 0.67 after serial-correlation adjustment)."
- "... (statistically significant, p = 0.01; an association in this record, not proof of a long-term trend)."

A non-significant result is never presented as proof of no trend, and neither method is presented as evidence of causation. The UI shows a short limitations note under the results header (reanalysis is not station data; percentile thresholds are relative to each location; significance is not causation) that links to the full "Sources & limitations" list.

## 5. Assumptions

Everything the brief leaves open, in one place:

| Area | Assumption | Why |
| --- | --- | --- |
| Dataset | ERA5 via Open-Meteo, pinned with `models=era5` | Free, global, back to 1940, and consistent across years |
| Spatial unit | A point is one 0.25° grid cell; a box is the mean of up to 4 sampled cells | Stays within the free provider quota; stated in every output |
| Day boundary | Local calendar day (`timezone=auto`) | Daily maxima match how people experience a day |
| Threshold | One annual (not day-of-year) percentile, Hyndman & Fan type 7 | Heatwaves are absolute hot spells for the location |
| Percentile and duration | Defaults 95th and 3 days; P in {90, 92.5, 95, 97.5, 99}, N from 2 to 10 | Brief's example as default; bounded choices keep results interpretable |
| Baseline | Fixed 1991-2020 reference by default | WMO climate normal; makes different analysis periods comparable |
| Comparison | Strictly greater than the threshold | A day at exactly the threshold is not "above" it |
| Missing data | Missing breaks a run; never zero-filled | Avoids inventing or hiding heat |
| Gap fill | Off by default; when on, only isolated single days, flagged and kept out of the threshold | Lets users test sensitivity without silently changing results |
| Outliers | Robust z-score per time of year, \|z\| > 4, flagged but kept | Genuine extremes must not be deleted; suspicious values must be visible |
| Plausible range | -60 to 60 °C | Outside the recorded range of Earth surface temperatures |
| Completeness | A year needs 80% observed days to enter trend statistics | Prevents partial years from biasing trends |
| Event year | Counted once in the start year; days attributed to the year they fall in | Event counts and day totals both add up across years |
| Trend test | Mann-Kendall with Hamed-Rao adjustment, α = 0.05, no multiple-testing correction | Robust to non-normal counts and serial correlation; the missing correction is stated |
| Percentage change | First 5 vs last 5 qualifying years | Less sensitive to single unusual years than endpoints |
| Hazards | Heatwave, heavy rainfall (R95p-style) and drought as dry spells (CDD-style) | Simple, published ETCCDI-style definitions that work from one daily variable |
| Wet and dry day | Wet day at least 1 mm; dry day below 1 mm | ETCCDI convention; ignores drizzle and reanalysis noise |
| Precipitation data | Plausible range 0 to 2000 mm/day; no gap fill; no outlier screening; missing never counted as dry | Rainfall is skewed and intermittent, so filling or screening would invent or remove real events |

## 6. Improvements

### Known limitations

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

**Precipitation**
- Reanalysis smooths local convective downpours, so heavy-rainfall amounts and counts are likely underestimated compared with rain gauges.
- Dry spells measure rainfall only. They ignore temperature, evaporation and soil moisture, so they are not a drought declaration; SPI and SPEI are not implemented.
- In strongly seasonal climates, most dry-spell days fall in the normal dry season.

**Statistics**
- The Hamed-Rao adjustment depends on autocorrelation estimates, which are uncertain for short records.
- No multiple-testing correction across the three indicators (stated in the UI and insights).
- Regression on count data assumes linear, homoscedastic behaviour.
- The outlier rule needs at least 30 values per ±15-day window, so it is skipped for very short records.

**Scaling:** the in-memory cache is per process. Rate limits are shared only when MongoDB is configured.

**Provider quota:** heavy use of uncached multi-decade or box queries can exhaust Open-Meteo's free quota. The API then returns `503 upstream_rate_limited`.

**The year after it ends:** in the first days of January, the previous year may not yet be fully available from the provider. Its missing days are reported, and the year may be excluded from trends.

### Future improvements

- Day-of-year (seasonal) percentile thresholds and an optional Tmin or heat-index co-condition.
- Field significance or false-discovery-rate control across indicators and regions.
- Standardised drought indices (SPI, SPEI) and further rainfall indices (Rx1day, Rx5day trends) alongside the current dry-spell and R95p-style hazards.
- Area-weighted box averages using the provider's native grid, plus administrative boundary polygons (GeoJSON).
- Comparison against station records (for example GHCN-Daily) where a station is close to the grid cell.
- Redis for a lower-latency shared cache and rate limiter, and background prefetching of preset regions.
- End-to-end browser tests (Playwright) and visual regression tests for the PDF.

## 7. AI-tool disclosure

This project was built with the help of an AI coding assistant inside the IDE. I used it to scaffold the code, write tests, and debug deployment issues. I chose the heatwave definition, the 1991–2020 baseline and the ERA5 dataset, decided the data-quality rules, reviewed every change, deployed the services, and verified the results against the brief.

- **What the agent did:**
  - Read the brief and drafted the requirements checklist and implementation plans.
  - Ran the test suites, builds, browser checks and live API smoke tests, and fixed the failures they exposed.
- **What the agent changed after testing:**
  - Switched the basemap after a CARTO API-key placeholder was observed in the browser.
  - Reworked the rate limiter after live tests showed it was not counting requests behind Render's proxy.
  - Fixed the map's blank strip after switching to box mode and moved the charts to a numeric year axis without animation, after checking both in the browser.
  - Corrected test expectations and fixed lint warnings.
- **The developer's role:** choosing the scope and priorities, deciding the methodology questions (for example, that gap fill stays opt-in and that outliers are flagged rather than removed), reviewing the scientific caveats and the final code, and deploying the services. All numbers shown in the app are computed at runtime from Open-Meteo data. Nothing is hard-coded.
- **Verification:** the statistical formulas were checked against hand-computed values in the tests rather than trusted from the model.
