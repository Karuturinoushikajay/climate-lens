import type { QueryParams } from '../api/client'

export const MIN_YEAR = 1940
export const DEFAULT_MAX_YEAR = new Date().getFullYear() - 1
export const MAX_SPAN_YEARS = 60
export const MAX_BOX_SPAN = 10
export const MAX_LABEL_LENGTH = 80

export type Location =
  | { kind: 'point'; latitude: number; longitude: number }
  | { kind: 'box'; south: number; west: number; north: number; east: number }

export type BaselineMode = 'analysis_period' | 'fixed_reference'

export interface Selection {
  location: Location
  label: string
  startYear: number
  endYear: number
  hazard: string
  baseline: BaselineMode
  referenceStartYear: number
  referenceEndYear: number
}

export const DEFAULT_SELECTION: Selection = {
  location: { kind: 'point', latitude: 17.385, longitude: 78.4867 },
  label: 'Hyderabad',
  startYear: 1990,
  endYear: DEFAULT_MAX_YEAR,
  hazard: 'heatwave',
  baseline: 'analysis_period',
  referenceStartYear: 1991,
  referenceEndYear: 2020,
}

export function round4(n: number): number {
  return Math.round(n * 1e4) / 1e4
}

export function normalizeBox(a: [number, number], b: [number, number]): Location {
  return {
    kind: 'box',
    south: round4(Math.min(a[0], b[0])),
    north: round4(Math.max(a[0], b[0])),
    west: round4(Math.min(a[1], b[1])),
    east: round4(Math.max(a[1], b[1])),
  }
}

export function validateSelection(s: Selection, maxYear = DEFAULT_MAX_YEAR): string[] {
  const errors: string[] = []
  const loc = s.location
  if (loc.kind === 'point') {
    if (!Number.isFinite(loc.latitude) || loc.latitude < -90 || loc.latitude > 90)
      errors.push('Latitude must be between -90 and 90.')
    if (!Number.isFinite(loc.longitude) || loc.longitude < -180 || loc.longitude > 180)
      errors.push('Longitude must be between -180 and 180.')
  } else {
    const vals = [loc.south, loc.west, loc.north, loc.east]
    if (vals.some((v) => !Number.isFinite(v))) errors.push('All box edges must be numbers.')
    else {
      if (loc.south >= loc.north) errors.push('Box south must be less than north.')
      if (loc.west >= loc.east) errors.push('Box west must be less than east.')
      if (loc.north - loc.south > MAX_BOX_SPAN || loc.east - loc.west > MAX_BOX_SPAN)
        errors.push(`Box sides must not exceed ${MAX_BOX_SPAN} degrees.`)
    }
  }
  if (!Number.isInteger(s.startYear) || !Number.isInteger(s.endYear)) errors.push('Years must be whole numbers.')
  else {
    if (s.startYear < MIN_YEAR || s.endYear > maxYear) errors.push(`Years must be between ${MIN_YEAR} and ${maxYear}.`)
    if (s.startYear > s.endYear) errors.push('Start year must not be after end year.')
    if (s.endYear - s.startYear + 1 > MAX_SPAN_YEARS) errors.push(`The analysis window may not exceed ${MAX_SPAN_YEARS} years.`)
  }
  if (s.baseline === 'fixed_reference') {
    if (s.referenceStartYear < MIN_YEAR || s.referenceEndYear > maxYear)
      errors.push(`Reference years must be between ${MIN_YEAR} and ${maxYear}.`)
    if (s.referenceEndYear - s.referenceStartYear + 1 < 10) errors.push('The reference period must span at least 10 years.')
  }
  if (s.label.length > MAX_LABEL_LENGTH) errors.push(`Label must be ${MAX_LABEL_LENGTH} characters or fewer.`)
  return errors
}

export function toQueryParams(s: Selection): QueryParams {
  const params: QueryParams = {
    start_year: s.startYear,
    end_year: s.endYear,
    hazard: s.hazard,
    baseline: s.baseline,
  }
  if (s.location.kind === 'point') {
    params.latitude = round4(s.location.latitude)
    params.longitude = round4(s.location.longitude)
  } else {
    params.south = s.location.south
    params.west = s.location.west
    params.north = s.location.north
    params.east = s.location.east
  }
  const label = s.label.trim()
  if (label) params.label = label
  if (s.baseline === 'fixed_reference') {
    params.reference_start_year = s.referenceStartYear
    params.reference_end_year = s.referenceEndYear
  }
  return params
}

export function paramsKey(p: QueryParams): string {
  return Object.keys(p)
    .sort()
    .map((k) => `${k}=${p[k]}`)
    .join('&')
}

export function sameLocation(a: Location, b: Location): boolean {
  if (a.kind === 'point' && b.kind === 'point') return a.latitude === b.latitude && a.longitude === b.longitude
  if (a.kind === 'box' && b.kind === 'box')
    return a.south === b.south && a.west === b.west && a.north === b.north && a.east === b.east
  return false
}

export function describeLocation(loc: Location): string {
  if (loc.kind === 'point') return `${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}`
  return `S ${loc.south.toFixed(2)} · W ${loc.west.toFixed(2)} · N ${loc.north.toFixed(2)} · E ${loc.east.toFixed(2)}`
}
