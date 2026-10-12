import type { AnalysisResponse } from '../api/types'
import { fmt, pct } from '../utils/format'

export function YearTable({ data }: { data: AnalysisResponse }) {
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
                <td>
                  {pct(a.completeness)}
                  {!a.sufficient_data && <span className="badge">excluded</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
