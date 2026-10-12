import type { AnalysisResponse, ApiErrorBody, GeocodeResponse, HealthResponse, RegionsResponse } from './types'

export function normalizeBaseUrl(raw: string | undefined): string {
  let url = (raw ?? '').trim()
  if (!url) url = 'http://localhost:8000'
  if (!/^https?:\/\//i.test(url)) url = `${/^(localhost|127\.0\.0\.1)(:|$)/i.test(url) ? 'http' : 'https'}://${url}`
  return url.replace(/\/+$/, '')
}

export const API_BASE_URL = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL)

export type QueryParams = Record<string, string | number>

export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export function buildUrl(path: string, params?: QueryParams): string {
  const qs = params
    ? '?' +
      new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)] as [string, string])).toString()
    : ''
  return `${API_BASE_URL}${path}${qs}`
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = 'http_error'
  let message = `Request failed with status ${response.status}.`
  try {
    const body = (await response.json()) as ApiErrorBody
    if (body?.error?.message) {
      code = body.error.code
      message = body.error.message
    }
  } catch {
    /* non-JSON error body */
  }
  if (response.status === 429) {
    const retry = response.headers.get('Retry-After')
    if (retry) message += ` Retry in about ${retry} s.`
  }
  return new ApiError(response.status, code, message)
}

async function request(path: string, params?: QueryParams, signal?: AbortSignal): Promise<Response> {
  let response: Response
  try {
    response = await fetch(buildUrl(path, params), { signal, headers: { Accept: 'application/json' } })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError(0, 'network_error', 'Could not reach the Climate Lens API. Check your connection and try again.')
  }
  if (!response.ok) throw await toApiError(response)
  return response
}

async function parseJson<T>(response: Response): Promise<T> {
  const type = response.headers.get('Content-Type') ?? ''
  if (!type.includes('json')) {
    throw new ApiError(
      response.status,
      'not_api_response',
      `The API address (${API_BASE_URL}) returned a web page instead of data. ` +
        'Set VITE_API_BASE_URL to the backend URL (e.g. https://your-api.onrender.com) and rebuild the frontend.',
    )
  }
  return (await response.json()) as T
}

export async function fetchAnalysis(params: QueryParams, signal?: AbortSignal): Promise<AnalysisResponse> {
  return parseJson(await request('/api/analyze', params, signal))
}

export async function fetchRegions(signal?: AbortSignal): Promise<RegionsResponse> {
  return parseJson(await request('/api/regions', undefined, signal))
}

export async function searchPlaces(name: string, signal?: AbortSignal): Promise<GeocodeResponse> {
  return parseJson(await request('/api/geocode', { name, count: 6 }, signal))
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return parseJson(await request('/api/health', undefined, signal))
}

export function filenameFromDisposition(header: string | null, fallback: string): string {
  const match = header?.match(/filename="?([^";]+)"?/i)
  return match ? match[1] : fallback
}

export async function downloadExport(kind: 'csv' | 'pdf', params: QueryParams): Promise<string> {
  const response = await request(`/api/export.${kind}`, params)
  if ((response.headers.get('Content-Type') ?? '').includes('text/html')) {
    throw new ApiError(response.status, 'not_api_response', `The API address (${API_BASE_URL}) returned a web page instead of a ${kind.toUpperCase()} file.`)
  }
  const blob = await response.blob()
  const filename = filenameFromDisposition(response.headers.get('Content-Disposition'), `climate-lens.${kind}`)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return filename
}
