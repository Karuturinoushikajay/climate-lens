import { useSyncExternalStore } from 'react'
import { hasSlowRequest, subscribeSlowRequests } from '../api/client'

export function useSlowRequests(): boolean {
  return useSyncExternalStore(subscribeSlowRequests, hasSlowRequest)
}
