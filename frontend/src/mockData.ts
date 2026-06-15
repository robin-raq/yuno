import type { AgentConfig, RunSummary, KitCard, RunSnapshot } from './types'

// ─────────────────────────────────────────────────────────────────────────────
// MOCK / DEMO DATA — frontend prototype only.
// Numbers are illustrative and (for remittance) consistent with the committed
// backend fixture `backend/fixtures/transfer_fixture.json`. Nothing here is a
// live Goose run, a live provider rate, or a real API response. The flagship
// narrative is the Remittance Comparison workflow (Research → Compliance →
// Analyst); the Dev Pipeline is kept as a second template to show that Yuno is a
// general agent-orchestration platform, not a single-purpose app.
// ─────────────────────────────────────────────────────────────────────────────

// MOCK: accent colors and monograms are UI-only; not stored in backend agent_configs table.
export const MOCK_AGENTS: AgentConfig[] = [
  // Remittance team (flagship)
  { id: 'agent-research',   name: 'Research',   role: 'Remittance researcher',            model: 'claude-sonnet-4-6', accent: '#6E5BFF', monogram: 'Rs' },
  { id: 'agent-compliance', name: 'Compliance', role: 'Compliance screening (scripted)',  model: 'deterministic',     accent: '#1FA8A0', monogram: 'Cm' },
  { id: 'agent-analyst',    name: 'Analyst',    role: 'Remittance analyst',               model: 'claude-sonnet-4-6', accent: '#7C3AED', monogram: 'An' },
  // Dev Pipeline team (secondary — platform generality)
  { id: 'agent-coder',      name: 'Coder',      role: 'Software engineer',                model: 'claude-sonnet-4-6', accent: '#2F6BFF', monogram: 'Co' },
  { id: 'agent-reviewer',   name: 'Reviewer',   role: 'Code reviewer',                    model: 'claude-sonnet-4-6', accent: '#F4A024', monogram: 'Rv' },
  { id: 'agent-deployer',   name: 'Deployer',   role: 'Deployment engineer',              model: 'claude-haiku-4-5',  accent: '#1E9E6A', monogram: 'Dp' },
]

export const AGENT_BY_ID: Record<string, AgentConfig> = Object.fromEntries(
  MOCK_AGENTS.map(a => [a.id, a])
)

export const STATUS_COLOR: Record<string, string> = {
  pending:           '#929BB0',
  running:           '#2F6BFF',
  completed:         '#1E9E6A',
  failed:            '#E5484D',
  awaiting_approval: '#F4A024',
  awaiting_feedback: '#F4A024',
  cancelled:         '#929BB0',
}

export const STATUS_BG: Record<string, string> = {
  pending:           '#EEF1F6',
  running:           '#EAF0FF',
  completed:         '#E2F4EC',
  failed:            '#FCE9E9',
  awaiting_approval: '#FDF1DC',
  awaiting_feedback: '#FDF1DC',
  cancelled:         '#EEF1F6',
}

export const STATUS_LABEL: Record<string, string> = {
  pending:           'PENDING',
  running:           'RUNNING',
  completed:         'COMPLETED',
  failed:            'FAILED',
  awaiting_approval: 'APPROVAL',
  awaiting_feedback: 'AWAITING',
  cancelled:         'CANCELLED',
}

// ── Remittance payoff content (MOCK; fixture-consistent) ──────────────────────
// Shapes mirror the backend `AnalystResult` / `ComplianceResult` contracts and
// the telegram_message format locked in the remittance plan. Numbers match
// transfer_fixture.json: cop_received = round((amount_usd - fee_usd) * rate_cop).

export interface ProviderRow {
  name: string
  fee: string
  rate: string
  receive: string
  detail: string
  score: number   // MOCK: illustrative weighted score (0–1), cash-send weighting
}

