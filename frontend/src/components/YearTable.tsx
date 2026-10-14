import type { AnalysisResponse } from '../api/types'
import { fmt, pct } from '../utils/format'

export function YearTable({ data }: { data: AnalysisResponse }) {
  const gapFillOn = (data.data_quality.gap_fill ?? 'off') !== 'off'
  return (
    <section className="panel" aria-label="Year-by-year data">
      <h2>Year-by-year indicators</h2>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Annual indicators table">
        <table>
          <thead>
            <tr>
              <th scope="col">Year</th>
              <th scope="col">Events</th>
              <th scope="col">Heatwave days</th>
              <th scope="col">Longest (d)</th>
              <th scope="col">Mean Tmax °C</th>
              <th scope="col">Max Tmax °C</th>
              <th scope="col">Mean excess °C</th>
              <th scope="col">Valid days</th>
              <th scope="col">Missing</th>
              {gapFillOn && (
                <th scope="col" title="Days set by single-day gap fill (interpolated, not observed)">
                  Filled
                </th>
              )}
              <th scope="col">Completeness</th>
            </tr>
          </thead>
          <tbody>
            {data.annual.map((a) => (
              <tr key={a.year} className={a.sufficient_data ? '' : 'insufficient'}>
                <th scope="row">{a.year}</th>
                <td>{a.event_count}</td>
                <td>{a.heatwave_days}</td>
                <td>{a.longest_event_days}</td>
                <td>{fmt(a.mean_tmax_c, 1)}</td>
                <td>{fmt(a.max_tmax_c, 1)}</td>
                <td>{fmt(a.mean_excess_c, 2)}</td>
                <td>{a.valid_days}</td>
                <td>{a.missing_days}</td>
                {gapFillOn && (
                  <td data-testid={`filled-${a.year}`} className={(a.interpolated_days ?? 0) > 0 ? 'filled-cell' : ''}>
                    {a.interpolated_days ?? 0}
                  </td>
                )}
                <td>
                  {pct(a.completeness)}
                  {!a.sufficient_data && <span className="badge">excluded</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {gapFillOn && <FilledNote data={data} />}
    </section>
  )
}

function FilledNote({ data }: { data: AnalysisResponse }) {
  const withFill = data.events.filter((e) => (e.filled_days ?? 0) > 0)
  const total = data.data_quality.filled_total ?? data.data_quality.analysis.interpolated_days ?? 0
  return (
    <p className="fine" data-testid="filled-note">
      Gap fill is on: {total} day{total === 1 ? '' : 's'} filled.{' '}
      {withFill.length > 0
        ? `${withFill.length} heatwave event${withFill.length === 1 ? '' : 's'} include${withFill.length === 1 ? 's' : ''} a filled day (${withFill
            .map((e) => e.start)
            .join(', ')}); without gap fill ${withFill.length === 1 ? 'it' : 'they'} could be shorter or split.`
        : 'No heatwave event depends on a filled day.'}
    </p>
  )
}
