import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { MockEventSource } from './test/setup'

const health = {
  ok: true,
  service: 'drift-api',
  environment: 'test',
  build_revision: 'test-revision',
  reasoning_backend: 'deterministic',
  gemini_model: 'gemini-3.5-flash',
  state_backend: 'memory',
  action_mode: 'dry-run',
  live_actions_ready: false,
  cloud: { region: 'us-central1', pubsub_topic: 'drift-incidents' },
}

const incident = {
  incident_id: 'inc-1234567890',
  service: 'release-guardian',
  stage: 'awaiting_review',
  severity: 'critical',
  summary: 'Unsafe recommendation after missing evidence.',
  updated_at: '2026-08-08T12:00:00Z',
  demo: true,
}

const run = {
  ...incident,
  source_event_id: 'evt-1',
  source: 'drift.demo',
  trace_id: 'trace-1',
  created_at: incident.updated_at,
  event: {
    event_id: 'evt-1', source: 'drift.demo', service: incident.service,
    occurred_at: incident.updated_at, trace_id: 'trace-1', input_text: 'input',
    output_text: 'unsafe output', expected_behavior: 'safe behavior', tool_events: [],
    target: { owner: 'owner', repo: 'drift', base_branch: 'main', candidate_path: 'demo_target/prompts/system.md', baseline_content: 'baseline' },
    metadata: {}, demo: true,
  },
  triage: { severity: 'critical', category: 'unsafe_action', confidence: 0.96, summary: incident.summary, evidence: [], route: 'remediate' },
  investigation: null, proposal: null, validation: null, actions: [], issue_url: null,
  pull_request_url: null, branch_name: null, failure: null,
}

function response(body: unknown, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    statusText: 'error',
    json: () => Promise.resolve(body),
  } as Response)
}

afterEach(() => vi.unstubAllGlobals())

describe('Drift operations room', () => {
  it('loads incidents, filters severity, and reports SSE reconnection state', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string | URL) => {
      const path = String(url)
      if (path === '/healthz') return response(health)
      if (path === '/v1/incidents') return response([incident])
      if (path.endsWith('/events')) return response([])
      return response(run)
    }))

    render(<App />)
    expect(screen.getByText('Reconnecting event stream')).toBeInTheDocument()
    expect((await screen.findAllByText('release-guardian')).length).toBeGreaterThan(0)
    expect(screen.getByRole('group', { name: 'Severity filter' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'high' }))
    expect(screen.getByText('No incidents yet.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'critical' }))
    expect(screen.getAllByText('release-guardian').length).toBeGreaterThan(0)

    act(() => MockEventSource.instances[0].onopen?.())
    expect(screen.getByText('Event stream connected')).toBeInTheDocument()
    act(() => MockEventSource.instances[0].onerror?.())
    expect(screen.getByText('Reconnecting event stream')).toBeInTheDocument()
  })

  it('renders an API failure without hiding the proof trigger', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({ detail: 'Datastore unavailable' }, false)))
    render(<App />)
    expect(await screen.findByText('Datastore unavailable')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Trigger live proof/ }).length).toBeGreaterThan(0)
    await waitFor(() => expect(screen.getByText('Waiting for operational drift.')).toBeInTheDocument())
  })
})
