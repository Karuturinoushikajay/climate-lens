import type { AnalysisResponse } from '../api/types'
import { fmt, pct } from '../utils/format'

export function DataQualityPanel({ data }: { data: AnalysisResponse }) {
  const q = data.data_quality
  const a = q.analysis
  const gapFillOn = (q.gap_fill ?? 'off') !== 'off'
  const received = a.received_days ?? a.provided_days
  const missing = a.missing_dates + a.null_values
  const accountingOk =
    a.accounting_ok ??
    (received === a.valid_days + a.null_values + a.implausible_values &&
      a.expected_days === a.valid_days + missing + a.implausible_values)
  const counts = [
    { id: 'received', label: 'Days received', value: received, hint: 'distinct dates returned by the source' },
    { id: 'missing', label: 'Missing days', value: missing, hint: `${a.missing_dates} absent dates, ${a.null_values} null values` },
    {
      id: 'implausible',
      label: 'Implausible values',
      value: a.implausible_values,
      hint:
        q.plausible_range_c.length === 2
          ? `outside ${q.plausible_range_c[0]} to ${q.plausible_range_c[1]} ${q.plausible_range_units ?? '°C'}`
          : '',
    },
    { id: 'duplicate', label: 'Duplicate dates', value: a.duplicate_dates, hint: 'extra rows, first value kept' },
    {
      id: 'interpolated',
      label: 'Interpolated days',
      value: a.interpolated_days ?? 0,
      hint: gapFillOn ? 'single-day gaps filled (subset of missing)' : 'gap fill off',
    },
    {
      id: 'outlier',
      label: 'Outlier days',
      value: a.outlier_days ?? 0,
      hint: (q.outlier_method ?? '').startsWith('not applied') ? 'not screened for precipitation' : 'flagged, kept in analysis',
    },
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
  const outlierTotal = q.outlier_total ?? a.outlier_days ?? outliers.length
  const filled = q.filled_dates ?? []
  const filledTotal = q.filled_total ?? a.interpolated_days ?? filled.length

  return (
    <section className="panel dq-panel" aria-label="Data quality report">
      <div className="dq-head">
        <h2>Data quality report</h2>
        <p className="fine">
          {a.valid_days.toLocaleString()} of {a.expected_days.toLocaleString()} days observed ({pct(a.completeness, 2)}) · gap
          fill {gapFillOn ? 'on (single-day, flagged)' : 'off'}
        </p>
      </div>
      <p className={`dq-accounting ${accountingOk ? 'ok' : 'bad'}`} data-testid="dq-accounting">
        <span aria-hidden="true">{accountingOk ? '✓' : '✗'}</span>{' '}
        {a.expected_days.toLocaleString()} calendar days = {a.valid_days.toLocaleString()} valid + {missing.toLocaleString()} missing +{' '}
        {a.implausible_values.toLocaleString()} implausible · {received.toLocaleString()} received ={' '}
        {a.valid_days.toLocaleString()} valid + {a.null_values.toLocaleString()} null + {a.implausible_values.toLocaleString()}{' '}
        implausible{accountingOk ? '' : ' (counts do not add up)'}
      </p>
      <ul className="dq-counts">
        {counts.map((c) => (
          <li key={c.id} className={c.id !== 'received' && c.value > 0 ? 'has-issues' : ''}>
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
                  <th>Received</th>
                  <th>Valid</th>
                  <th>Missing</th>
                  <th>Implausible</th>
                  <th>Filled</th>
                  <th>Duplicates</th>
                  <th>Outliers</th>
                  <th>Completeness</th>
                </tr>
              </thead>
              <tbody>
                {flaggedYears.map((r) => (
                  <tr key={r.year}>
                    <td>{r.year}</td>
                    <td>{r.received_days ?? '–'}</td>
                    <td>{r.valid_days}</td>
                    <td>{r.missing_days - (r.implausible_days ?? 0)}</td>
                    <td>{r.implausible_days ?? 0}</td>
                    <td>{r.interpolated_days ?? 0}</td>
                    <td>{r.duplicate_dates ?? 0}</td>
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

      {filled.length > 0 && (
        <details className="dq-outliers">
          <summary data-testid="dq-filled-summary">
            Filled days ({filled.length < filledTotal ? `showing ${filled.length} of ${filledTotal}` : filledTotal})
          </summary>
          <ul>
            {filled.map((f) => (
              <li key={f.date}>
                {f.date}: {fmt(f.tmax_c, 1, ' °C')} (was {f.reason.replace('_', ' ')})
              </li>
            ))}
          </ul>
        </details>
      )}

      {outliers.length > 0 && (
        <details className="dq-outliers">
          <summary data-testid="dq-outlier-summary">
            Most extreme flagged days (
            {outliers.length < outlierTotal ? `showing ${outliers.length} of ${outlierTotal}` : outliers.length})
          </summary>
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
