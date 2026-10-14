import type { AnalysisResponse, HazardLabels } from '../api/types'

const HEATWAVE_LABELS: HazardLabels = {
  days: 'Heatwave days',
  events: 'Heatwave events',
  longest: 'Longest event',
  threshold: 'pct threshold',
  qualifying_day: 'hot day',
  third: 'Mean Tmax',
  third_long: 'Annual mean daily maximum temperature',
}

export interface HazardView {
  type: string
  name: string
  precip: boolean
  units: string
  labels: HazardLabels
  threshold: number | null
}

export function hazardView(data: AnalysisResponse): HazardView {
  const h = data.hazard
  const precip = h.type === 'heavy_rainfall' || h.type === 'drought'
  return {
    type: h.type,
    name: h.name || 'Heatwave',
    precip,
    units: h.units ?? '°C',
    labels: { ...HEATWAVE_LABELS, ...(h.labels ?? {}) },
    threshold: data.baseline.threshold_value ?? data.baseline.threshold_c,
  }
}
