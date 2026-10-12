import type { AnalysisResponse, ApiErrorBody, HealthResponse, RegionsResponse } from './types'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')

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

export async function fetchAnalysis(params: QueryParams, signal?: AbortSignal): Promise<AnalysisResponse> {
  return (await request('/api/analyze', params, signal)).json()
}

export async function fetchRegions(signal?: AbortSignal): Promise<RegionsResponse> {
  return (await request('/api/regions', undefined, signal)).json()
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return (await request('/api/health', undefined, signal)).json()
}

export function filenameFromDisposition(header: string | null, fallback: string): string {
  const match = header?.match(/filename="?([^";]+)"?/i)
  return match ? match[1] : fallback
}

export async function downloadExport(kind: 'csv' | 'pdf', params: QueryParams): Promise<string> {
  const response = await request(`/api/export.${kind}`, params)
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
