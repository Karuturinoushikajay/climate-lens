import type { AnalysisResponse } from '../api/types'
import { fmt, pct } from '../utils/format'

export function DataQualityPanel({ data }: { data: AnalysisResponse }) {
  const q = data.data_quality
  const a = q.analysis
  const gapFillOn = (q.gap_fill ?? 'off') !== 'off'
  const counts = [
    { id: 'missing', label: 'Missing days', value: a.missing_days, hint: `${a.missing_dates} absent dates, ${a.null_values} null values` },
    { id: 'interpolated', label: 'Interpolated days', value: a.interpolated_days ?? 0, hint: gapFillOn ? 'single-day gaps filled' : 'gap fill off' },
    { id: 'duplicate', label: 'Duplicate dates', value: a.duplicate_dates, hint: 'first value kept' },
    {
      id: 'implausible',
      label: 'Implausible values',
      value: a.implausible_values,
      hint: q.plausible_range_c.length === 2 ? `outside ${q.plausible_range_c[0]} to ${q.plausible_range_c[1]} °C` : '',
    },
    { id: 'outlier', label: 'Outlier days', value: a.outlier_days ?? 0, hint: 'flagged, kept in analysis' },
  ]
  const flaggedYears = data.annual.filter(
    (r) =>
      r.missing_days > 0 ||
      (r.interpolated_days ?? 0) > 0 ||
      (r.duplicate_dates ?? 0) > 0 ||
      (r.implausible_days ?? 0) > 0 ||
      (r.outlier_days ?? 0) > 0,
  )
  const outliers = q.outlier_dates ?? []

  return (
    <section className="panel dq-panel" aria-label="Data quality report">
      <div className="dq-head">
        <h2>Data quality report</h2>
        <p className="fine">
          {a.valid_days.toLocaleString()} of {a.expected_days.toLocaleString()} days observed ({pct(a.completeness, 2)}) · gap
          fill {gapFillOn ? 'on (single-day, flagged)' : 'off'}
        </p>
      </div>
      <ul className="dq-counts">
        {counts.map((c) => (
          <li key={c.id} className={c.value > 0 ? 'has-issues' : ''}>
            <span className="dq-value" data-testid={`dq-${c.id}`}>
              {c.value.toLocaleString()}
            </span>
            <span className="dq-label">{c.label}</span>
            <span className="fine">{c.hint}</span>
          </li>
        ))}
      </ul>

      {flaggedYears.length > 0 ? (
        <details className="dq-years">
          <summary>
            Per-year breakdown ({flaggedYears.length} year{flaggedYears.length === 1 ? '' : 's'} with flags)
          </summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Year</th>
                  <th>Missing</th>
                  <th>Interpolated</th>
                  <th>Duplicates</th>
                  <th>Implausible</th>
                  <th>Outliers</th>
                  <th>Completeness</th>
                </tr>
              </thead>
              <tbody>
                {flaggedYears.map((r) => (
                  <tr key={r.year}>
                    <td>{r.year}</td>
                    <td>{r.missing_days}</td>
                    <td>{r.interpolated_days ?? 0}</td>
                    <td>{r.duplicate_dates ?? 0}</td>
                    <td>{r.implausible_days ?? 0}</td>
                    <td>{r.outlier_days ?? 0}</td>
                    <td>{pct(r.completeness, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : (
        <p className="fine">No year in the window has missing, interpolated, duplicate, implausible or outlier days.</p>
      )}

      {outliers.length > 0 && (
        <details className="dq-outliers">
          <summary>Most extreme flagged days ({outliers.length})</summary>
          <ul>
            {outliers.map((o) => (
              <li key={o.date}>
                {o.date}: {fmt(o.tmax_c, 1, ' °C')} (robust z {o.robust_z > 0 ? '+' : ''}
                {fmt(o.robust_z, 1)})
              </li>
            ))}
          </ul>
        </details>
      )}
      {q.outlier_method && <p className="fine">Outliers: {q.outlier_method}.</p>}
    </section>
  )
}
