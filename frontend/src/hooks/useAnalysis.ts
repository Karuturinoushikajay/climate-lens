import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchAnalysis, type QueryParams } from '../api/client'
import type { AnalysisResponse } from '../api/types'

export type AnalysisState =
  | { status: 'idle' }
  | { status: 'loading'; params: QueryParams; previous?: { data: AnalysisResponse; params: QueryParams } }
  | { status: 'success'; data: AnalysisResponse; params: QueryParams }
  | { status: 'error'; error: string; params: QueryParams; previous?: { data: AnalysisResponse; params: QueryParams } }

/** Runs analyses, aborting superseded requests so a slow older response can never overwrite a newer one. */
export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({ status: 'idle' })
  const controller = useRef<AbortController | null>(null)
  const requestId = useRef(0)

  const run = useCallback((params: QueryParams) => {
    controller.current?.abort()
    const ctrl = new AbortController()
    controller.current = ctrl
    const id = ++requestId.current

    setState((prev) => ({
      status: 'loading',
      params,
      previous: prev.status === 'success' ? { data: prev.data, params: prev.params } : 'previous' in prev ? prev.previous : undefined,
    }))

    fetchAnalysis(params, ctrl.signal)
      .then((data) => {
        if (id === requestId.current) setState({ status: 'success', data, params })
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError' || id !== requestId.current) return
        setState((prev) => ({
          status: 'error',
          error: err.message || 'Analysis failed.',
          params,
          previous: prev.status === 'loading' ? prev.previous : undefined,
        }))
      })
  }, [])

  useEffect(() => () => controller.current?.abort(), [])

  return { state, run }
}
