import { useEffect, useState } from 'react'
import { Loader2, Play } from 'lucide-react'
import type { PresetRegion } from '../api/types'
import {
  MAX_LABEL_LENGTH,
  MIN_YEAR,
  describeLocation,
  sameLocation,
  validateLocation,
  validateSelection,
  type BaselineMode,
  type Location,
  type Selection,
} from '../state/selection'
import { InfoTip } from './InfoTip'

const HAZARDS = [
  { id: 'heatwave', label: 'Heatwave', available: true },
  { id: 'drought', label: 'Drought (not implemented)', available: false },
  { id: 'heavy_rainfall', label: 'Heavy rainfall (not implemented)', available: false },
]

const COORD_DEBOUNCE_MS = 500

interface Props {
  selection: Selection
  presets: PresetRegion[]
  presetsError: string | null
  maxYear: number
  loading: boolean
  onLocation: (location: Location, label?: string) => void
  onChange: (patch: Partial<Selection>) => void
  onAnalyze: (location: Location) => void
}

type Drafts = Record<string, string>

function draftsFor(loc: Location): Drafts {
  return loc.kind === 'point'
    ? { latitude: String(loc.latitude), longitude: String(loc.longitude) }
    : { south: String(loc.south), west: String(loc.west), north: String(loc.north), east: String(loc.east) }
}

function parseDrafts(kind: Location['kind'], d: Drafts): Location | null {
  const keys = kind === 'point' ? ['latitude', 'longitude'] : ['south', 'west', 'north', 'east']
  const nums = keys.map((k) => (d[k]?.trim() === '' ? NaN : Number(d[k])))
  if (nums.some((n) => !Number.isFinite(n))) return null
  return kind === 'point'
    ? { kind, latitude: nums[0], longitude: nums[1] }
    : { kind, south: nums[0], west: nums[1], north: nums[2], east: nums[3] }
}

function presetLocation(p: PresetRegion): Location {
  return p.bbox ? { kind: 'box', ...p.bbox } : { kind: 'point', latitude: p.latitude, longitude: p.longitude }
}

