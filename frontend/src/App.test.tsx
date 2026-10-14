import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HEALTH, PRESETS, makeAnalysis } from './test/fixtures'

vi.mock('react-leaflet', async () => (await import('./test/leafletMock')).leafletMock)

import App from './App'
import { fakeMap, mapClick } from './test/leafletMock'

type Responder = (url: URL, init?: RequestInit) => Promise<Response>

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })

function defaultAnalyze(url: URL): Promise<Response> {
  const p = url.searchParams
  const label = p.get('label') ?? `Point ${p.get('latitude')}, ${p.get('longitude')}`
  const body = makeAnalysis(
    label,
    Number(p.get('latitude') ?? 0),
    Number(p.get('longitude') ?? 0),
    Number(p.get('start_year')),
    Number(p.get('end_year')),
  )
  if (p.has('percentile')) body.hazard.percentile = Number(p.get('percentile'))
  if (p.has('min_duration_days')) body.hazard.min_duration_days = Number(p.get('min_duration_days'))
  if (p.get('fill_gaps') === 'true') {
    body.data_quality.gap_fill = 'single-day linear'
    body.data_quality.analysis.interpolated_days = 3
    body.data_quality.filled_total = 3
    body.data_quality.filled_dates = [
      { date: `${body.period.start_year}-05-10`, tmax_c: 41.2, reason: 'null' },
      { date: `${body.period.start_year}-07-02`, tmax_c: 30.1, reason: 'missing_date' },
    ]
    body.annual[0].interpolated_days = 3
    body.annual[0].missing_days = 3
    body.events = [
      {
        start: `${body.period.start_year}-05-08`,
        end: `${body.period.start_year}-05-12`,
        duration_days: 5,
        peak_tmax_c: 43,
        mean_tmax_c: 42,
        mean_excess_c: 1.5,
        start_year: body.period.start_year,
        year_contributions: [{ year: body.period.start_year, days: 5 }],
        filled_days: 1,
      },
    ]
  }
  return Promise.resolve(json(body))
}

const PHOENIX = {
  id: 5308655,
  name: 'Phoenix',
  latitude: 33.44838,
  longitude: -112.07404,
  admin1: 'Arizona',
  country: 'United States',
  country_code: 'US',
  timezone: 'America/Phoenix',
  population: 1650070,
}
const PHOENIX_OR = { ...PHOENIX, id: 5745656, latitude: 42.27541, longitude: -122.81809, admin1: 'Oregon', population: 4553 }

function defaultGeocode(url: URL): Promise<Response> {
  const name = url.searchParams.get('name') ?? ''
  const results = name.toLowerCase().startsWith('phoe') ? [PHOENIX, PHOENIX_OR] : []
  return Promise.resolve(json({ query: name, results, provider: 'Open-Meteo Geocoding API', attribution: '', cache: 'miss' }))
}

let analyzeResponder: Responder
let exportResponder: Responder
let geocodeResponder: Responder
let calls: URL[]

beforeEach(() => {
  calls = []
  analyzeResponder = defaultAnalyze
  geocodeResponder = defaultGeocode
  exportResponder = async (url) =>
    new Response(url.pathname.endsWith('.pdf') ? '%PDF-1.4' : 'Year\n2000', {
      status: 200,
      headers: {
        'Content-Type': url.pathname.endsWith('.pdf') ? 'application/pdf' : 'text/csv',
        'Content-Disposition': `attachment; filename="climate-lens-test.${url.pathname.endsWith('.pdf') ? 'pdf' : 'csv'}"`,
      },
    })
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input))
    calls.push(url)
    if (url.pathname === '/api/regions') return json({ regions: PRESETS, note: '' })
    if (url.pathname === '/api/health') return json(HEALTH)
    if (url.pathname === '/api/analyze') return analyzeResponder(url, init)
    if (url.pathname === '/api/geocode') return geocodeResponder(url, init)
    if (url.pathname.startsWith('/api/export')) return exportResponder(url, init)
    return json({ error: { code: 'not_found', message: 'nope' } }, 404)
  })
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock')
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
})

const analyzeCalls = () => calls.filter((u) => u.pathname === '/api/analyze')
const lastAnalyze = () => analyzeCalls().at(-1)!.searchParams

async function renderLoaded() {
  const user = userEvent.setup()
  render(<App />)
  await screen.findByText('Hyderabad', { selector: '[data-testid=result-title]', exact: false })
  await screen.findByRole('option', { name: 'Delhi' })
  return user
}

