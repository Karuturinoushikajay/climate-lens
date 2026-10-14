import type { AnalysisResponse, QualityBlock } from '../api/types'
import { fmt, pct } from '../utils/format'

function Quality({ title, q }: { title: string; q: QualityBlock }) {
  return (
    <div className="stats-block">
      <h4>{title}</h4>
      <dl>
        <div className="stat-row"><dt>Calendar days</dt><dd>{q.expected_days}</dd></div>
        <div className="stat-row"><dt>Days received</dt><dd>{q.received_days ?? q.provided_days}</dd></div>
        <div className="stat-row"><dt>Valid values</dt><dd>{q.valid_days}</dd></div>
        <div className="stat-row"><dt>Missing dates</dt><dd>{q.missing_dates}</dd></div>
        <div className="stat-row"><dt>Null values</dt><dd>{q.null_values}</dd></div>
        <div className="stat-row"><dt>Implausible values</dt><dd>{q.implausible_values}</dd></div>
        <div className="stat-row"><dt>Duplicate dates</dt><dd>{q.duplicate_dates}</dd></div>
        <div className="stat-row"><dt>Interpolated days</dt><dd>{q.interpolated_days ?? 0}</dd></div>
        <div className="stat-row"><dt>Outlier days (kept)</dt><dd>{q.outlier_days ?? 0}</dd></div>
        <div className="stat-row"><dt>Completeness</dt><dd>{pct(q.completeness, 2)}</dd></div>
      </dl>
    </div>
  )
}

export function MethodologyPanel({ data }: { data: AnalysisResponse }) {
  const b = data.baseline
  const q = data.data_quality
  return (
    <section className="panel" aria-label="Methodology and data quality">
      <h2>Methodology &amp; data quality</h2>
      <div className="stats-grid">
        <div className="stats-block">
          <h4>Definition</h4>
          <p>{data.hazard.definition}</p>
          <dl>
            <div className="stat-row"><dt>Baseline</dt><dd>{b.mode === 'analysis_period' ? 'Analysis period' : 'Fixed reference'} ({b.reference_start_year}–{b.reference_end_year})</dd></div>
            <div className="stat-row"><dt>Threshold</dt><dd>{fmt(b.threshold_value ?? b.threshold_c, 2, ` ${b.threshold_units ?? '°C'}`)}</dd></div>
            {b.normal_annual_total_mm != null && (
              <div className="stat-row"><dt>Normal annual precipitation</dt><dd>{fmt(b.normal_annual_total_mm, 0, ' mm')}</dd></div>
            )}
            <div className="stat-row"><dt>Threshold method</dt><dd>{b.percentile_method}</dd></div>
            <div className="stat-row"><dt>Days used for threshold</dt><dd>{b.valid_days_used}</dd></div>
          </dl>
          <p className="fine">{b.note}</p>
          <p className="fine">
            Events are counted in the year they start; their days are attributed to the year each day falls in.{' '}
            {(q.gap_fill ?? 'off') !== 'off'
              ? 'Isolated one-day gaps are filled with the mean of their neighbours and flagged; longer gaps break a run.'
              : 'Any missing day breaks a run.'}{' '}
            Years below {pct(q.min_year_completeness, 0)} completeness are excluded from
            trend statistics
            {q.insufficient_years.length ? ` (excluded: ${q.insufficient_years.join(', ')})` : ' (none excluded)'}.
          </p>
          <details className="defaults-note fine" data-testid="defaults-note">
            <summary>Why these defaults?</summary>
            {data.hazard.type === 'heavy_rainfall' ? (
              <ul>
                <li>
                  <strong>95th percentile of wet days:</strong> the ETCCDI R95p convention. Only days with at least 1 mm
                  count, so the threshold is not dragged down by the many dry days.
                </li>
                <li>
                  <strong>1 day:</strong> a single extreme day is enough to cause flooding, so every heavy-rain day counts;
                  raise it to look for multi-day wet spells.
                </li>
                <li>
                  <strong>1991–2020 baseline:</strong> the current WMO climate normal, shared by every analysis period.
                </li>
              </ul>
            ) : data.hazard.type === 'drought' ? (
              <ul>
                <li>
                  <strong>Dry day below 1 mm:</strong> the ETCCDI convention used for consecutive dry days (CDD); trace
                  amounts do not end a dry spell.
                </li>
                <li>
                  <strong>15 days:</strong> long enough to stress rain-fed crops in the growing season, short enough to
                  register within a year. 5 to 60 days can be selected.
                </li>
                <li>
                  <strong>Annual % of normal:</strong> dry spells alone ignore how much rain falls when it does rain, so
                  the yearly total is compared with the 1991–2020 normal.
                </li>
              </ul>
            ) : (
            <ul>
              <li>
                <strong>95th percentile:</strong> keeps hot days rare (about 18 a year in the reference climate), so events
                describe extremes rather than ordinary summer heat. 90th is also common in the literature and can be
                selected.
              </li>
              <li>
                <strong>3 consecutive days:</strong> a common minimum duration in heatwave definitions; it separates
                sustained heat, which drives health impacts, from single hot days. 2 to 10 days can be selected.
              </li>
              <li>
                <strong>1991–2020 baseline:</strong> the current WMO 30-year climate normal. A fixed baseline gives every
                analysis period the same threshold, so periods can be compared.
              </li>
              <li>
                <strong>One annual threshold:</strong> simple and transparent, but not seasonal; a day-of-year threshold
                is listed as a future improvement.
              </li>
            </ul>
            )}
          </details>
        </div>
        <Quality title="Analysis period data" q={q.analysis} />
        {q.reference && <Quality title="Reference period data" q={q.reference} />}
        <div className="stats-block">
          <h4>Source</h4>
          <dl>
            <div className="stat-row"><dt>Provider</dt><dd>{data.source.provider}</dd></div>
            <div className="stat-row"><dt>Dataset</dt><dd>{data.source.dataset}</dd></div>
            <div className="stat-row"><dt>Variable</dt><dd>{data.source.variable} ({data.source.units})</dd></div>
            <div className="stat-row"><dt>Time zone</dt><dd>{data.source.timezone}</dd></div>
            <div className="stat-row"><dt>Spatial handling</dt><dd>{data.source.aggregation}</dd></div>
            <div className="stat-row"><dt>Retrieved</dt><dd>{data.source.retrieved_at}</dd></div>
            <div className="stat-row"><dt>Cache</dt><dd>{data.cache.backend} · analysis {data.cache.analysis} · observations {data.cache.observations}</dd></div>
          </dl>
          <p className="fine">{data.region.note}</p>
        </div>
      </div>
    </section>
  )
}