export function ControlsPanel({
  selection,
  presets,
  presetsError,
  maxYear,
  loading,
  onLocation,
  onChange,
  onAnalyze,
}: Props) {
  const loc = selection.location
  const [drafts, setDrafts] = useState<Drafts>(() => draftsFor(loc))
  const presetId =
    presets.find((p) => sameLocation(presetLocation(p), loc) && selection.label.trim() === p.name)?.id ?? ''

  // Reset text inputs when the location changes from the map or a preset.
  const [syncedLoc, setSyncedLoc] = useState(loc)
  if (syncedLoc !== loc) {
    setSyncedLoc(loc)
    setDrafts(draftsFor(loc))
  }

  // Commit typed coordinates after a pause rather than on every keystroke.
  const draftLoc = parseDrafts(loc.kind, drafts)
  const draftValid = draftLoc !== null && validateLocation(draftLoc).length === 0
  const commitDrafts = () => {
    if (draftValid && !sameLocation(draftLoc, loc)) onLocation(draftLoc)
  }
  useEffect(() => {
    if (!draftValid || sameLocation(draftLoc, loc)) return
    const t = setTimeout(commitDrafts, COORD_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [drafts]) // eslint-disable-line react-hooks/exhaustive-deps

  // Validate what is typed, not only what has been committed, so errors clear as soon as the input is fixed.
  const errors = draftLoc
    ? validateSelection({ ...selection, location: draftLoc }, maxYear)
    : ['Enter a number for every coordinate.']

  const runAnalysis = () => {
    if (!draftLoc || errors.length > 0) return
    commitDrafts()
    onAnalyze(draftLoc)
  }

  const choosePreset = (id: string) => {
    const p = presets.find((r) => r.id === id)
    if (p) onLocation(presetLocation(p), p.name)
  }

  const coordField = (key: string, label: string, min: number, max: number) => (
    <label className="field" key={key}>
      <span>{label}</span>
      <input
        type="number"
        inputMode="decimal"
        step="0.0001"
        min={min}
        max={max}
        value={drafts[key] ?? ''}
        aria-label={label}
        onChange={(e) => setDrafts((d) => ({ ...d, [key]: e.target.value }))}
        onBlur={commitDrafts}
        onKeyDown={(e) => e.key === 'Enter' && commitDrafts()}
      />
    </label>
  )

  const cities = presets.filter((p) => p.kind === 'city')
  const states = presets.filter((p) => p.kind === 'state')
  const years = Array.from({ length: maxYear - MIN_YEAR + 1 }, (_, i) => MIN_YEAR + i)

  return (
    <section className="panel controls" aria-label="Analysis controls">
      <h2>Analysis setup</h2>

      <label className="field">
        <span>Preset region</span>
        <select value={presetId} onChange={(e) => choosePreset(e.target.value)} aria-label="Preset region">
          <option value="">Custom selection</option>
          <optgroup label="Cities (point)">
            {cities.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </optgroup>
          <optgroup label="States (approximate box)">
            {states.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </optgroup>
        </select>
      </label>
      {presetsError && <p className="field-error">{presetsError}</p>}

      <div className="coord-grid">
        {loc.kind === 'point' ? (
          <>
            {coordField('latitude', 'Latitude', -90, 90)}
            {coordField('longitude', 'Longitude', -180, 180)}
          </>
        ) : (
          <>
            {coordField('south', 'South', -90, 90)}
            {coordField('north', 'North', -90, 90)}
            {coordField('west', 'West', -180, 180)}
            {coordField('east', 'East', -180, 180)}
          </>
        )}
      </div>
      <p className="fine">Selected: {describeLocation(loc)}</p>

      <label className="field">
        <span>Location label</span>
        <input
          type="text"
          value={selection.label}
          maxLength={MAX_LABEL_LENGTH}
          placeholder="e.g. My farm"
          aria-label="Location label"
          onChange={(e) => onChange({ label: e.target.value })}
        />
      </label>

      <label className="field">
        <span>Hazard type</span>
        <select value={selection.hazard} onChange={(e) => onChange({ hazard: e.target.value })} aria-label="Hazard type">
          {HAZARDS.map((h) => (
            <option key={h.id} value={h.id} disabled={!h.available}>
              {h.label}
            </option>
          ))}
        </select>
      </label>

      <div className="coord-grid">
        <label className="field">
          <span>Start year</span>
          <select
            value={selection.startYear}
            aria-label="Start year"
            onChange={(e) => onChange({ startYear: Number(e.target.value) })}
          >
            {years.map((y) => (
              <option key={y}>{y}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>End year</span>
          <select value={selection.endYear} aria-label="End year" onChange={(e) => onChange({ endYear: Number(e.target.value) })}>
            {years.map((y) => (
              <option key={y}>{y}</option>
            ))}
          </select>
        </label>
      </div>

      <fieldset className="field baseline">
        <legend>
          Percentile baseline{' '}
          <InfoTip text="The 95th-percentile threshold can come from the analysis period itself or from a fixed reference period (e.g. 1991-2020). Results from different baselines are not directly comparable." />
        </legend>
        {(['fixed_reference', 'analysis_period'] as BaselineMode[]).map((mode) => (
          <label key={mode} className="radio">
            <input
              type="radio"
              name="baseline"
              value={mode}
              checked={selection.baseline === mode}
              onChange={() => onChange({ baseline: mode })}
            />
            {mode === 'analysis_period' ? 'Analysis period' : 'Fixed reference period (recommended)'}
          </label>
        ))}
        {selection.baseline === 'fixed_reference' && (
          <div className="coord-grid">
            <label className="field">
              <span>Reference start</span>
              <select
                value={selection.referenceStartYear}
                aria-label="Reference start year"
                onChange={(e) => onChange({ referenceStartYear: Number(e.target.value) })}
              >
                {years.map((y) => (
                  <option key={y}>{y}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Reference end</span>
              <select
                value={selection.referenceEndYear}
                aria-label="Reference end year"
                onChange={(e) => onChange({ referenceEndYear: Number(e.target.value) })}
              >
                {years.map((y) => (
                  <option key={y}>{y}</option>
                ))}
              </select>
            </label>
          </div>
        )}
      </fieldset>

      {errors.length > 0 && (
        <ul className="field-error" role="alert">
          {errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}

      <button type="button" className="primary" onClick={runAnalysis} disabled={loading || errors.length > 0}>
        {loading ? <Loader2 size={16} className="spin" aria-hidden /> : <Play size={16} aria-hidden />}
        {loading ? 'Analysing…' : 'Run analysis'}
      </button>
    </section>
  )
}
