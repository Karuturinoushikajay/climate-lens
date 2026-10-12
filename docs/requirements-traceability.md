# Requirements traceability

The case-study brief is confidential and is not committed to this repository. The requirements below paraphrase it.

- **Source A** marks a requirement from the Dygnify case-study brief.
- **Source E** marks an engineering improvement added beyond the brief. These come from the project's master prompt or from design decisions.

Backend test paths are relative to `backend/tests/`. Frontend test paths are relative to `frontend/src/`.

## Core features

| # | Requirement | Source | Implementation | Tests |
| --- | --- | --- | --- | --- |
| 1 | Select a region: city, state, or custom lat-lon box | A | City presets are points and state presets are approximate boxes (`app/services/regions.py`). Box handling is in `AnalysisQuery` (`app/models/schemas.py`) and `sample_points` (`app/services/analysis.py`). The UI uses `ControlsPanel.tsx` and `MapPanel.tsx`. | `test_api.py::test_regions`, `test_box_query_samples_grid`, `test_box_validation`; `App.test.tsx` state-preset and box-mode tests |
| 2 | Heatwave is the hazard type and is selected by default | A | `hazard` defaults to `heatwave`. Other hazards are rejected with `422`. The UI shows Drought and Heavy rainfall as disabled options. | `test_api.py::test_validation_errors[hazard]`; `App.test.tsx` "unsupported hazards are visible but disabled" |
| 3 | Choose a time range | A | `start_year` and `end_year`, limited to 1940 through the last complete year, with a maximum span of 60 years. | `test_validation_errors`; `selection.test.ts`; `App.test.tsx` year-change test |
| 4 | Time-series plots of hazard frequency and intensity | A | `TrendCharts.tsx` shows annual heatwave days, annual events, and a mean/max daily-maximum temperature chart with the threshold. The API also reports mean excess over the threshold. | `App.test.tsx` rendering test |
| 5 | Interactive visualisations (charts, maps) | A | Recharts charts and a React Leaflet map | `App.test.tsx` map and chart tests |
| 6 | Summary insights such as "increased by X% since ..." | A | `climate/trends.py::build_insights` and `period_change`. All text comes from computed values. The percentage is omitted when the early-period mean is zero. | `test_trends.py::test_insights_are_derived_from_values`, `test_period_change_zero_baseline_omits_percentage` |
| 7 | Ingest and cache historical weather data from a public API | A | `services/weather.py` (Open-Meteo archive, `temperature_2m_max`) and `cache/store.py` | `test_weather_and_cache.py`; `test_api.py::test_cache_hit_avoids_upstream` |
| 8 | Heatwave = 3+ consecutive days above the 95th percentile (defaults; percentile 90-99 and 2-10 days configurable) | A | `climate/heatwave.py`: `percentile_threshold`, `detect_events` (strict `>`); `AnalysisQuery.percentile`, `min_duration_days` | `test_heatwave.py` (2 vs 3 days, equality, long events, multiple events, gaps); `test_api.py::test_configurable_percentile_and_duration`, `test_exports_follow_configured_hazard` |
| 9 | Analyse frequency and duration trends using rolling averages or regression | A | 5-year rolling means plus OLS regression on heatwave days, event counts, and mean Tmax | `test_trends.py`; `test_api.py::test_analyze_valid_point` |
| 10 | Store data in a NoSQL database | A | MongoDB `observations` and `analyses` collections with TTL indexes | `test_weather_and_cache.py::test_mongo_cache_*` (mongomock); verified live against MongoDB Atlas, with a cache miss followed by a hit (see README) |
| 11 | API reads data from the database and returns JSON summaries and trend plots | A | `/api/analyze` reads observations and analyses from the cache store and returns JSON, including the series needed to draw the trend plots | `test_api.py::test_observation_cache_reused_for_new_label` |
| 12 | Handle noisy real-world data: gaps, outliers, units | A (evaluation criterion) | Complete calendar index; missing dates, nulls, and NaN kept as missing; values outside -60 to 60 °C flagged as implausible; duplicates counted; units verified as °C; opt-in single-day gap fill (flagged, excluded from the threshold); robust-z outliers flagged but kept; run and per-year counts in API, UI, CSV and PDF | `test_heatwave.py::test_build_daily_series_quality_counts`, `test_implausible_value_is_flagged_and_breaks_sequence`, gap-fill and outlier tests; `test_api.py::test_fill_gaps_is_opt_in_flagged_and_keyed`; `test_weather_and_cache.py::test_unexpected_units_rejected` |
| 13 | Clean API design and safe external API access | A (evaluation criterion) | Pydantic models, OpenAPI at `/docs`, uniform error JSON, timeouts, bounded retries (5xx and transport errors only), no retries on 429 | `test_api.py` provider-failure tests |
| 14 | API caching, rate limiting, and safe handling of user input | A (evaluation criterion) | Cache store; `security/rate_limit.py`; validation; label sanitising; CSV formula guard; PDF markup escaping; restricted CORS | `test_rate_limit`, `test_rate_limit_ignores_spoofed_forwarded_for`, `test_rate_limit_shared_across_instances_via_mongodb`, `test_rate_limit_headers_on_every_response`, `test_cors_restricted`, `test_csv_formula_injection_is_neutralised`, `test_pdf_label_markup_is_escaped` |
| 15 | README with setup, architecture, data sources, hazard logic, assumptions, and improvements | A | `README.md`, `docs/architecture.md` | n/a |
| 16 | Disclose AI tool use | A | README section "AI-tool disclosure" | n/a |
| 17 | Public GitHub repository and deployed app URL | A | Deployment configs (`render.yaml`, `frontend/vercel.json`) and step-by-step instructions | **Done.** Repository: https://github.com/Karuturinoushikajay/climate-lens. Live app: https://climate-lens-gamma.vercel.app, with the API at https://climate-lens-api.onrender.com. Verified live on 12 October 2026: CORS, an analysis, and the CSV and PDF downloads. |