export interface RemittanceClearedPayoff {
  request: string
  complianceStatus: 'CLEARED'
  complianceNotes: string[]
  winner: string
  providers: ProviderRow[]
  reportPath: string
  telegram: string
}

export interface RemittanceFlaggedPayoff {
  request: string
  complianceStatus: 'FLAGGED'
  issue: string
  required: string
  complianceNotes: string[]
  telegram: string
}

export const REMITTANCE_CLEARED: RemittanceClearedPayoff = {
  request: '$500 cash · Austin, TX → Bogotá, Colombia (USD→COP)',
  complianceStatus: 'CLEARED',
  complianceNotes: [
    'Colombia is not on the restricted-country list',
    '$500 is under the $3,000 AML reporting threshold',
    'Cash send ≥ $500 — valid government-issued ID required at pickup',
    'USD→COP corridor supported by Western Union and MoneyGram',
  ],
  winner: 'MoneyGram',
  providers: [
    { name: 'Western Union', fee: '$12.99', rate: '4,180', receive: '2,035,702 COP', detail: 'Pickup 1.2 mi · 10 min',  score: 0.50 },
    { name: 'MoneyGram',     fee: '$9.99',  rate: '4,155', receive: '2,035,992 COP', detail: 'Pickup 3.8 mi · 15 min',  score: 0.50 },
    { name: 'Wise',          fee: '$7.45',  rate: '4,205', receive: '2,071,273 COP', detail: 'No cash pickup · ~24 hr', score: 0.61 },
  ],
  reportPath: 'reports/transfer_comparison.md',
  telegram:
    'RECOMMENDATION: MoneyGram\n' +
    'Fee $9.99 · Rate 4,155 COP/USD · You receive 2,035,992 COP\n' +
    'Pickup: Walmart Supercenter, 3.8 mi (Daily 7am-11pm)\n' +
    'Runner-up: Western Union — $3.00 higher fee but 25 COP/USD better rate\n' +
    'Full report: reports/transfer_comparison.md',
}

export const REMITTANCE_FLAGGED: RemittanceFlaggedPayoff = {
  request: '$3,500 cash · Austin, TX → Bogotá, Colombia (USD→COP)',
  complianceStatus: 'FLAGGED',
  issue: 'Cash send of $3,500 exceeds the $3,000 AML reporting threshold',
  required: 'Complete AML reporting at the send location before this transfer can proceed',
  complianceNotes: [
    'AML rule: cash sends over $3,000 require reporting before send',
    'Run halted at Compliance — Analyst never runs, no recommendation produced',
  ],
  telegram:
    '⚠️ Transfer on hold — cash send of $3,500 exceeds the $3,000 AML reporting ' +
    'threshold. Required: complete AML reporting at the send location before proceeding.',
}

// MOCK: progress % and human-readable time are not in backend RunSnapshot.
// Remittance runs lead; Dev Pipeline runs are kept for platform generality.
export const MOCK_RUN_SUMMARIES: RunSummary[] = [
  { id: 'run-1042', name: 'Remittance Comparison', status: 'running',           progress: 60,  cost: '$0.03', started: 'just now' },
  { id: 'run-1043', name: 'Remittance Comparison', status: 'completed',         progress: 100, cost: '$0.01', started: '8m ago'  },
  { id: 'run-1039', name: 'Dev Pipeline',          status: 'awaiting_approval', progress: 78,  cost: '$0.84', started: '1h ago'  },
  { id: 'run-1041', name: 'Dev Pipeline',          status: 'completed',         progress: 100, cost: '$0.31', started: '3h ago'  },
]

