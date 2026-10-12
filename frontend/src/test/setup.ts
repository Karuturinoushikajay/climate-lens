import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

if (!URL.createObjectURL) URL.createObjectURL = vi.fn(() => 'blob:mock')
if (!URL.revokeObjectURL) URL.revokeObjectURL = vi.fn()

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
