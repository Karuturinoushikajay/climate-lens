const MAX_TICKS = 10

export function yearTicks(years: number[]): number[] {
  if (years.length === 0) return []
  const first = years[0]
  const last = years[years.length - 1]
  const step = Math.max(1, Math.ceil((last - first + 1) / MAX_TICKS))
  const ticks: number[] = []
  for (let y = first; y <= last; y += step) ticks.push(y)
  if (ticks[ticks.length - 1] !== last && last - ticks[ticks.length - 1] >= step / 2) ticks.push(last)
  return ticks
}
