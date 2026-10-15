export interface BBox {
  south: number
  west: number
  north: number
  east: number
}

export interface PresetRegion {
  id: string
  name: string
  kind: 'city' | 'state'
  latitude: number
  longitude: number
  bbox: BBox | null
}

export interface RegionsResponse {
  regions: PresetRegion[]
  note: string
}

export interface Place {
  id: number | null
  name: string
  latitude: number
  longitude: number
  admin1: string | null
  country: string | null
  country_code: string | null
  timezone: string | null
  population: number | null
}

export interface GeocodeResponse {
  query: string
  results: Place[]
  provider: string
  attribution: string
  cache: 'hit' | 'miss'
}

export interface HealthResponse {
  status: string
  version: string
  algorithm_version: string
  environment: string
  cache: { mode: string; healthy: boolean; detail: string }
  data_source: Record<string, string>
  limits: {
    min_year: number
    max_year: number
    max_analysis_span_years: number
    max_box_span_degrees: number
  }
  prewarm?: { status: string; done: number; total: number; detail?: string }
}

export interface Regression {
  n: number
  slope_per_year: number | null
  slope_per_decade: number | null
  intercept: number | null
  r_squared: number | null
  slope_se_per_year?: number | null
  slope_se_per_decade?: number | null
  t_statistic?: number | null
  p_value?: number | null
  status: string
  notes: string[]
}

export interface MannKendall {
  n: number
  alpha: number
  s: number | null
  var_s_no_ties: number | null
  var_s: number | null
  z: number | null
  p_value: number | null
  z_uncorrected?: number | null
  p_value_uncorrected?: number | null
  variance_correction?: number | null
  autocorrelation_lags?: number[]
  sen_slope_ci_low?: number | null
  sen_slope_ci_high?: number | null
  sen_slope_per_year: number | null
  direction: string
  significant: boolean
  interpretation_code: string
  interpretation: string
  dropped_values: number
  notes: string[]
}

export interface PeriodChange {
  window_years: number
  first_period: string | null
  last_period: string | null
  first_mean: number | null
  last_mean: number | null
  absolute_change: number | null
  percent_change: number | null
  note: string | null
}

export interface IndicatorTrend {
  indicator: string
  units: string
  regression: Regression
  mann_kendall: MannKendall
  period_change: PeriodChange
}

export interface AnnualRow {
  year: number
  event_count: number
  event_days: number
  longest_event_days: number
  mean_tmax_c: number | null
  max_tmax_c: number | null
  mean_excess_c: number | null
  total_mm?: number | null
  max_daily_mm?: number | null
  event_total_mm?: number | null
  percent_of_normal?: number | null
  valid_days: number
  expected_days: number
  missing_days: number
  completeness: number
  sufficient_data: boolean
  received_days?: number
  interpolated_days?: number
  duplicate_dates?: number
  implausible_days?: number
  outlier_days?: number
  event_days_rolling_mean: number | null
  event_count_rolling_mean: number | null
}

export interface HeatwaveEvent {
  start: string
  end: string
  duration_days: number
  peak_tmax_c: number | null
  mean_tmax_c: number | null
  mean_excess_c: number | null
  peak_value?: number | null
  total_value?: number | null
  start_year: number
  year_contributions: { year: number; days: number }[]
  filled_days?: number
}

export interface QualityBlock {
  expected_days: number
  received_days?: number
  provided_days: number
  valid_days: number
  missing_days: number
  missing_dates: number
  null_values: number
  implausible_values: number
  duplicate_dates: number
  interpolated_days?: number
  outlier_days?: number
  completeness: number
  accounting_ok?: boolean
  accounting?: string
}

export interface OutlierDay {
  date: string
  value: number
  robust_z: number
}

export interface FilledDay {
  date: string
  value: number
  reason: string
}

export interface HazardLabels {
  days: string
  events: string
  longest: string
  threshold: string
  qualifying_day: string
  third: string
  third_long: string
}

export interface AnalysisResponse {
  request: Record<string, unknown>
  region: {
    label: string
    kind: 'point' | 'box'
    latitude: number
    longitude: number
    bbox: BBox | null
    sampled_points: number[][]
    note: string
  }
  period: { start_year: number; end_year: number; start_date: string; end_date: string; years: number }
  hazard: {
    type: string
    name?: string
    definition: string
    percentile: number | null
    min_duration_days: number
    comparison: string
    variable?: string
    units?: string
    labels?: HazardLabels
  }
  baseline: {
    mode: 'analysis_period' | 'fixed_reference'
    reference_start_year: number
    reference_end_year: number
    threshold_value: number | null
    threshold_units: string
    normal_annual_total_mm?: number | null
    percentile_method: string
    valid_days_used: number
    note: string
  }
  source: {
    provider: string
    dataset: string
    endpoint: string
    variable: string
    units: string
    timezone: string
    retrieved_at: string
    aggregation: string
    grid_points: { latitude: number; longitude: number; elevation: number | null }[]
    attribution: string
  }
  cache: { backend: string; analysis: 'hit' | 'miss'; observations: 'hit' | 'miss' | 'partial' }
  summary: {
    total_events: number
    total_event_days: number
    mean_events_per_year: number
    mean_event_days_per_year: number
    longest_event_days: number
    longest_event_start: string | null
    longest_event_end: string | null
    peak_tmax_c: number | null
    mean_tmax_c: number | null
    peak_daily_mm?: number | null
    mean_annual_total_mm?: number | null
    years_analyzed: number
    years_used_for_trends: number
    excluded_years: number[]
  }
  annual: AnnualRow[]
  events: HeatwaveEvent[]
  trends: { event_days: IndicatorTrend; event_count: IndicatorTrend; climate_indicator: IndicatorTrend }
  data_quality: {
    analysis: QualityBlock
    reference: QualityBlock | null
    min_year_completeness: number
    insufficient_years: number[]
    plausible_range: number[]
    plausible_range_units?: string
    gap_fill?: string
    outlier_method?: string
    outlier_dates?: OutlierDay[]
    outlier_total?: number
    filled_dates?: FilledDay[]
    filled_total?: number
  }
  insights: string[]
  caveats: string[]
  algorithm_version: string
  generated_at: string
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: { field: string | null; message: string }[] }
}
