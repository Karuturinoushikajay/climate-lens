export function fmt(value: number | null | undefined, digits = 2, suffix = ''): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'n/a'
  return `${value.toFixed(digits)}${suffix}`
}

export function fmtSigned(value: number | null | undefined, digits = 2, suffix = ''): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'n/a'
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`
}

export function fmtP(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return 'undefined'
  return p < 1e-4 ? '< 0.0001' : p.toFixed(4)
}

export function pct(fraction: number, digits = 1): string {
  return `${(fraction * 100).toFixed(digits)}%`
}
