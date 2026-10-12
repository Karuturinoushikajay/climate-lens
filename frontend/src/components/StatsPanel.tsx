import { useState } from 'react'
import type { AnalysisResponse, IndicatorTrend } from '../api/types'
import { fmt, fmtP, fmtSigned } from '../utils/format'
import { InfoTip } from './InfoTip'

const TIPS = {
  slope: 'Ordinary least-squares slope of the annual values against year. Describes the observed record; it is not a forecast and does not by itself establish significance.',
  r2: 'Share of year-to-year variance explained by the straight-line fit (0-1). Low values mean the series is noisy relative to the trend.',
  s: 'Mann-Kendall S: sum of signs of all later-minus-earlier pairs. Positive means later values tend to be larger.',
  z: 'Standardised S using the tie-corrected variance, inflated for serial correlation (Hamed-Rao), with a continuity correction.',
  p: 'Two-sided p-value after the Hamed-Rao serial-correlation adjustment. The verdict uses this value. Below alpha means the no-trend hypothesis is rejected at that level.',
  pRaw: 'Two-sided p-value of the classic test, which assumes independent years. Shown for comparison only.',
  vif: 'Factor by which the variance of S was inflated to account for autocorrelation in the detrended ranks (1 = no adjustment).',
  senCi: "Confidence interval for Sen's slope at the chosen alpha (Gilbert 1987), using the adjusted variance.",
  alpha: 'Significance level used to judge the p-value.',
  n: 'Number of annual values used (years failing the completeness rule are excluded).',
  sen: "Sen's slope: median of all pairwise slopes, a robust companion to Mann-Kendall.",
}

const INDICATORS = [
  { key: 'heatwave_days', label: 'Heatwave days' },
  { key: 'event_count', label: 'Event count' },
  { key: 'mean_tmax', label: 'Mean Tmax' },
] as const

function Row({ label, tip, value }: { label: string; tip: string; value: string }) {
  return (
    <div className="stat-row">
      <dt>
        {label} <InfoTip text={tip} />
      </dt>
      <dd>{value}</dd>
    </div>
  )
}

function Indicator({ t }: { t: IndicatorTrend }) {
  const r = t.regression
  const mk = t.mann_kendall
  const hasCi = mk.sen_slope_ci_low != null && mk.sen_slope_ci_high != null
  return (
    <div className="stats-grid">
      <div className="stats-block">
        <h4>Linear regression</h4>
        <dl>
          <Row label="Slope" tip={TIPS.slope} value={`${fmtSigned(r.slope_per_decade, 3)} ${t.units.replace('/year', '')} per decade`} />
          <Row label="R²" tip={TIPS.r2} value={fmt(r.r_squared, 3)} />
          <Row label="Observations" tip={TIPS.n} value={String(r.n)} />
        </dl>
        {r.notes.map((n) => (
          <p key={n} className="fine">
            {n}
          </p>
        ))}
      </div>
      <div className="stats-block">
        <h4>Mann-Kendall test</h4>
        <dl>
          <Row label="S" tip={TIPS.s} value={fmt(mk.s, 0)} />
          <Row label="Z" tip={TIPS.z} value={fmt(mk.z, 3)} />
          <Row label="p-value (adjusted)" tip={TIPS.p} value={fmtP(mk.p_value)} />
          {mk.p_value_uncorrected != null && (
            <Row label="p-value (unadjusted)" tip={TIPS.pRaw} value={fmtP(mk.p_value_uncorrected)} />
          )}
          {mk.variance_correction != null && (
            <Row label="Variance factor" tip={TIPS.vif} value={fmt(mk.variance_correction, 2)} />
          )}
          <Row label="α" tip={TIPS.alpha} value={fmt(mk.alpha, 2)} />
          <Row label="Observations" tip={TIPS.n} value={String(mk.n)} />
          <Row label="Direction" tip={TIPS.s} value={mk.direction} />
          <Row label="Sen's slope" tip={TIPS.sen} value={`${fmtSigned(mk.sen_slope_per_year, 3)} per year`} />
          {hasCi && (
            <Row
              label={`Sen's slope ${Math.round((1 - mk.alpha) * 100)}% CI`}
              tip={TIPS.senCi}
              value={`${fmtSigned(mk.sen_slope_ci_low ?? null, 3)} to ${fmtSigned(mk.sen_slope_ci_high ?? null, 3)}`}
            />
          )}
        </dl>
        <p className="verdict tone-neutral" data-testid={`mk-verdict-${t.indicator}`}>
          {mk.interpretation}
        </p>
        {mk.notes.map((n) => (
          <p key={n} className="fine">
            {n}
          </p>
        ))}
      </div>
    </div>
  )
}

export function StatsPanel({ data }: { data: AnalysisResponse }) {
  const [active, setActive] = useState<(typeof INDICATORS)[number]['key']>('heatwave_days')
  return (
    <section className="panel" aria-label="Statistical analysis">
      <div className="panel-head">
        <h2>Statistical analysis</h2>
        <div className="segmented" role="tablist" aria-label="Indicator">
          {INDICATORS.map((i) => (
            <button
              key={i.key}
              type="button"
              role="tab"
              aria-selected={active === i.key}
              className={active === i.key ? 'active' : ''}
              onClick={() => setActive(i.key)}
            >
              {i.label}
            </button>
          ))}
        </div>
      </div>
      <Indicator t={data.trends[active]} />
      <p className="fine">
        Regression and Mann-Kendall answer different questions and are reported separately. The Mann-Kendall verdict
        uses the Hamed-Rao adjustment for serial correlation; the unadjusted p-value is shown for comparison. Three
        indicators are tested at once with no multiple-testing correction, so one result below α can occur by chance.
        A significant result is a statistical association in this reanalysis record, not proof of a long-term climate
        trend; a non-significant result is not proof that no trend exists. Neither method establishes causation.
      </p>
    </section>
  )
}
