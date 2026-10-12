import type { ReactNode } from 'react'
import { CalendarRange, Flame, Thermometer, Timer, Gauge, Database } from 'lucide-react'
import type { AnalysisResponse } from '../api/types'
import { fmt, pct } from '../utils/format'

export function SummaryCards({ data }: { data: AnalysisResponse }) {
  const s = data.summary
  const cards: { icon: ReactNode; id?: string; label: string; value: string; sub: string; tone: string }[] = [
    {
      icon: <Flame size={18} />,
      label: 'Heatwave events',
      value: String(s.total_events),
      sub: `${fmt(s.mean_events_per_year, 2)} per year`,
      tone: 'amber',
    },
    {
      icon: <CalendarRange size={18} />,
      label: 'Heatwave days',
      value: String(s.total_heatwave_days),
      sub: `${fmt(s.mean_heatwave_days_per_year, 1)} per year`,
      tone: 'amber',
    },
    {
      icon: <Timer size={18} />,
      label: 'Longest event',
      value: `${s.longest_event_days} d`,
      sub: s.longest_event_start ? `${s.longest_event_start} → ${s.longest_event_end}` : 'No events detected',
      tone: 'amber',
    },
    {
      icon: <Thermometer size={18} />,
      id: 'threshold',
      label: `${data.hazard.percentile}th pct threshold`,
      value: fmt(data.baseline.threshold_c, 1, ' °C'),
      sub: `${data.hazard.min_duration_days}+ days · baseline ${data.baseline.reference_start_year}–${data.baseline.reference_end_year}`,
      tone: 'mint',
    },
    {
      icon: <Gauge size={18} />,
      label: 'Mean daily max',
      value: fmt(s.mean_tmax_c, 1, ' °C'),
      sub: `Peak ${fmt(s.peak_tmax_c, 1, ' °C')}`,
      tone: 'mint',
    },
    {
      icon: <Database size={18} />,
      label: 'Data completeness',
      value: pct(data.data_quality.analysis.completeness),
      sub: `${s.years_used_for_trends}/${s.years_analyzed} years used for trends`,
      tone: 'mint',
    },
  ]
  return (
    <div className="cards" role="list" aria-label="Summary metrics">
      {cards.map((c) => (
        <div key={c.id ?? c.label} className={`card tone-${c.tone}`} role="listitem">
          <div className="card-label">
            {c.icon}
            <span>{c.label}</span>
          </div>
          <div className="card-value" data-testid={`metric-${c.id ?? c.label}`}>
            {c.value}
          </div>
          <div className="card-sub">{c.sub}</div>
        </div>
      ))}
    </div>
  )
}
