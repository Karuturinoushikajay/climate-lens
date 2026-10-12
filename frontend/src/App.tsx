import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Leaf, RefreshCw } from 'lucide-react'
import { fetchHealth, fetchRegions } from './api/client'
import type { HealthResponse, PresetRegion } from './api/types'
import { ControlsPanel } from './components/ControlsPanel'
import { DataQualityPanel } from './components/DataQualityPanel'
import { ExportButtons } from './components/ExportButtons'
import { InsightsPanel } from './components/InsightsPanel'
import { MapPanel, type SelectMode } from './components/MapPanel'
import { MethodologyPanel } from './components/MethodologyPanel'
import { StatsPanel } from './components/StatsPanel'
import { SummaryCards } from './components/SummaryCards'
import { EventFrequencyChart, HeatwaveDaysChart, TemperatureChart } from './components/TrendCharts'
import { YearTable } from './components/YearTable'
import { useAnalysis } from './hooks/useAnalysis'
import {
  DEFAULT_MAX_YEAR,
  DEFAULT_SELECTION,
  describeLocation,
  paramsKey,
  percentileLabel,
  toQueryParams,
  validateSelection,
  type Location,
  type Selection,
} from './state/selection'

export default function App() {
  const [selection, setSelection] = useState<Selection>(DEFAULT_SELECTION)
  const [mode, setMode] = useState<SelectMode>('point')
  const [focusToken, setFocusToken] = useState(0)
  const [presets, setPresets] = useState<PresetRegion[]>([])
  const [presetsError, setPresetsError] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const { state, run } = useAnalysis()

  const maxYear = health?.limits.max_year ?? DEFAULT_MAX_YEAR
  const currentParams = useMemo(() => toQueryParams(selection), [selection])

  useEffect(() => {
    const ctrl = new AbortController()
    fetchRegions(ctrl.signal)
      .then((r) => setPresets(r.regions))
      .catch((e: Error) => e.name !== 'AbortError' && setPresetsError('Preset regions unavailable; enter coordinates manually.'))
    fetchHealth(ctrl.signal)
      .then(setHealth)
      .catch(() => undefined)
    return () => ctrl.abort()
  }, [])

  useEffect(() => {
    run(toQueryParams(DEFAULT_SELECTION))
  }, [run])

  const [labelFromPreset, setLabelFromPreset] = useState(true)

  const onLocation = useCallback(
    (location: Location, presetLabel?: string) => {
      setMode(location.kind)
      if (presetLabel !== undefined) {
        setSelection((s) => ({ ...s, location, label: presetLabel }))
        setLabelFromPreset(true)
      } else {
        setSelection((s) => ({ ...s, location, label: labelFromPreset ? '' : s.label }))
      }
      setFocusToken((t) => t + 1)
    },
    [labelFromPreset],
  )

  const onMapSelect = useCallback(
    (location: Location) => {
      setSelection((s) => ({ ...s, location, label: labelFromPreset ? '' : s.label }))
    },
    [labelFromPreset],
  )

  const onChange = (patch: Partial<Selection>) => {
    if (patch.label !== undefined) setLabelFromPreset(false)
    setSelection((s) => ({ ...s, ...patch }))
  }

  const onModeChange = (next: SelectMode) => {
    setMode(next)
    if (next === selection.location.kind) return
    const loc = selection.location
    if (next === 'box' && loc.kind === 'point') {
      const d = 0.5
      setSelection((s) => ({
        ...s,
        label: labelFromPreset ? '' : s.label,
        location: {
          kind: 'box',
          south: Math.max(-90, +(loc.latitude - d).toFixed(4)),
          north: Math.min(90, +(loc.latitude + d).toFixed(4)),
          west: Math.max(-180, +(loc.longitude - d).toFixed(4)),
          east: Math.min(180, +(loc.longitude + d).toFixed(4)),
        },
      }))
    } else if (next === 'point' && loc.kind === 'box') {
      setSelection((s) => ({
        ...s,
        label: labelFromPreset ? '' : s.label,
        location: {
          kind: 'point',
          latitude: +((loc.south + loc.north) / 2).toFixed(4),
          longitude: +((loc.west + loc.east) / 2).toFixed(4),
        },
      }))
    }
    setFocusToken((t) => t + 1)
  }

  const analyze = (location: Location) => {
    const next = { ...selection, location }
    if (validateSelection(next, maxYear).length === 0) run(toQueryParams(next))
  }

  const loading = state.status === 'loading'
  const shown =
    state.status === 'success'
      ? { data: state.data, params: state.params }
      : state.status === 'loading' || state.status === 'error'
        ? state.previous
        : undefined
  const stale = shown ? paramsKey(shown.params) !== paramsKey(currentParams) : false

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <Leaf size={22} aria-hidden />
          <div>
            <h1>Climate Lens</h1>
            <p>Climate Hazard Trend Analyzer · Heatwaves</p>
          </div>
        </div>
        <nav aria-label="Sections">
          <a href="#overview">Overview</a>
          <a href="#trends">Trends</a>
          <a href="#statistics">Statistics</a>
          <a href="#data">Data</a>
        </nav>
        <div className={`status-pill ${health ? (health.cache.healthy ? 'ok' : 'warn') : 'unknown'}`} title={health?.cache.detail}>
          {health ? `API online · cache: ${health.cache.mode}` : 'API status unknown'}
        </div>
      </header>

      <main>
        <div className="setup">
          <ControlsPanel
            selection={selection}
            presets={presets}
            presetsError={presetsError}
            maxYear={maxYear}
            loading={loading}
            onLocation={onLocation}
            onChange={onChange}
            onAnalyze={analyze}
          />
          <MapPanel
            location={selection.location}
            label={selection.label}
            mode={mode}
            onModeChange={onModeChange}
            onSelect={onMapSelect}
            focusToken={focusToken}
          />
        </div>

        {loading && (
          <div className="banner info" role="status">
            <RefreshCw size={16} className="spin" aria-hidden /> Fetching historical data and running the analysis…
            {shown && ' Previous results remain visible below until the new analysis finishes.'}
          </div>
        )}

        {state.status === 'error' && (
          <div className="banner error" role="alert">
            <AlertTriangle size={16} aria-hidden />
            <span>{state.error}</span>
            <button type="button" className="secondary small" onClick={() => run(state.params)}>
              Retry
            </button>
          </div>
        )}

        {!shown && !loading && state.status !== 'error' && (
          <div className="empty panel">Choose a region and period, then run the analysis.</div>
        )}

        {shown && (
          <div className={`results ${loading ? 'dimmed' : ''}`} aria-busy={loading}>
            {stale && !loading && (
              <div className="banner warn" role="status">
                <AlertTriangle size={16} aria-hidden /> The selection has changed. Results below still describe{' '}
                <strong>{shown.data.region.label}</strong> ({shown.data.period.start_year}–{shown.data.period.end_year}).
                Run the analysis to update.
              </div>
            )}

            <section id="overview" className="results-head">
              <div>
                <h2 data-testid="result-title">
                  {shown.data.region.label}{' '}
                  <span className="muted">
                    {shown.data.period.start_year}–{shown.data.period.end_year}
                  </span>
                </h2>
                <p className="fine">
                  {shown.data.region.kind === 'box' && shown.data.region.bbox
                    ? describeLocation({ kind: 'box', ...shown.data.region.bbox })
                    : `${shown.data.region.latitude.toFixed(4)}, ${shown.data.region.longitude.toFixed(4)}`}{' '}
                  · {shown.data.baseline.mode === 'analysis_period' ? 'analysis-period baseline' : 'fixed reference baseline'} ·
                  cache {shown.data.cache.analysis}
                </p>
                <p className="fine" data-testid="result-hazard">
                  Heatwave: {percentileLabel(shown.data.hazard.percentile)} · {shown.data.hazard.min_duration_days}+ days
                  {(shown.data.data_quality.gap_fill ?? 'off') !== 'off' && ' · single-day gaps filled'}
                </p>
                <p className="fine" data-testid="result-dataset">
                  Data: {shown.data.source.dataset}
                </p>
              </div>
              <ExportButtons key={paramsKey(shown.params)} params={shown.params} disabled={loading} />
            </section>

            <p className="limitations" role="note" data-testid="limitations">
              <strong>Limitations:</strong> values come from ERA5 reanalysis (a model estimate on a 0.25°, roughly 28 km, grid), not
              from weather stations. The {percentileLabel(shown.data.hazard.percentile)} threshold is relative to this
              location's own climate, so the same label means different temperatures in different places. A
              statistically significant trend is an association in this record, not proof of a cause.{' '}
              <a href="#limitations">Sources &amp; limitations</a>
            </p>

            <SummaryCards data={shown.data} />

            <DataQualityPanel data={shown.data} />

            <section id="trends" className="charts">
              <HeatwaveDaysChart data={shown.data} />
              <EventFrequencyChart data={shown.data} />
            </section>

            <InsightsPanel data={shown.data} />

            <div id="statistics" className="two-col">
              <StatsPanel data={shown.data} />
              <TemperatureChart data={shown.data} />
            </div>

            <div id="data">
              <MethodologyPanel data={shown.data} />
              <YearTable data={shown.data} />
            </div>

            <section id="limitations" className="panel disclaimer" aria-label="Sources and limitations">
              <h2>Sources &amp; limitations</h2>
              <ul>
                {shown.data.caveats.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
              <p className="fine">{shown.data.source.attribution}. Basemap © OpenStreetMap contributors.</p>
            </section>
          </div>
        )}
      </main>

      <footer className="footer">
        Climate Lens · algorithm {health?.algorithm_version ?? '—'} · Data: Open-Meteo Historical Weather API (ERA5)
      </footer>
    </div>
  )
}
