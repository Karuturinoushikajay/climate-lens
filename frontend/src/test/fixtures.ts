import type { AnalysisResponse, IndicatorTrend, PresetRegion } from '../api/types'

const trend = (indicator: string, code = 'increasing_significant'): IndicatorTrend => ({
  indicator,
  units: 'days/year',
  regression: {
    n: 3,
    slope_per_year: 1.5,
    slope_per_decade: 15,
    intercept: -2990,
    r_squared: 0.75,
    status: 'ok',
    notes: [],
  },
  mann_kendall: {
    n: 3,
    alpha: 0.05,
    s: 3,
    var_s_no_ties: 3.667,
    var_s: 3.667,
    z: 1.0445,
    p_value: 0.2963,
    sen_slope_per_year: 1.5,
    direction: 'increasing',
    significant: code.endsWith('_significant'),
    interpretation_code: code,
    interpretation:
      code === 'increasing_significant'
        ? 'Increasing monotonic trend detected, with the significance criterion met.'
        : 'Trend direction estimated, but statistical evidence is insufficient at the selected threshold.',
    dropped_values: 0,
    notes: ['Only 3 observations: the normal approximation for Z is less reliable below 10.'],
  },
  period_change: {
    window_years: 1,
    first_period: null,
    last_period: null,
    first_mean: null,
    last_mean: null,
    absolute_change: null,
    percent_change: null,
    note: 'Too few valid years to compare early and late periods.',
  },
})

export function makeAnalysis(label = 'Hyderabad', lat = 17.385, lon = 78.4867, start = 2000, end = 2002): AnalysisResponse {
  const years = Array.from({ length: end - start + 1 }, (_, i) => start + i)
  return {
    request: {},
    region: {
      label,
      kind: 'point',
      latitude: lat,
      longitude: lon,
      bbox: null,
      sampled_points: [[lat, lon]],
      note: 'Results describe the reanalysis grid cell containing this point.',
    },
    period: { start_year: start, end_year: end, start_date: `${start}-01-01`, end_date: `${end}-12-31`, years: years.length },
    hazard: {
      type: 'heatwave',
      definition: 'At least 3 consecutive valid days with daily maximum temperature strictly greater than the 95th-percentile threshold.',
      percentile: 95,
      min_duration_days: 3,
      comparison: 'strictly greater than',
    },
    baseline: {
      mode: 'analysis_period',
      reference_start_year: start,
      reference_end_year: end,
      threshold_c: 39.87,
      percentile_method: "numpy 'linear' interpolation (Hyndman & Fan type 7)",
      valid_days_used: 1096,
      note: 'Threshold computed from the selected analysis period.',
    },
    source: {
      provider: 'Open-Meteo Historical Weather API',
      dataset: 'ERA5',
      endpoint: 'https://archive-api.open-meteo.com/v1/archive',
      variable: 'temperature_2m_max',
      units: '°C',
      timezone: 'Asia/Kolkata',
      retrieved_at: '2026-10-12T00:00:00+00:00',
      aggregation: 'single point',
      grid_points: [{ latitude: lat, longitude: lon, elevation: 500 }],
      attribution: 'Weather data by Open-Meteo.com (CC BY 4.0)',
    },
    cache: { backend: 'memory', analysis: 'miss', observations: 'miss' },
    summary: {
      total_events: 7,
      total_heatwave_days: 31,
      mean_events_per_year: 2.3333,
      mean_heatwave_days_per_year: 10.3333,
      longest_event_days: 9,
      longest_event_start: `${end}-05-01`,
      longest_event_end: `${end}-05-09`,
      peak_tmax_c: 44.2,
      mean_tmax_c: 32.1,
      years_analyzed: years.length,
      years_used_for_trends: years.length,
      excluded_years: [],
    },
    annual: years.map((y, i) => ({
      year: y,
      event_count: i + 1,
      heatwave_days: [5, 10, 16][i] ?? 5,
      longest_event_days: [3, 5, 9][i] ?? 3,
      mean_tmax_c: 32 + i * 0.1,
      max_tmax_c: 43 + i,
      mean_excess_c: 1.2,
      valid_days: 365,
      expected_days: 365,
      missing_days: 0,
      completeness: 1,
      sufficient_data: true,
      interpolated_days: 0,
      duplicate_dates: 0,
      implausible_days: 0,
      outlier_days: i === 1 ? 2 : 0,
      heatwave_days_rolling_mean: null,
      event_count_rolling_mean: null,
    })),
    events: [],
    trends: {
      heatwave_days: trend('Annual heatwave days'),
      event_count: trend('Annual heatwave events', 'direction_not_significant'),
      mean_tmax: trend('Annual mean daily maximum temperature', 'direction_not_significant'),
    },
    data_quality: {
      analysis: {
        expected_days: 1096,
        received_days: 1096,
        provided_days: 1096,
        valid_days: 1096,
        missing_days: 0,
        missing_dates: 0,
        null_values: 0,
        implausible_values: 0,
        duplicate_dates: 0,
        interpolated_days: 0,
        outlier_days: 2,
        completeness: 1,
        accounting_ok: true,
        accounting: '1096 calendar days = 1096 valid + 0 missing + 0 implausible',
      },
      reference: null,
      min_year_completeness: 0.8,
      insufficient_years: [],
      plausible_range_c: [-60, 60],
      gap_fill: 'off',
      outlier_method: 'robust z-score |0.6745*(x - median)/MAD| > 4',
      outlier_dates: [
        { date: `${start + 1}-01-14`, tmax_c: 12.3, robust_z: -5.2 },
        { date: `${start + 1}-04-02`, tmax_c: 44.9, robust_z: 4.4 },
      ],
      outlier_total: 2,
      filled_dates: [],
      filled_total: 0,
    },
    insights: [`${label}: 7 heatwave event(s) totalling 31 heatwave day(s) were detected between ${start} and ${end}.`],
    caveats: ['Data are ERA5-family reanalysis estimates served by Open-Meteo, not weather-station observations.'],
    algorithm_version: 'test',
    generated_at: '2026-10-12T00:00:00+00:00',
  }
}

