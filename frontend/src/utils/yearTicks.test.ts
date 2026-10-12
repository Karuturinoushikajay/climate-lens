import { describe, expect, it } from 'vitest'
import { yearTicks } from './yearTicks'

const range = (a: number, b: number) => Array.from({ length: b - a + 1 }, (_, i) => a + i)

describe('yearTicks', () => {
  it('labels every year of a short window, including the last', () => {
    expect(yearTicks(range(1966, 1970))).toEqual([1966, 1967, 1968, 1969, 1970])
  })

  it('thins long windows to at most about ten ticks', () => {
    const ticks = yearTicks(range(1966, 2025))
    expect(ticks[0]).toBe(1966)
    expect(ticks.length).toBeLessThanOrEqual(11)
    expect(ticks.every((t, i) => i === 0 || t > ticks[i - 1])).toBe(true)
  })

  it('handles empty and single-year input', () => {
    expect(yearTicks([])).toEqual([])
    expect(yearTicks([2000])).toEqual([2000])
  })
})
