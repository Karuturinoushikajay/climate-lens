import { describe, expect, it, vi } from 'vitest'
import { ApiError, buildUrl, fetchAnalysis, filenameFromDisposition, normalizeBaseUrl } from './client'

describe('api client', () => {
  it('builds URLs with encoded query parameters', () => {
    expect(buildUrl('/api/analyze', { label: 'A & B', start_year: 1990 })).toBe(
      'http://localhost:8000/api/analyze?label=A+%26+B&start_year=1990',
    )
  })

  it('extracts filenames from Content-Disposition', () => {
    expect(filenameFromDisposition('attachment; filename="climate-lens-x-1990-2020.csv"', 'f')).toBe(
      'climate-lens-x-1990-2020.csv',
    )
    expect(filenameFromDisposition(null, 'fallback.pdf')).toBe('fallback.pdf')
  })

  it('surfaces structured API errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'validation_error', message: 'start_year must not be after end_year.' } }), {
        status: 422,
      }),
    )
    await expect(fetchAnalysis({})).rejects.toMatchObject({
      status: 422,
      code: 'validation_error',
      message: 'start_year must not be after end_year.',
    })
  })

  it('adds retry hint on rate limiting', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'rate_limited', message: 'Too many requests.' } }), {
        status: 429,
        headers: { 'Retry-After': '42' },
      }),
    )
    await expect(fetchAnalysis({})).rejects.toThrow('Too many requests. Retry in about 42 s.')
  })

  it('normalizes the configured API base URL', () => {
    expect(normalizeBaseUrl(undefined)).toBe('http://localhost:8000')
    expect(normalizeBaseUrl('  ')).toBe('http://localhost:8000')
    expect(normalizeBaseUrl('climate-lens-api.onrender.com/')).toBe('https://climate-lens-api.onrender.com')
    expect(normalizeBaseUrl('localhost:8010')).toBe('http://localhost:8010')
    expect(normalizeBaseUrl('https://api.example.com//')).toBe('https://api.example.com')
  })

  it('explains when the API address serves HTML instead of JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('<!doctype html><html></html>', { status: 200, headers: { 'Content-Type': 'text/html' } }),
    )
    const err = await fetchAnalysis({}).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('not_api_response')
    expect(err.message).toContain('VITE_API_BASE_URL')
  })

  it('maps network failures to a friendly error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const err = await fetchAnalysis({}).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('network_error')
  })
})
