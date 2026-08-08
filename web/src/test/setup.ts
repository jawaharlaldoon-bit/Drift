import '@testing-library/jest-dom/vitest'
import { beforeEach } from 'vitest'

class MockEventSource extends EventTarget {
  static instances: MockEventSource[] = []
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  readonly url: string

  constructor(url: string | URL) {
    super()
    this.url = String(url)
    MockEventSource.instances.push(this)
  }

  close() {}
}

Object.defineProperty(globalThis, 'EventSource', {
  configurable: true,
  writable: true,
  value: MockEventSource,
})

beforeEach(() => {
  MockEventSource.instances = []
  sessionStorage.clear()
})

export { MockEventSource }
