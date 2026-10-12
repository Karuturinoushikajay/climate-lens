import { describe, expect, it } from 'vitest'
import {
  DEFAULT_SELECTION,
  normalizeBox,
  paramsKey,
  sameLocation,
  toQueryParams,
  validateSelection,
  type Selection,
} from './selection'

const sel = (patch: Partial<Selection>): Selection => ({ ...DEFAULT_SELECTION, ...patch })

describe('validateSelection', () => {
  it('accepts the default selection', () => {
    expect(validateSelection(DEFAULT_SELECTION, 2025)).toEqual([])
  })

  it('rejects invalid coordinates', () => {
    const errors = validateSelection(sel({ location: { kind: 'point', latitude: 95, longitude: 200 } }), 2025)
    expect(errors).toContain('Latitude must be between -90 and 90.')
    expect(errors).toContain('Longitude must be between -180 and 180.')
  })

  it('rejects reversed and over-long year ranges', () => {
    expect(validateSelection(sel({ startYear: 2010, endYear: 2000 }), 2025)).toContain(
      'Start year must not be after end year.',
    )
    expect(validateSelection(sel({ startYear: 1940, endYear: 2010 }), 2025)).toContain(
      'The analysis window may not exceed 60 years.',
    )
  })

  it('validates boxes', () => {
    const big = sel({ location: { kind: 'box', south: 0, west: 0, north: 20, east: 5 } })
    expect(validateSelection(big, 2025)).toContain('Box sides must not exceed 10 degrees.')
    const inverted = sel({ location: { kind: 'box', south: 5, west: 0, north: 1, east: 5 } })
    expect(validateSelection(inverted, 2025)).toContain('Box south must be less than north.')
  })

  it('requires a 10-year reference period', () => {
    const s = sel({ baseline: 'fixed_reference', referenceStartYear: 2000, referenceEndYear: 2004 })
    expect(validateSelection(s, 2025)).toContain('The reference period must span at least 10 years.')
  })
})

describe('toQueryParams', () => {
  it('builds point params and omits reference years for analysis-period baseline', () => {
    expect(toQueryParams(DEFAULT_SELECTION)).toEqual({
      start_year: 1990,
      end_year: DEFAULT_SELECTION.endYear,
      hazard: 'heatwave',
      baseline: 'analysis_period',
      latitude: 17.385,
      longitude: 78.4867,
      label: 'Hyderabad',
    })
  })

  it('builds box params with reference years', () => {
    const p = toQueryParams(
      sel({
        label: '  ',
        location: { kind: 'box', south: 1, west: 2, north: 3, east: 4 },
        baseline: 'fixed_reference',
      }),
    )
    expect(p).toMatchObject({ south: 1, west: 2, north: 3, east: 4, reference_start_year: 1991, reference_end_year: 2020 })
    expect(p).not.toHaveProperty('latitude')
    expect(p).not.toHaveProperty('label')
  })
})

describe('helpers', () => {
  it('normalizes box corners in any order', () => {
    expect(normalizeBox([19, 80], [16, 77])).toEqual({ kind: 'box', south: 16, north: 19, west: 77, east: 80 })
  })

  it('paramsKey is order independent', () => {
    expect(paramsKey({ a: 1, b: 2 })).toBe(paramsKey({ b: 2, a: 1 }))
  })

  it('sameLocation compares by value', () => {
    expect(sameLocation(normalizeBox([1, 2], [3, 4]), { kind: 'box', south: 1, west: 2, north: 3, east: 4 })).toBe(true)
    expect(sameLocation({ kind: 'point', latitude: 1, longitude: 2 }, { kind: 'point', latitude: 1, longitude: 3 })).toBe(false)
  })
})
