import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ReactElement } from 'react'
import type { AnalysisResponse, IndicatorTrend } from '../api/types'
import { yearTicks } from '../utils/yearTicks'

const AMBER = '#f2b14c'
const AMBER_SOFT = '#c9782b'
const MINT = '#8fe3c8'
const MUTED = '#6f8a80'
const AXIS = '#9fb3aa'

function fitted(trend: IndicatorTrend, year: number, sufficient: boolean): number | null {
  const { slope_per_year: b, intercept: a } = trend.regression
  if (!sufficient || a === null || b === null) return null
  return Math.round((a + b * year) * 100) / 100
}

// Bars are centred on their year, so bar charts need half a year of room at each end.
function YearAxis({ years, bars }: { years: number[]; bars?: boolean }) {
  return (
    <XAxis
      dataKey="year"
      type="number"
      domain={bars ? ['dataMin - 0.5', 'dataMax + 0.5'] : ['dataMin', 'dataMax']}
      ticks={yearTicks(years)}
      allowDecimals={false}
      padding={bars ? undefined : { left: 8, right: 8 }}
      stroke={AXIS}
      tick={{ fontSize: 11 }}
      interval={0}
    />
  )
}

const tooltipStyle = {
  contentStyle: { background: '#141c19', border: '1px solid #2b3a34', borderRadius: 8, color: '#e6efe9' },
  labelStyle: { color: '#e6efe9' },
}

function ChartFrame({ title, subtitle, children }: { title: string; subtitle: string; children: ReactElement }) {
  return (
    <figure className="panel chart">
      <figcaption>
        <h3>{title}</h3>
        <p className="fine">{subtitle}</p>
      </figcaption>
      <div className="chart-body">
        <ResponsiveContainer width="100%" height={260}>
          {children}
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

export function HeatwaveDaysChart({ data }: { data: AnalysisResponse }) {
  const trend = data.trends.heatwave_days
  const rows = data.annual.map((a) => ({
    year: a.year,
    days: a.heatwave_days,
    rolling: a.heatwave_days_rolling_mean,
    fit: fitted(trend, a.year, a.sufficient_data),
  }))
  return (
    <ChartFrame
      title="Annual heatwave days"
      subtitle="Days inside heatwave events, attributed to the calendar year they occur in. Line: 5-year rolling mean; dashed: linear fit."
    >
      <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
        <CartesianGrid stroke="#22302b" vertical={false} />
        <YearAxis years={rows.map((r) => r.year)} bars />
        <YAxis stroke={AXIS} tick={{ fontSize: 11 }} allowDecimals={false} />
        <Tooltip {...tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="days" name="Heatwave days" fill={AMBER} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Line
          dataKey="rolling"
          name="5-yr rolling mean"
          stroke={MINT}
          dot={false}
          strokeWidth={2}
          connectNulls={false}
          isAnimationActive={false}
        />
        <Line
          dataKey="fit"
          name="Linear fit"
          stroke={MUTED}
          dot={false}
          strokeDasharray="5 4"
          strokeWidth={1.5}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ChartFrame>
  )
}

export function EventFrequencyChart({ data }: { data: AnalysisResponse }) {
  const trend = data.trends.event_count
  const rows = data.annual.map((a) => ({
    year: a.year,
    events: a.event_count,
    rolling: a.event_count_rolling_mean,
    fit: fitted(trend, a.year, a.sufficient_data),
  }))
  return (
    <ChartFrame
      title="Annual heatwave events"
      subtitle="Each event is counted once, in the year it starts. Line: 5-year rolling mean; dashed: linear fit."
    >
      <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
        <CartesianGrid stroke="#22302b" vertical={false} />
        <YearAxis years={rows.map((r) => r.year)} bars />
        <YAxis stroke={AXIS} tick={{ fontSize: 11 }} allowDecimals={false} />
        <Tooltip {...tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="events" name="Events" fill={AMBER_SOFT} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Line dataKey="rolling" name="5-yr rolling mean" stroke={MINT} dot={false} strokeWidth={2} isAnimationActive={false} />
        <Line
          dataKey="fit"
          name="Linear fit"
          stroke={MUTED}
          dot={false}
          strokeDasharray="5 4"
          strokeWidth={1.5}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ChartFrame>
  )
}

export function TemperatureChart({ data }: { data: AnalysisResponse }) {
  const threshold = data.baseline.threshold_c
  const rows = data.annual.map((a) => ({ year: a.year, mean: a.mean_tmax_c, max: a.max_tmax_c, threshold }))
  return (
    <ChartFrame
      title="Annual daily-maximum temperature"
      subtitle={`Mean and highest daily Tmax per year (°C). Dashed line: heatwave threshold ${threshold?.toFixed(1) ?? 'n/a'} °C.`}
    >
      <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
        <CartesianGrid stroke="#22302b" vertical={false} />
        <YearAxis years={rows.map((r) => r.year)} />
        <YAxis stroke={AXIS} tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
        <Tooltip {...tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line dataKey="mean" name="Mean Tmax" stroke={MINT} dot={false} strokeWidth={2} isAnimationActive={false} />
        <Line dataKey="max" name="Highest Tmax" stroke={AMBER} dot={false} strokeWidth={2} isAnimationActive={false} />
        {threshold !== null && (
          <Line
            dataKey="threshold"
            name="Threshold"
            stroke={MUTED}
            dot={false}
            strokeDasharray="4 4"
            isAnimationActive={false}
          />
        )}
      </ComposedChart>
    </ChartFrame>
  )
}
