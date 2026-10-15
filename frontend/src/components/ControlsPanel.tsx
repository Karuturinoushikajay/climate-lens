import { useEffect, useState } from 'react'
import { Loader2, Play } from 'lucide-react'
import type { PresetRegion } from '../api/types'
import {
  HAZARD_OPTIONS,
  MAX_LABEL_LENGTH,
  MIN_YEAR,
  PERCENTILE_MAX,
  PERCENTILE_MIN,
  PERCENTILE_PRESETS,
  describeLocation,
  hazardOption,
  sameLocation,
  validateLocation,
  validateSelection,
  type BaselineMode,
  type Location,
  type Selection,
} from '../state/selection'
import { CitySearch } from './CitySearch'
import { InfoTip } from './InfoTip'

const PERCENTILE_TIPS: Record<string, string> = {
  heatwave:
    'A hot day is warmer than this percentile of daily maximum temperatures for the location. Higher percentiles find rarer, more extreme heat. Any value from 90 to 99.9 is accepted.',
  heavy_rainfall:
    'A heavy-rain day has more rain than this percentile of wet days (at least 1 mm) in the baseline, as in the ETCCDI R95p index. Higher percentiles find rarer downpours. Any value from 90 to 99.9 is accepted.',
}

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

  const hazard = hazardOption(selection.hazard)
  const chooseHazard = (id: string) => {
    const next = hazardOption(id)
    onChange({ hazard: next.id, minDurationDays: next.defaultRun, fillGaps: next.gapFill && selection.fillGaps })
  }

  const cities = presets.filter((p) => p.kind === 'city')
  const states = presets.filter((p) => p.kind === 'state')
  const years = Array.from({ length: maxYear - MIN_YEAR + 1 }, (_, i) => MIN_YEAR + i)

  return (
    <section className="panel controls" aria-label="Analysis controls">
      <h2>Analysis setup</h2>

      <CitySearch
        onSelect={(p, label) => onLocation({ kind: 'point', latitude: p.latitude, longitude: p.longitude }, label)}
      />

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
        <select value={selection.hazard} onChange={(e) => chooseHazard(e.target.value)} aria-label="Hazard type">
          {HAZARD_OPTIONS.map((h) => (
            <option key={h.id} value={h.id}>
              {h.label}
            </option>
          ))}
        </select>
      </label>

      <div className="coord-grid">
        {hazard.usesPercentile ? (
          <label className="field">
            <span>
              Threshold percentile <InfoTip text={PERCENTILE_TIPS[hazard.id] ?? PERCENTILE_TIPS.heatwave} />
            </span>
            <input
              type="number"
              inputMode="decimal"
              min={PERCENTILE_MIN}
              max={PERCENTILE_MAX}
              step={0.1}
              list="percentile-presets"
              value={Number.isNaN(selection.percentile) ? '' : selection.percentile}
              aria-label="Threshold percentile"
              onChange={(e) => onChange({ percentile: e.target.value === '' ? NaN : Number(e.target.value) })}
            />
            <datalist id="percentile-presets">
              {PERCENTILE_PRESETS.map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
          </label>
        ) : (
          <div className="field" data-testid="dry-day-rule">
            <span>
              Dry day <InfoTip text="A dry day has less than 1 mm of precipitation (the ETCCDI convention). A missing day is never counted as dry." />
            </span>
            <p className="fine static-value">below 1 mm</p>
          </div>
        )}
        <label className="field">
          <span>{hazard.runLabel}</span>
          <input
            type="number"
            inputMode="numeric"
            min={hazard.minRun}
            max={hazard.maxRun}
            step={1}
            value={Number.isNaN(selection.minDurationDays) ? '' : selection.minDurationDays}
            aria-label="Minimum consecutive days"
            onChange={(e) => onChange({ minDurationDays: e.target.value === '' ? NaN : Number(e.target.value) })}
          />
        </label>
      </div>

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
          {hazard.usesPercentile ? 'Percentile baseline' : 'Precipitation normal baseline'}{' '}
          <InfoTip text="The threshold (or, for dry spells, the precipitation normal) can come from the analysis period itself or from a fixed reference period (e.g. 1991-2020). Results from different baselines are not directly comparable." />
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

      <label className={`radio checkbox${hazard.gapFill ? '' : ' disabled'}`}>
        <input
          type="checkbox"
          checked={hazard.gapFill && selection.fillGaps}
          disabled={!hazard.gapFill}
          aria-label="Fill single-day gaps"
          onChange={(e) => onChange({ fillGaps: e.target.checked })}
        />
        Fill single-day gaps (interpolated, flagged){' '}
        <InfoTip
          text={
            hazard.gapFill
              ? 'Off by default. When on, an isolated missing day between two observed days is set to their mean so it does not break a heatwave run. Filled days are counted in the data-quality report and never used for the threshold.'
              : 'Not available for precipitation: rain is too patchy to interpolate from neighbouring days, so missing days stay missing.'
          }
        />
      </label>

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