export function makePrecipAnalysis(
  hazard: 'heavy_rainfall' | 'drought',
  ...args: Parameters<typeof makeAnalysis>
): AnalysisResponse {
  const body = makeAnalysis(...args)
  const heavy = hazard === 'heavy_rainfall'
  body.hazard = {
    type: hazard,
    name: heavy ? 'Heavy rainfall' : 'Drought (dry spells)',
    definition: heavy
      ? 'Heavy-rain day: daily precipitation strictly greater than the 95th percentile of wet-day (>= 1 mm) precipitation in the baseline.'
      : 'Dry spell: at least 15 consecutive valid days with precipitation strictly less than 1 mm.',
    percentile: heavy ? 95 : null,
    min_duration_days: heavy ? 1 : 15,
    comparison: heavy ? 'strictly greater than' : 'strictly less than',
    variable: 'precipitation_sum',
    units: 'mm',
    labels: heavy
      ? {
          days: 'Heavy-rain days',
          events: 'Heavy-rain events',
          longest: 'Longest heavy-rain run',
          threshold: 'pct wet-day threshold',
          qualifying_day: 'heavy-rain day',
          third: 'Annual total',
          third_long: 'Annual total precipitation',
        }
      : {
          days: 'Dry-spell days',
          events: 'Dry spells',
          longest: 'Longest dry spell (CDD)',
          threshold: 'Dry-day threshold',
          qualifying_day: 'dry day',
          third: 'Annual total',
          third_long: 'Annual total precipitation',
        },
  }
  body.baseline = {
    ...body.baseline,
    threshold_c: null,
    threshold_value: heavy ? 48.6 : 1,
    threshold_units: 'mm',
    normal_annual_total_mm: 812,
  }
  body.source = { ...body.source, variable: 'precipitation_sum', units: 'mm' }
  body.summary = { ...body.summary, peak_tmax_c: null, mean_tmax_c: null, peak_daily_mm: 131.2, mean_annual_total_mm: 790 }
  body.annual = body.annual.map((a, i) => ({
    ...a,
    mean_tmax_c: null,
    max_tmax_c: null,
    mean_excess_c: null,
    total_mm: [700, 820, 850][i] ?? 800,
    max_daily_mm: [90.5, 101, 131.2][i] ?? 90,
    event_total_mm: heavy ? ([120, 180, 260][i] ?? 100) : null,
    percent_of_normal: [86.2, 101, 104.7][i] ?? 98.5,
    outlier_days: 0,
  }))
  body.trends.mean_tmax = { ...body.trends.mean_tmax, indicator: 'Annual total precipitation', units: 'mm/year' }
  body.data_quality = {
    ...body.data_quality,
    plausible_range_c: [0, 2000],
    plausible_range_units: 'mm',
    outlier_method: 'not applied to precipitation (a skewed distribution with many zero days)',
    outlier_dates: [],
    outlier_total: 0,
    analysis: { ...body.data_quality.analysis, outlier_days: 0 },
  }
  body.insights = [
    `${args[0] ?? 'Hyderabad'}: 7 ${heavy ? 'heavy-rain event(s)' : 'dry spell(s)'} totalling 31 ${heavy ? 'heavy-rain day(s)' : 'dry-spell day(s)'} were detected.`,
  ]
  return body
}

export const PRESETS: PresetRegion[] = [
  { id: 'hyderabad', name: 'Hyderabad', kind: 'city', latitude: 17.385, longitude: 78.4867, bbox: null },
  { id: 'delhi', name: 'Delhi', kind: 'city', latitude: 28.6139, longitude: 77.209, bbox: null },
  {
    id: 'telangana',
    name: 'Telangana (approx. box)',
    kind: 'state',
    latitude: 17.85,
    longitude: 79.5,
    bbox: { south: 15.8, west: 77.2, north: 19.9, east: 81.8 },
  },
]

export const HEALTH = {
  status: 'ok',
  version: '1.0.0',
  algorithm_version: 'test',
  environment: 'test',
  cache: { mode: 'memory', healthy: true, detail: 'in-memory' },
  data_source: {},
  limits: { min_year: 1940, max_year: 2025, max_analysis_span_years: 60, max_box_span_degrees: 10 },
}
