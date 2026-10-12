import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { makeAnalysis } from '../test/fixtures'
import { useAnalysis } from './useAnalysis'

describe('useAnalysis', () => {
  it('aborts superseded requests so a slow older response never wins', async () => {
    const aborted: string[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const label = new URL(String(input)).searchParams.get('label')!
      const delay = label === 'Slow' ? 200 : 10
      return new Promise((resolve, reject) => {
        const t = setTimeout(() => resolve(new Response(JSON.stringify(makeAnalysis(label)))), delay)
        init?.signal?.addEventListener('abort', () => {
          clearTimeout(t)
          aborted.push(label)
          reject(new DOMException('aborted', 'AbortError'))
        })
      })
    })

    const { result } = renderHook(() => useAnalysis())
    act(() => result.current.run({ label: 'Slow' }))
    act(() => result.current.run({ label: 'Fast' }))

    await waitFor(() => expect(result.current.state.status).toBe('success'))
    await new Promise((r) => setTimeout(r, 250))
    const state = result.current.state
    expect(state.status === 'success' && state.data.region.label).toBe('Fast')
    expect(aborted).toEqual(['Slow'])
  })

  it('keeps the previous result available while loading and after an error', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(makeAnalysis('First'))))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { code: 'upstream_timeout', message: 'Timed out.' } }), { status: 504 }),
      )
    const { result } = renderHook(() => useAnalysis())
    act(() => result.current.run({ label: 'First' }))
    await waitFor(() => expect(result.current.state.status).toBe('success'))
    act(() => result.current.run({ label: 'Second' }))
    await waitFor(() => expect(result.current.state.status).toBe('error'))
    const state = result.current.state
    expect(state.status === 'error' && state.error).toBe('Timed out.')
    expect(state.status === 'error' && state.previous?.data.region.label).toBe('First')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