describe('App', () => {
  it('runs the default analysis and renders API values', async () => {
    await renderLoaded()
    expect(screen.getByTestId('result-title')).toHaveTextContent('Hyderabad')
    expect(screen.getByTestId('metric-Heatwave events')).toHaveTextContent('7')
    expect(screen.getByTestId('metric-Heatwave days')).toHaveTextContent('31')
    expect(screen.getByTestId('metric-threshold')).toHaveTextContent('39.9 °C')
    expect(screen.getByText('95th pct threshold')).toBeInTheDocument()
    expect(screen.getByText(/7 heatwave event\(s\) totalling 31 heatwave day\(s\)/)).toBeInTheDocument()
    expect(screen.getByTestId('mk-verdict-Annual heatwave days')).toHaveTextContent(
      'Increasing monotonic trend detected, with the significance criterion met.',
    )
    const table = screen.getByRole('region', { name: 'Annual indicators table' })
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 36)
    expect(lastAnalyze().get('latitude')).toBe('17.385')
  })

  it('selecting a preset updates coordinates and marks results stale until re-run', async () => {
    const user = await renderLoaded()
    await user.selectOptions(screen.getByLabelText('Preset region'), 'delhi')
    expect(screen.getByLabelText('Latitude')).toHaveValue(28.6139)
    expect(screen.getByLabelText('Location label')).toHaveValue('Delhi')
    expect(screen.getByText(/The selection has changed/)).toBeInTheDocument()
    expect(screen.getByTestId('result-title')).toHaveTextContent('Hyderabad')

    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() => expect(screen.getByTestId('result-title')).toHaveTextContent('Delhi'))
    expect(lastAnalyze().get('latitude')).toBe('28.6139')
    expect(lastAnalyze().get('label')).toBe('Delhi')
    expect(screen.queryByText(/The selection has changed/)).not.toBeInTheDocument()
  })

  it('state presets select a lat-lon box', async () => {
    const user = await renderLoaded()
    await user.selectOptions(screen.getByLabelText('Preset region'), 'telangana')
    expect(screen.getByLabelText('South')).toHaveValue(15.8)
    expect(screen.getByTestId('rectangle')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() => expect(lastAnalyze().get('south')).toBe('15.8'))
    expect(lastAnalyze().get('east')).toBe('81.8')
    expect(lastAnalyze().has('latitude')).toBe(false)
  })

  it('map click selects a point and clears the preset label', async () => {
    const user = await renderLoaded()
    act(() => mapClick(20.12346, 75.98766))
    expect(screen.getByLabelText('Latitude')).toHaveValue(20.1235)
    expect(screen.getByLabelText('Longitude')).toHaveValue(75.9877)
    expect(screen.getByLabelText('Location label')).toHaveValue('')
    expect(screen.getByTestId('marker')).toHaveAttribute('data-center', '20.1235,75.9877')
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() => expect(lastAnalyze().get('latitude')).toBe('20.1235'))
  })

  it('box mode builds a normalised box from two map clicks', async () => {
    const user = await renderLoaded()
    await user.click(screen.getByRole('button', { name: /lat-lon box/i }))
    act(() => mapClick(19, 80))
    expect(screen.getByText(/First corner set/)).toBeInTheDocument()
    act(() => mapClick(18, 79))
    expect(screen.getByLabelText('South')).toHaveValue(18)
    expect(screen.getByLabelText('North')).toHaveValue(19)
    expect(screen.getByLabelText('West')).toHaveValue(79)
    expect(screen.getByLabelText('East')).toHaveValue(80)
  })

  it('switching map mode re-measures the map so no blank strip remains', async () => {
    const user = await renderLoaded()
    fakeMap.invalidateSize.mockClear()
    await user.click(screen.getByRole('button', { name: /lat-lon box/i }))
    await waitFor(() => expect(fakeMap.invalidateSize).toHaveBeenCalled())
  })

  it('manual coordinate entry is debounced and never triggers analysis by itself', async () => {
    const user = await renderLoaded()
    const before = analyzeCalls().length
    const lat = screen.getByLabelText('Latitude')
    await user.clear(lat)
    await user.type(lat, '12.5')
    expect(screen.getByText('Selected: 17.3850, 78.4867')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Selected: 12.5000, 78.4867')).toBeInTheDocument())
    expect(analyzeCalls().length).toBe(before)
  })

  it('year changes are validated and sent with the request', async () => {
    const user = await renderLoaded()
    await user.selectOptions(screen.getByLabelText('Start year'), '2010')
    await user.selectOptions(screen.getByLabelText('End year'), '2005')
    expect(screen.getByText('Start year must not be after end year.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run analysis/i })).toBeDisabled()

    await user.selectOptions(screen.getByLabelText('End year'), '2012')
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() => expect(lastAnalyze().get('start_year')).toBe('2010'))
    expect(lastAnalyze().get('end_year')).toBe('2012')
  })

  it('defaults to the fixed 1991-2020 reference baseline', async () => {
    const user = await renderLoaded()
    expect(screen.getByRole('radio', { name: /fixed reference period/i })).toBeChecked()
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() => expect(lastAnalyze().get('baseline')).toBe('fixed_reference'))
    expect(lastAnalyze().get('reference_start_year')).toBe('1991')
    expect(lastAnalyze().get('reference_end_year')).toBe('2020')
  })

  it('analysis-period baseline omits reference years', async () => {
    const user = await renderLoaded()
    await user.click(screen.getByLabelText('Analysis period'))
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() => expect(lastAnalyze().get('baseline')).toBe('analysis_period'))
    expect(lastAnalyze().get('reference_start_year')).toBeNull()
  })

  it('names the dataset in the results header', async () => {
    const user = await renderLoaded()
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    expect(await screen.findByTestId('result-dataset')).toHaveTextContent('Data: ERA5')
  })

  it('shows loading state and disables the run button during a request', async () => {
    const user = await renderLoaded()
    let release!: () => void
    analyzeResponder = (url) => new Promise((resolve) => (release = () => resolve(defaultAnalyze(url))))
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    const button = screen.getByRole('button', { name: /analysing/i })
    expect(button).toBeDisabled()
    expect(screen.getByText(/Fetching historical data/)).toBeInTheDocument()
    await act(async () => release())
    await waitFor(() => expect(screen.getByRole('button', { name: /run analysis/i })).toBeEnabled())
  })

  it('shows API errors with a working retry button', async () => {
    const user = await renderLoaded()
    analyzeResponder = async () =>
      json({ error: { code: 'upstream_unavailable', message: 'The weather data provider is currently unavailable.' } }, 503)
    await user.selectOptions(screen.getByLabelText('Preset region'), 'delhi')
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The weather data provider is currently unavailable.')

    analyzeResponder = defaultAnalyze
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(screen.getByTestId('result-title')).toHaveTextContent('Delhi'))
  })

  it('exports CSV and PDF for the displayed analysis, not unsaved edits', async () => {
    const user = await renderLoaded()
    await user.selectOptions(screen.getByLabelText('Preset region'), 'delhi')

    await user.click(screen.getByRole('button', { name: /export csv/i }))
    expect(await screen.findByText(/Downloaded climate-lens-test.csv/)).toBeInTheDocument()
    const csvCall = calls.find((u) => u.pathname === '/api/export.csv')!
    expect(csvCall.searchParams.get('label')).toBe('Hyderabad')
    expect(csvCall.searchParams.get('latitude')).toBe('17.385')

    await user.click(screen.getByRole('button', { name: /export pdf/i }))
    expect(await screen.findByText(/Downloaded climate-lens-test.pdf/)).toBeInTheDocument()
    expect(calls.some((u) => u.pathname === '/api/export.pdf')).toBe(true)
  })

  it('reports export failures', async () => {
    const user = await renderLoaded()
    exportResponder = async () => json({ error: { code: 'rate_limited', message: 'Too many requests.' } }, 429)
    await user.click(screen.getByRole('button', { name: /export pdf/i }))
    expect(await screen.findByText(/Too many requests/)).toBeInTheDocument()
  })

  it('preset dropdown follows the selection: map clicks and box mode switch it to Custom', async () => {
    const user = await renderLoaded()
    const preset = screen.getByLabelText('Preset region')
    expect(preset).toHaveValue('hyderabad')
    await user.selectOptions(preset, 'delhi')
    expect(preset).toHaveValue('delhi')
    act(() => mapClick(20, 76))
    expect(preset).toHaveValue('')
    await user.selectOptions(preset, 'delhi')
    await user.click(screen.getByRole('button', { name: /lat-lon box/i }))
    expect(preset).toHaveValue('')
  })

  it('validation errors clear as soon as the typed coordinate is fixed', async () => {
    const user = await renderLoaded()
    const lat = screen.getByLabelText('Latitude')
    await user.clear(lat)
    await user.type(lat, '95')
    expect(screen.getByText('Latitude must be between -90 and 90.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run analysis/i })).toBeDisabled()
    await user.clear(lat)
    expect(screen.getByText('Enter a number for every coordinate.')).toBeInTheDocument()
    await user.type(lat, '45')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run analysis/i })).toBeEnabled()
  })

  it('invalid typed coordinates never move the map or marker', async () => {
    const user = await renderLoaded()
    fakeMap.setView.mockClear()
    const lat = screen.getByLabelText('Latitude')
    await user.clear(lat)
    await user.type(lat, '99{Enter}')
    await new Promise((r) => setTimeout(r, 650))
    expect(screen.getByText('Latitude must be between -90 and 90.')).toBeInTheDocument()
    expect(fakeMap.setView).not.toHaveBeenCalled()
    expect(screen.getByTestId('marker')).toHaveAttribute('data-center', '17.385,78.4867')

    await user.clear(lat)
    await user.type(lat, '45{Enter}')
    await waitFor(() => expect(fakeMap.setView).toHaveBeenCalledWith([45, 78.4867], expect.any(Number)))
    expect(screen.getByTestId('marker')).toHaveAttribute('data-center', '45,78.4867')
  })

  it('renaming a preset location switches the dropdown to Custom selection', async () => {
    const user = await renderLoaded()
    const preset = screen.getByLabelText('Preset region')
    await user.selectOptions(preset, 'delhi')
    const label = screen.getByLabelText('Location label')
    await user.clear(label)
    await user.type(label, 'Phoenix')
    expect(preset).toHaveValue('')
    await user.clear(label)
    await user.type(label, 'Delhi')
    expect(preset).toHaveValue('delhi')
  })

  it('run uses typed coordinates even before the debounce commits them', async () => {
    const user = await renderLoaded()
    const lat = screen.getByLabelText('Latitude')
    await user.clear(lat)
    await user.type(lat, '12.5')
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() => expect(lastAnalyze().get('latitude')).toBe('12.5'))
  })

  it('typed coordinates move the map', async () => {
    const user = await renderLoaded()
    fakeMap.setView.mockClear()
    const lat = screen.getByLabelText('Latitude')
    await user.clear(lat)
    await user.type(lat, '12.5{Enter}')
    await waitFor(() => expect(fakeMap.setView).toHaveBeenCalledWith([12.5, 78.4867], expect.any(Number)))
  })

  it('export status resets when a different analysis is shown', async () => {
    const user = await renderLoaded()
    await user.click(screen.getByRole('button', { name: /export csv/i }))
    expect(await screen.findByText(/Downloaded climate-lens-test.csv/)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Preset region'), 'delhi')
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() => expect(screen.getByTestId('result-title')).toHaveTextContent('Delhi'))
    expect(screen.queryByText(/Downloaded/)).not.toBeInTheDocument()
  })

  it('sends percentile and minimum days, and labels results with them', async () => {
    const user = await renderLoaded()
    expect(lastAnalyze().get('percentile')).toBe('95')
    expect(lastAnalyze().get('min_duration_days')).toBe('3')
    expect(lastAnalyze().has('fill_gaps')).toBe(false)
    expect(screen.getByTestId('result-hazard')).toHaveTextContent('95th percentile · 3+ days')

    await user.selectOptions(screen.getByLabelText('Threshold percentile'), '90')
    const days = screen.getByLabelText('Minimum consecutive days')
    await user.clear(days)
    await user.type(days, '2')
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() => expect(lastAnalyze().get('percentile')).toBe('90'))
    expect(lastAnalyze().get('min_duration_days')).toBe('2')
    await waitFor(() => expect(screen.getByTestId('result-hazard')).toHaveTextContent('90th percentile · 2+ days'))
    expect(screen.getByText('90th pct threshold')).toBeInTheDocument()
  })

  it('rejects minimum days outside 2-10', async () => {
    const user = await renderLoaded()
    const days = screen.getByLabelText('Minimum consecutive days')
    await user.clear(days)
    await user.type(days, '11')
    expect(screen.getByText('Minimum consecutive days must be a whole number from 2 to 10.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run analysis/i })).toBeDisabled()
  })

  it('gap fill is off by default and sent only when ticked', async () => {
    const user = await renderLoaded()
    const box = screen.getByRole('checkbox', { name: /fill single-day gaps/i })
    expect(box).not.toBeChecked()
    expect(screen.getByTestId('dq-interpolated')).toHaveTextContent('0')
    await user.click(box)
    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() => expect(lastAnalyze().get('fill_gaps')).toBe('true'))
    await waitFor(() => expect(screen.getByTestId('dq-interpolated')).toHaveTextContent('3'))
    expect(screen.getByTestId('result-hazard')).toHaveTextContent('single-day gaps filled')
    const start = Number(lastAnalyze().get('start_year'))
    expect(screen.getByTestId(`filled-${start}`)).toHaveTextContent('3')
    expect(screen.getByTestId('filled-note')).toHaveTextContent(`1 heatwave event includes a filled day (${start}-05-08)`)
    expect(screen.getByTestId('dq-filled-summary')).toHaveTextContent('Filled days (showing 2 of 3)')
  })

  it('shows no Filled column while gap fill is off', async () => {
    await renderLoaded()
    const table = screen.getByRole('region', { name: 'Annual indicators table' })
    expect(within(table).queryByRole('columnheader', { name: 'Filled' })).not.toBeInTheDocument()
    expect(screen.queryByTestId('filled-note')).not.toBeInTheDocument()
  })

  it('shows the quality accounting check and days received', async () => {
    await renderLoaded()
    expect(screen.getByTestId('dq-received')).toHaveTextContent('1,096')
    const check = screen.getByTestId('dq-accounting')
    expect(check).toHaveClass('ok')
    expect(check).toHaveTextContent('1,096 calendar days = 1,096 valid + 0 missing + 0 implausible')
    expect(check).toHaveTextContent('1,096 received = 1,096 valid + 0 null + 0 implausible')
  })

  it('says when the outlier list is truncated', async () => {
    analyzeResponder = async (url) => {
      const body = (await (await defaultAnalyze(url)).json()) as ReturnType<typeof makeAnalysis>
      body.data_quality.outlier_total = 22
      body.data_quality.analysis.outlier_days = 22
      return json(body)
    }
    await renderLoaded()
    expect(screen.getByTestId('dq-outlier-summary')).toHaveTextContent('Most extreme flagged days (showing 2 of 22)')
  })

  it('explains the default choices', async () => {
    await renderLoaded()
    const note = screen.getByTestId('defaults-note')
    expect(note).toHaveTextContent('Why these defaults?')
    expect(note).toHaveTextContent('95th percentile')
    expect(note).toHaveTextContent('1991–2020 baseline')
  })

  it('shows a wake-up message when a request takes longer than 3 s', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      let release: () => void = () => undefined
      analyzeResponder = (url) =>
        new Promise((resolve) => {
          release = () => resolve(defaultAnalyze(url))
        })
      render(<App />)
      expect(screen.queryByTestId('wake-note')).not.toBeInTheDocument()
      await act(async () => {
        vi.advanceTimersByTime(3100)
      })
      expect(screen.getByTestId('wake-note')).toHaveTextContent('Waking the server, this can take about 30 s')
      await act(async () => {
        release()
      })
      await waitFor(() => expect(screen.queryByTestId('wake-note')).not.toBeInTheDocument())
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows the data quality report with counts, per-year flags and outliers', async () => {
    const user = await renderLoaded()
    const panel = screen.getByRole('region', { name: 'Data quality report' })
    expect(within(panel).getByTestId('dq-missing')).toHaveTextContent('0')
    expect(within(panel).getByTestId('dq-duplicate')).toHaveTextContent('0')
    expect(within(panel).getByTestId('dq-implausible')).toHaveTextContent('0')
    expect(within(panel).getByTestId('dq-outlier')).toHaveTextContent('2')
    await user.click(within(panel).getByText(/Per-year breakdown \(1 year with flags\)/))
    expect(within(panel).getAllByRole('row')).toHaveLength(2)
    await user.click(within(panel).getByText(/Most extreme flagged days \(2\)/))
    expect(within(panel).getByText(/12\.3 °C \(robust z -5\.2\)/)).toBeInTheDocument()
  })

  it('shows a limitations note linked to the sources list', async () => {
    await renderLoaded()
    const note = screen.getByTestId('limitations')
    expect(note).toHaveTextContent('not from weather stations')
    expect(note).toHaveTextContent('relative to this location')
    expect(note).toHaveTextContent('not proof of a cause')
    expect(within(note).getByRole('link', { name: /sources & limitations/i })).toHaveAttribute('href', '#limitations')
    expect(document.getElementById('limitations')).not.toBeNull()
  })

  it('reversed reference years show the ordering error, not the span error', async () => {
    const user = await renderLoaded()
    await user.selectOptions(screen.getByLabelText('Reference start year'), '2020')
    await user.selectOptions(screen.getByLabelText('Reference end year'), '1991')
    expect(screen.getByText('Reference start year must not be after reference end year.')).toBeInTheDocument()
    expect(screen.queryByText(/must span at least 10 years/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run analysis/i })).toBeDisabled()
  })

  it('unsupported hazards are visible but disabled', async () => {
    await renderLoaded()
    expect(screen.getByRole('option', { name: /drought/i })).toBeDisabled()
    expect(screen.getByLabelText('Hazard type')).toHaveValue('heatwave')
  })

  describe('city search', () => {
    const geocodeCalls = () => calls.filter((u) => u.pathname === '/api/geocode')

    it('picking a result sets coordinates, label and map, and runs on that point', async () => {
      const user = await renderLoaded()
      fakeMap.setView.mockClear()
      await user.type(screen.getByRole('combobox', { name: /search city/i }), 'Phoenix')
      const option = await screen.findByRole('option', { name: /Phoenix, Arizona, United States/ })
      expect(geocodeCalls().at(-1)!.searchParams.get('name')).toBe('Phoenix')
      await user.click(option)

      expect(screen.getByLabelText('Latitude')).toHaveValue(33.44838)
      expect(screen.getByLabelText('Longitude')).toHaveValue(-112.07404)
      expect(screen.getByLabelText('Location label')).toHaveValue('Phoenix, Arizona, United States')
      expect(screen.getByLabelText('Preset region')).toHaveValue('')
      await waitFor(() => expect(fakeMap.setView).toHaveBeenCalledWith([33.44838, -112.07404], expect.any(Number)))

      await user.click(screen.getByRole('button', { name: /run analysis/i }))
      await waitFor(() => expect(lastAnalyze().get('label')).toBe('Phoenix, Arizona, United States'))
      expect(lastAnalyze().get('latitude')).toBe('33.4484')
      await waitFor(() => expect(screen.getByTestId('result-title')).toHaveTextContent('Phoenix'))
    })

    it('keyboard selection picks the highlighted result', async () => {
      const user = await renderLoaded()
      const box = screen.getByRole('combobox', { name: /search city/i })
      await user.type(box, 'Phoe')
      await screen.findByRole('option', { name: /Oregon/ })
      await user.keyboard('{ArrowDown}{Enter}')
      expect(screen.getByLabelText('Location label')).toHaveValue('Phoenix, Oregon, United States')
      expect(screen.getByLabelText('Latitude')).toHaveValue(42.27541)
    })

    it('does not search for fewer than 2 characters and debounces typing', async () => {
      const user = await renderLoaded()
      const box = screen.getByRole('combobox', { name: /search city/i })
      await user.type(box, 'P')
      await new Promise((r) => setTimeout(r, 500))
      expect(geocodeCalls()).toHaveLength(0)
      await user.type(box, 'hoenix')
      await screen.findByRole('option', { name: /Arizona/ })
      expect(geocodeCalls()).toHaveLength(1)
    })

    it('shows a no-match message and leaves the selection alone', async () => {
      const user = await renderLoaded()
      await user.type(screen.getByRole('combobox', { name: /search city/i }), 'Zzqqxx')
      expect(await screen.findByText(/No places found for “Zzqqxx”/)).toBeInTheDocument()
      expect(screen.getByLabelText('Location label')).toHaveValue('Hyderabad')
    })

    it('shows the API error message when search fails', async () => {
      geocodeResponder = async () =>
        json({ error: { code: 'rate_limited', message: 'Too many requests. Limit is 60 per 60 seconds.' } }, 429)
      const user = await renderLoaded()
      await user.type(screen.getByRole('combobox', { name: /search city/i }), 'Phoenix')
      expect(await screen.findByText(/Too many requests/)).toBeInTheDocument()
      expect(screen.getByLabelText('Location label')).toHaveValue('Hyderabad')
    })
  })
})
