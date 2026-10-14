import type { ReactNode } from 'react'
import { CalendarRange, CloudRain, Flame, Gauge, Database, Sun, Thermometer, Timer } from 'lucide-react'
import type { AnalysisResponse } from '../api/types'
import { fmt, pct } from '../utils/format'
import { hazardView } from '../utils/hazard'

export function SummaryCards({ data }: { data: AnalysisResponse }) {
  const s = data.summary
  const h = hazardView(data)
  const EventIcon = h.type === 'drought' ? Sun : h.precip ? CloudRain : Flame
  const baseline = `baseline ${data.baseline.reference_start_year}–${data.baseline.reference_end_year}`
  const thresholdCard =
    data.hazard.percentile != null
      ? {
          label: `${data.hazard.percentile}th ${h.labels.threshold}`,
          value: fmt(h.threshold, 1, ` ${h.units}`),
          sub: `${data.hazard.min_duration_days}+ days · ${baseline}`,
        }
      : {
          label: h.labels.threshold,
          value: `< ${fmt(h.threshold, 0, ` ${h.units}`)}`,
          sub: `spells of ${data.hazard.min_duration_days}+ days`,
        }
  const valueCard = h.precip
    ? {
        label: 'Mean annual precipitation',
        value: fmt(s.mean_annual_total_mm ?? null, 0, ' mm'),
        sub:
          data.baseline.normal_annual_total_mm != null
            ? `Normal ${fmt(data.baseline.normal_annual_total_mm, 0, ' mm')} · wettest day ${fmt(s.peak_daily_mm ?? null, 0, ' mm')}`
            : `Wettest day ${fmt(s.peak_daily_mm ?? null, 0, ' mm')}`,
      }
    : { label: 'Mean daily max', value: fmt(s.mean_tmax_c, 1, ' °C'), sub: `Peak ${fmt(s.peak_tmax_c, 1, ' °C')}` }
  const cards: { icon: ReactNode; id?: string; label: string; value: string; sub: string; tone: string }[] = [
    {
      icon: <EventIcon size={18} />,
      id: 'events',
      label: h.labels.events,
      value: String(s.total_events),
      sub: `${fmt(s.mean_events_per_year, 2)} per year`,
      tone: 'amber',
    },
    {
      icon: <CalendarRange size={18} />,
      id: 'days',
      label: h.labels.days,
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
    { icon: <Thermometer size={18} />, id: 'threshold', ...thresholdCard, tone: 'mint' },
    { icon: <Gauge size={18} />, id: 'value', ...valueCard, tone: 'mint' },
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
