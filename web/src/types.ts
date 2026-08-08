export type Severity = 'critical' | 'high' | 'medium' | 'low'

export interface IncidentSummary {
  incident_id: string
  service: string
  stage: string
  severity: Severity | null
  summary: string
  demo: boolean
  updated_at: string
}

export interface WorkflowEvent {
  incident_id: string
  stage: string
  title: string
  detail: string
  occurred_at: string
  payload: Record<string, unknown>
}

export interface ActionReceipt {
  action_kind: string
  idempotency_key: string
  status: 'pending' | 'succeeded' | 'failed' | 'skipped'
  attempts: number
  external_url?: string
  sanitized_error?: string
}

export interface ValidationCase {
  name: string
  before_output: string
  after_output: string
  before_passed: boolean
  after_passed: boolean
}

export interface WorkflowRun {
  incident_id: string
  service: string
  source: string
  trace_id: string
  demo: boolean
  stage: string
  updated_at: string
  event: {
    input_text: string
    output_text: string
    expected_behavior: string
    metadata: Record<string, unknown>
  }
  triage?: {
    severity: Severity
    category: string
    confidence: number
    summary: string
    evidence: string[]
    route: string
  }
  investigation?: {
    root_cause: string
    causal_factors: string[]
    recommended_change: string
  }
  proposal?: {
    target_path: string
    unified_diff: string
    rationale: string
    risk: string
  }
  validation?: {
    passed: boolean
    before_pass_rate: number
    after_pass_rate: number
    gate_reason: string
    cases: ValidationCase[]
  }
  actions: ActionReceipt[]
  issue_url?: string
  pull_request_url?: string
  branch_name?: string
  failure?: string
}

export interface Health {
  ok: boolean
  environment: string
  build_revision: string
  reasoning_backend: string
  gemini_model: string
  state_backend: string
  action_mode: string
  live_actions_ready: boolean
  cloud: { project_configured: boolean; region: string; pubsub_topic: string }
}
