import {
  Activity,
  ArrowUpRight,
  BellRing,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  Cloud,
  Code2,
  GitPullRequest,
  Radio,
  RefreshCw,
  ShieldCheck,
  Siren,
  TerminalSquare,
  XCircle,
  Zap,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { Health, IncidentSummary, WorkflowEvent, WorkflowRun } from './types'

const stageOrder = [
  'ingested',
  'deduplicated',
  'triaged',
  'investigated',
  'routed',
  'issue_created',
  'candidate_generated',
  'validated',
  'pr_opened',
  'notified',
  'awaiting_review',
]

const titleCase = (value: string) => value.replaceAll('_', ' ').replace(/\b\w/g, (m) => m.toUpperCase())
const compactId = (value: string) => value.replace('inc-', '').slice(0, 8).toUpperCase()
const percent = (value: number) => `${Math.round(value * 100)}%`

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

function SeverityPill({ severity }: { severity: string | null | undefined }) {
  return <span className={`severity severity-${severity || 'pending'}`}>{severity || 'pending'}</span>
}

function App() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [events, setEvents] = useState<WorkflowEvent[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [connected, setConnected] = useState(false)

  const refreshIncidents = useCallback(async () => {
    const data = await getJson<IncidentSummary[]>('/v1/incidents')
    setIncidents(data)
    setSelected((current) => current || data[0]?.incident_id || null)
  }, [])

  const loadRun = useCallback(async (id: string) => {
    const [detail, timeline] = await Promise.all([
      getJson<WorkflowRun>(`/v1/incidents/${id}`),
      getJson<WorkflowEvent[]>(`/v1/incidents/${id}/events`),
    ])
    setRun(detail)
    setEvents(timeline)
  }, [])

  useEffect(() => {
    Promise.all([refreshIncidents(), getJson<Health>('/healthz').then(setHealth)]).catch((err) =>
      setError(err.message),
    )
  }, [refreshIncidents])

  useEffect(() => {
    if (selected) loadRun(selected).catch((err) => setError(err.message))
  }, [selected, loadRun])

  useEffect(() => {
    const stream = new EventSource('/v1/events/stream')
    stream.onopen = () => setConnected(true)
    stream.onerror = () => setConnected(false)
    stream.addEventListener('workflow', (message) => {
      const event = JSON.parse((message as MessageEvent).data) as WorkflowEvent
      setEvents((current) =>
        event.incident_id === selected ? [...current, event] : current,
      )
      refreshIncidents().catch(() => undefined)
      if (event.incident_id === selected) loadRun(selected).catch(() => undefined)
    })
    return () => stream.close()
  }, [selected, loadRun, refreshIncidents])

  const triggerDemo = async () => {
    let token = sessionStorage.getItem('drift-demo-token') || ''
    if (!token) token = window.prompt('Enter the protected demo trigger token') || ''
    if (!token) return
    sessionStorage.setItem('drift-demo-token', token)
    setLoading(true)
    setError('')
    try {
      const result = await getJson<{ incident_id: string }>('/v1/demo/incidents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: '{}',
      })
      await refreshIncidents()
      setSelected(result.incident_id)
      await loadRun(result.incident_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Demo failed')
    } finally {
      setLoading(false)
    }
  }

  const filtered = useMemo(
    () => incidents.filter((item) => filter === 'all' || item.severity === filter),
    [incidents, filter],
  )
  const completed = incidents.filter((item) => item.stage === 'awaiting_review').length
  const liveActions = run?.actions.filter((item) => item.status === 'succeeded').length || 0
  const messageId = run?.event.metadata.pubsub_message_id
  const displayedMessageId = typeof messageId === 'string'
    ? messageId
    : run?.demo ? 'demo trigger' : 'not supplied'

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Drift home">
          <span className="brand-mark"><Radio size={21} /></span>
          <span>DRIFT</span>
          <small>OPERATIONS ROOM</small>
        </a>
        <div className="topbar-status">
          <span className={`connection-dot ${connected ? 'online' : ''}`} />
          {connected ? 'Event stream connected' : 'Reconnecting event stream'}
          <span className="divider" />
          <span>{health?.gemini_model || 'loading model'}</span>
        </div>
        <button className="trigger-button" onClick={triggerDemo} disabled={loading}>
          {loading ? <RefreshCw className="spin" size={17} /> : <Zap size={17} />}
          {loading ? 'Running workflow' : 'Trigger live proof'}
        </button>
      </header>

      <main id="top">
        <section className="hero">
          <div>
            <div className="eyebrow"><ShieldCheck size={15} /> Proof-carrying remediation</div>
            <h1>From agent failure to<br /><span>validated pull request.</span></h1>
            <p>
              Drift catches failed AI workflows, finds the evidence gap, validates a safe fix,
              and carries it to GitHub and Slack—without touching production.
            </p>
          </div>
          <div className="hero-flow" aria-label="Drift workflow">
            {['EVENT', 'TRIAGE', 'REPLAY', 'DRAFT PR'].map((label, index) => (
              <div className="flow-item" key={label}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{label}</strong>
                {index < 3 && <ChevronRight size={16} />}
              </div>
            ))}
          </div>
        </section>

        {error && <div className="error-banner"><XCircle size={18} /> {error}</div>}

        <section className="metrics" aria-label="Workflow metrics">
          <article><Activity /><div><strong>{incidents.length}</strong><span>Incidents observed</span></div></article>
          <article><GitPullRequest /><div><strong>{completed}</strong><span>Awaiting human review</span></div></article>
          <article><TerminalSquare /><div><strong>{liveActions}</strong><span>Action receipts</span></div></article>
          <article><Cloud /><div><strong>{health?.cloud.region || '—'}</strong><span>Cloud Run region</span></div></article>
        </section>

        <section className="workspace">
          <aside className="incident-rail">
            <div className="section-heading">
              <div><span>INCIDENT QUEUE</span><h2>Incoming drift</h2></div>
              <button className="icon-button" onClick={() => refreshIncidents()} aria-label="Refresh incidents"><RefreshCw size={16} /></button>
            </div>
            <div className="filters" role="group" aria-label="Severity filter">
              {['all', 'critical', 'high', 'medium'].map((item) => (
                <button className={filter === item ? 'active' : ''} onClick={() => setFilter(item)} key={item}>{item}</button>
              ))}
            </div>
            <div className="incident-list">
              {filtered.length === 0 && (
                <div className="empty-rail"><CircleDashed size={25} /><p>No incidents yet.</p><span>Trigger the proof workflow to populate the room.</span></div>
              )}
              {filtered.map((incident) => (
                <button
                  className={`incident-card ${selected === incident.incident_id ? 'selected' : ''}`}
                  onClick={() => setSelected(incident.incident_id)}
                  key={incident.incident_id}
                >
                  <div><SeverityPill severity={incident.severity} /><time>{new Date(incident.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></div>
                  <strong>{incident.service}</strong>
                  <p>{incident.summary}</p>
                  <footer><span>#{compactId(incident.incident_id)}</span><span>{titleCase(incident.stage)}</span></footer>
                </button>
              ))}
            </div>
          </aside>

          <section className="incident-detail">
            {!run ? <EmptyDetail trigger={triggerDemo} /> : (
              <>
                <header className="detail-header">
                  <div>
                    <div className="detail-kicker">
                      <SeverityPill severity={run.triage?.severity} />
                      {run.demo && <span className="demo-badge">DEMO SOURCE</span>}
                      <span>#{compactId(run.incident_id)}</span>
                    </div>
                    <h2>{run.service}</h2>
                    <p>{run.triage?.summary || 'Incident is being processed.'}</p>
                  </div>
                  <div className="terminal-state">
                    <span>CURRENT STATE</span>
                    <strong>{titleCase(run.stage)}</strong>
                  </div>
                </header>

                <div className="timeline" aria-label="Workflow timeline">
                  {stageOrder.map((stage, index) => {
                    const event = events.find((item) => item.stage === stage)
                    const currentIndex = stageOrder.indexOf(run.stage)
                    const done = Boolean(event) || currentIndex > index
                    return (
                      <div className={`timeline-step ${done ? 'done' : ''} ${run.stage === stage ? 'current' : ''}`} key={stage}>
                        <span className="timeline-icon">{done ? <Check size={13} /> : index + 1}</span>
                        <div><strong>{titleCase(stage)}</strong><small>{event?.detail || 'Waiting'}</small></div>
                      </div>
                    )
                  })}
                </div>

                <div className="detail-grid">
                  <article className="panel evidence-panel">
                    <PanelTitle icon={<Siren size={17} />} label="Evidence, not intuition" meta={run.trace_id} />
                    <div className="evidence-block bad"><span>OBSERVED</span><p>{run.event.output_text}</p></div>
                    <div className="evidence-block expected"><span>EXPECTED</span><p>{run.event.expected_behavior}</p></div>
                    {run.investigation && <div className="root-cause"><strong>Root cause</strong><p>{run.investigation.root_cause}</p></div>}
                  </article>

                  <article className="panel score-panel">
                    <PanelTitle icon={<ShieldCheck size={17} />} label="Replay gate" meta={run.validation?.passed ? 'PASSED' : 'PENDING'} />
                    <div className="score-comparison">
                      <div><span>BASELINE</span><strong>{run.validation ? percent(run.validation.before_pass_rate) : '—'}</strong></div>
                      <ChevronRight />
                      <div className="candidate-score"><span>CANDIDATE</span><strong>{run.validation ? percent(run.validation.after_pass_rate) : '—'}</strong></div>
                    </div>
                    <div className="case-list">
                      {run.validation?.cases.map((item) => (
                        <div key={item.name}>
                          {item.after_passed ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                          <span>{titleCase(item.name)}</span>
                          <small>{item.before_passed ? 'pass' : 'fail'} → {item.after_passed ? 'pass' : 'fail'}</small>
                        </div>
                      )) || <p className="muted">Replay evidence appears after a candidate is generated.</p>}
                    </div>
                  </article>

                  <article className="panel action-panel">
                    <PanelTitle icon={<Bot size={17} />} label="Action ledger" meta={`${run.actions.length} RECEIPTS`} />
                    <div className="action-list">
                      {run.actions.map((action) => (
                        <div className="action-row" key={action.idempotency_key}>
                          <span className={`action-status ${action.status}`}>{action.status === 'succeeded' ? <Check size={13} /> : <XCircle size={13} />}</span>
                          <div><strong>{titleCase(action.action_kind)}</strong><small>{action.attempts} attempt{action.attempts === 1 ? '' : 's'}</small></div>
                          {action.external_url && <a href={action.external_url} target="_blank" rel="noreferrer" aria-label={`Open ${action.action_kind}`}><ArrowUpRight size={15} /></a>}
                        </div>
                      ))}
                      {run.actions.length === 0 && <p className="muted">No external actions were required.</p>}
                    </div>
                  </article>

                  <article className="panel cloud-panel">
                    <PanelTitle icon={<Cloud size={17} />} label="Google Cloud proof" meta={health?.build_revision || 'DEV'} />
                    <dl>
                      <div><dt>Runtime</dt><dd>Cloud Run · {health?.cloud.region || 'not configured'}</dd></div>
                      <div><dt>Revision</dt><dd>{health?.build_revision || 'dev'}</dd></div>
                      <div><dt>Event bus</dt><dd>{health?.cloud.pubsub_topic || 'drift-incidents'}</dd></div>
                      <div><dt>Message ID</dt><dd>{displayedMessageId}</dd></div>
                      <div><dt>State</dt><dd>{health?.state_backend || 'memory'}</dd></div>
                      <div><dt>Reasoning</dt><dd>{health?.reasoning_backend || 'loading'}</dd></div>
                      <div><dt>Actions</dt><dd>{health?.action_mode || 'dry-run'}</dd></div>
                    </dl>
                  </article>
                </div>

                {run.proposal && (
                  <article className="panel diff-panel">
                    <PanelTitle icon={<Code2 size={17} />} label="Constrained remediation" meta={run.proposal.target_path} />
                    <p>{run.proposal.rationale}</p>
                    <pre>{run.proposal.unified_diff}</pre>
                    <footer>
                      <span><ShieldCheck size={15} /> Allow-listed path · {run.proposal.risk} risk</span>
                      {run.pull_request_url && <a className="pr-link" href={run.pull_request_url} target="_blank" rel="noreferrer"><GitPullRequest size={16} /> Open draft pull request <ArrowUpRight size={15} /></a>}
                    </footer>
                  </article>
                )}
              </>
            )}
          </section>
        </section>
      </main>
      <footer className="page-footer"><span>DRIFT / TASKMASTER</span><span>Gemini 3.5 Flash · Google ADK · Cloud Run · Pub/Sub · Firestore</span><span><BellRing size={14} /> Human approval stays in the loop</span></footer>
    </div>
  )
}

function PanelTitle({ icon, label, meta }: { icon: React.ReactNode; label: string; meta: string }) {
  return <header className="panel-title"><div>{icon}<span>{label}</span></div><small>{meta}</small></header>
}

function EmptyDetail({ trigger }: { trigger: () => void }) {
  return (
    <div className="empty-detail">
      <span className="radar"><Radio size={39} /></span>
      <div className="eyebrow">System ready</div>
      <h2>Waiting for operational drift.</h2>
      <p>Publish an incident to Pub/Sub or run the protected deterministic proof workflow.</p>
      <button className="trigger-button" onClick={trigger}><Zap size={17} /> Trigger live proof</button>
    </div>
  )
}

export default App