export const MOCK_KITS: KitCard[] = [
  {
    id: 'kit-rem-01', code: 'KIT·REM-01', name: 'Remittance Comparison', tag: 'Money Transfer',
    color: '#6E5BFF',
    description: 'Research gathers Western Union / MoneyGram / Wise quotes, Compliance screens the transfer against AML & corridor rules, Analyst picks the best deal and drafts the Telegram reply. Halts on a compliance flag.',
    stations: ['Rs', 'Cm', 'An'], costEstimate: '~$0.03/run',
  },
  {
    id: 'kit-dev-03', code: 'KIT·DEV-03', name: 'Dev Pipeline', tag: 'Engineering',
    color: '#2F6BFF',
    description: 'Coder writes, Reviewer approves or loops back, Deployer ships after a human approval gate. A structurally different workflow on the same engine.',
    stations: ['Co', 'Rv', 'Dp'], costEstimate: '~$0.84/run',
  },
  {
    id: 'kit-blank', code: 'KIT·BLK-00', name: 'Blank Workflow', tag: 'Custom',
    color: '#929BB0',
    description: 'Start from an empty canvas. Add agent blocks and connect them your way.',
    stations: [], costEstimate: '—',
  },
]

// MOCK: Full RunSnapshot objects shaped exactly like the GET /runs/{run_id}
// response (see types.ts, frozen against backend/app/services/workflow_service.py).
export const MOCK_RUNS: Record<string, RunSnapshot> = {
  // ── Flagship: Remittance Comparison, CLEARED → RECOMMENDATION ──────────────
  'run-1042': {
    run_id: 'run-1042', workflow_id: 'wf-remittance', status: 'running', forced_complete: false,
    started_at: '2026-06-14T10:00:00Z', completed_at: null,
    total_tokens: 2860, total_cost: 0.029,
    workflow: { id: 'wf-remittance', name: 'Remittance Comparison', description: 'Research → Compliance → Analyst (money transfer comparison)', template_key: 'remittance_comparison' },
    tasks: [
      {
        id: 'task-rs1', run_id: 'run-1042', node_id: 'node-research', agent_id: 'agent-research',
        source: 'workflow', status: 'completed',
        input: 'run remittance: $500 cash to Bogotá',
        output: 'Transfer brief ready (data_source=fixture): $500 USD→COP cash send, Austin → Bogotá. Quotes: Western Union, MoneyGram, Wise.',
        feedback_iteration_count: 0, tokens_used: 1480, cost_usd: 0.015,
        started_at: '2026-06-14T10:00:00Z', completed_at: '2026-06-14T10:00:42Z',
      },
      {
        id: 'task-cm1', run_id: 'run-1042', node_id: 'node-compliance', agent_id: 'agent-compliance',
        source: 'workflow', status: 'completed',
        input: 'Screen transfer brief against compliance rules',
        output: 'COMPLIANCE=CLEARED\nColombia not restricted. $500 under the $3,000 AML threshold. ID required at pickup. USD→COP corridor supported.',
        feedback_iteration_count: 0, tokens_used: 0, cost_usd: 0,
        started_at: '2026-06-14T10:00:42Z', completed_at: '2026-06-14T10:00:43Z',
      },
      {
        id: 'task-an1', run_id: 'run-1042', node_id: 'node-analyst', agent_id: 'agent-analyst',
        source: 'workflow', status: 'running',
        input: 'Score providers and recommend the best transfer',
        output: null,
        feedback_iteration_count: 0, tokens_used: 0, cost_usd: 0,
        started_at: '2026-06-14T10:00:43Z', completed_at: null,
      },
    ],
    messages: [
      {
        id: 'msg-rm1', run_id: 'run-1042', from_task_id: 'task-rs1', to_task_id: 'task-cm1',
        msg_type: 'task_output',
        payload: { content: 'Transfer brief: $500 USD→COP cash, Austin → Bogotá (WU / MoneyGram / Wise quotes).', chat_id: null, agent_id: 'agent-research' },
        created_at: '2026-06-14T10:00:42Z',
      },
      {
        id: 'msg-rm2', run_id: 'run-1042', from_task_id: 'task-cm1', to_task_id: 'task-an1',
        msg_type: 'task_output',
        payload: { content: 'COMPLIANCE=CLEARED — routing to Analyst.', chat_id: null, agent_id: 'agent-compliance' },
        created_at: '2026-06-14T10:00:43Z',
      },
    ],
    pending_approval: null,
  },

  // ── Remittance Comparison, FLAGGED stop (Compliance halts before Analyst) ──
  'run-1043': {
    run_id: 'run-1043', workflow_id: 'wf-remittance', status: 'completed', forced_complete: false,
    started_at: '2026-06-14T09:30:00Z', completed_at: '2026-06-14T09:30:50Z',
    total_tokens: 1490, total_cost: 0.015,
    workflow: { id: 'wf-remittance', name: 'Remittance Comparison', description: 'Research → Compliance → Analyst (money transfer comparison)', template_key: 'remittance_comparison' },
    tasks: [
      {
        id: 'task-rs2', run_id: 'run-1043', node_id: 'node-research', agent_id: 'agent-research',
        source: 'workflow', status: 'completed',
        input: 'run remittance: $3,500 cash to Bogotá',
        output: 'Transfer brief ready (data_source=fixture): $3,500 USD→COP cash send, Austin → Bogotá.',
        feedback_iteration_count: 0, tokens_used: 1490, cost_usd: 0.015,
        started_at: '2026-06-14T09:30:00Z', completed_at: '2026-06-14T09:30:44Z',
      },
      {
        id: 'task-cm2', run_id: 'run-1043', node_id: 'node-compliance', agent_id: 'agent-compliance',
        source: 'workflow', status: 'completed',
        input: 'Screen transfer brief against compliance rules',
        output: 'COMPLIANCE=FLAGGED\nCash send of $3,500 exceeds the $3,000 AML reporting threshold. Reporting required before send.',
        feedback_iteration_count: 0, tokens_used: 0, cost_usd: 0,
        started_at: '2026-06-14T09:30:44Z', completed_at: '2026-06-14T09:30:45Z',
      },
      // No Analyst task — FLAGGED terminates by end-node fallthrough (KTD2).
    ],
    messages: [
      {
        id: 'msg-fl1', run_id: 'run-1043', from_task_id: 'task-rs2', to_task_id: 'task-cm2',
        msg_type: 'task_output',
        payload: { content: 'Transfer brief: $3,500 USD→COP cash, Austin → Bogotá.', chat_id: null, agent_id: 'agent-research' },
        created_at: '2026-06-14T09:30:44Z',
      },
    ],
    pending_approval: null,
  },

  // ── Dev Pipeline, awaiting human approval (secondary — generality) ─────────
  'run-1039': {
    run_id: 'run-1039', workflow_id: 'wf-dev', status: 'awaiting_approval', forced_complete: false,
    started_at: '2026-06-14T07:00:00Z', completed_at: null,
    total_tokens: 2100, total_cost: 0.021,
    workflow: { id: 'wf-dev', name: 'Dev Pipeline', description: 'Coder → Reviewer → Deployer with feedback loop + approval gate', template_key: 'dev_pipeline' },
    tasks: [], messages: [],
    pending_approval: {
      id: 'appr-1', run_id: 'run-1039', task_id: 'task-dep-1',
      description: 'Deploy auth-refactor to production?',
      status: 'pending', created_at: '2026-06-14T07:45:00Z', resolved_at: null,
    },
  },

  // ── Dev Pipeline, completed (secondary — generality) ──────────────────────
  'run-1041': {
    run_id: 'run-1041', workflow_id: 'wf-dev', status: 'completed', forced_complete: false,
    started_at: '2026-06-14T06:42:00Z', completed_at: '2026-06-14T06:47:00Z',
    total_tokens: 2840, total_cost: 0.031,
    workflow: { id: 'wf-dev', name: 'Dev Pipeline', description: 'Coder → Reviewer → Deployer with feedback loop + approval gate', template_key: 'dev_pipeline' },
    tasks: [], messages: [], pending_approval: null,
  },
}
