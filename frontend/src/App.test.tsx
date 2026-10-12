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
  return Promise.resolve(
    json(
      makeAnalysis(
        label,
        Number(p.get('latitude') ?? 0),
        Number(p.get('longitude') ?? 0),
        Number(p.get('start_year')),
        Number(p.get('end_year')),
      ),
    ),
  )
}

let analyzeResponder: Responder
let exportResponder: Responder
let calls: URL[]

beforeEach(() => {
  calls = []
  analyzeResponder = defaultAnalyze
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
    expect(screen.getByTestId('metric-95th pct threshold')).toHaveTextContent('39.9 °C')
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

  it('unsupported hazards are visible but disabled', async () => {
    await renderLoaded()
    expect(screen.getByRole('option', { name: /drought/i })).toBeDisabled()
    expect(screen.getByLabelText('Hazard type')).toHaveValue('heatwave')
  })
})