## Bonus challenges

| # | Requirement | Source | Implementation | Tests |
| --- | --- | --- | --- | --- |
| B1 | Map UI for region selection | A (bonus) | `MapPanel.tsx`: click to set a point, two clicks to draw a box, presets, fly-to, attribution, and tile-provider fallback | `App.test.tsx` map-click, box-mode, and preset tests |
| B2 | PDF/CSV export of insights | A (bonus) | `/api/export.csv` (`exports/csv_export.py`) and `/api/export.pdf` (`exports/pdf_report.py`); UI in `ExportButtons.tsx` | `test_csv_export`, `test_pdf_export`, `test_dashboard_csv_pdf_agree`; `App.test.tsx` export tests |
| B3 | Trend detection with linear regression or Mann-Kendall | A (bonus) | Both are implemented: `climate/trends.py::linear_regression` and `climate/mann_kendall.py` (tie-corrected variance, continuity-corrected Z, two-sided p, Sen's slope) | `test_mann_kendall.py` (hand-computed values, ties, constant series, too few points, invalid values, alpha) |

## Engineering additions (source E)

| Item | Implementation | Tests |
| --- | --- | --- |
| Fixed reference baseline (e.g. 1991-2020) | `baseline=fixed_reference` in `AnalysisService._fetch_ranges` | `test_fixed_reference_baseline`, `test_fixed_reference_disjoint_fetches_two_ranges` |
| Cross-year event convention | `HeatwaveEvent.year_contributions` and `annual_indicators` | `test_heatwave.py::test_cross_year_annual_accounting` |
| Annual completeness rule (80%) excluding years from trends | `annual_indicators(min_completeness)` and `_trends` | `test_annual_completeness_and_leap_year` |
| Algorithm-versioned cache keys | `climate.ALGORITHM_VERSION` | `test_cache_hit_avoids_upstream` |
| MongoDB failure fallback | `create_cache` and `MongoCache._mark_error` | `test_create_cache_falls_back_to_memory`, `test_mongo_failure_degrades_gracefully` |
| Stale-result protection and request superseding | `App.tsx` stale banner; `useAnalysis.ts` abort and request id | `App.test.tsx` preset test; `useAnalysis.test.ts` |
| Health endpoint with cache mode and limits | `/api/health` | `test_health` |
| Docker Compose, Render, Vercel configuration | `docker-compose.yml`, `render.yaml`, `frontend/vercel.json` | Manual verification (see README) |
