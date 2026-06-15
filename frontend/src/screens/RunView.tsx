import { useState, useEffect } from 'react'
import type { Screen } from '../types'
import { MOCK_RUNS, REMITTANCE_CLEARED, REMITTANCE_FLAGGED } from '../mockData'

interface Props {
  runId: string
  setScreen: (s: Screen) => void
}

// ─────────────────────────────────────────────────────────────────────────────
// Scenario-driven run simulation (MOCK). One renderer expresses both the
// remittance gate-and-recommend flow and the dev approve-and-ship flow — a new
// workflow is new data here, not new component code. No live SSE, no API.
// ─────────────────────────────────────────────────────────────────────────────

type StationStatus =
  | 'idle' | 'running' | 'completed' | 'failed'
  | 'awaiting_approval' | 'rejected' | 'cleared' | 'flagged'

type Payoff = 'recommendation' | 'flagged' | 'shipped' | null

interface Banner { tone: 'amber' | 'green' | 'red'; icon: string; title: string; sub?: string }

interface ScenarioStation { id: string; name: string; mg: string; accent: string; task: string }

interface Frame {
  runStatus: string
  progress: number
  status: Record<string, StationStatus>
  active: string | null
  badges?: Record<string, string>
  banner?: Banner | null
  showApproval?: boolean
  payoff?: Payoff
  events: Array<{ icon: string; text: string; color: string }>
}

interface Scenario {
  jobToken: string
  stations: ScenarioStation[]
  frames: Frame[]
  approveTargetFrame?: number
}

// ── Remittance: CLEARED → RECOMMENDATION (flagship happy path) ────────────────
const REMITTANCE_STATIONS: ScenarioStation[] = [
  { id: 'research',   name: 'Research',   mg: 'Rs', accent: '#6E5BFF', task: 'Parse request · gather Western Union / MoneyGram / Wise quotes (USD→COP cash send)' },
  { id: 'compliance', name: 'Compliance', mg: 'Cm', accent: '#1FA8A0', task: 'Screen against AML, ID, corridor & sender rules — deterministic, no LLM' },
  { id: 'analyst',    name: 'Analyst',    mg: 'An', accent: '#7C3AED', task: 'Score providers · pick winner · write report · draft Telegram reply' },
]

const REMITTANCE_CLEARED_SCENARIO: Scenario = {
  jobToken: '$500 → Bogotá',
  stations: REMITTANCE_STATIONS,
  frames: [
    {
      runStatus: 'pending', progress: 0, active: null,
      status: { research: 'idle', compliance: 'idle', analyst: 'idle' },
      events: [{ icon: '▸', text: 'Run started — remittance: $500 cash → Bogotá', color: '#2F6BFF' }],
    },
    {
      runStatus: 'running', progress: 15, active: 'research',
      status: { research: 'running', compliance: 'idle', analyst: 'idle' },
      events: [
        { icon: '▸', text: 'Run started — remittance: $500 cash → Bogotá', color: '#2F6BFF' },
        { icon: '◆', text: 'Research gathering provider quotes…', color: '#929BB0' },
      ],
    },
    {
      runStatus: 'running', progress: 45, active: 'compliance',
      status: { research: 'completed', compliance: 'running', analyst: 'idle' },
      events: [
        { icon: '✓', text: 'Research completed — brief: WU / MoneyGram / Wise (1.5k tokens)', color: '#1E9E6A' },
        { icon: '◆', text: 'Compliance screening transfer…', color: '#929BB0' },
      ],
    },
    {
      runStatus: 'running', progress: 72, active: 'analyst',
      status: { research: 'completed', compliance: 'cleared', analyst: 'running' },
      badges: { compliance: 'CLEARED' },
      banner: { tone: 'green', icon: '✓', title: 'Compliance CLEARED', sub: 'Under the $3,000 AML threshold · corridor supported — routing to Analyst.' },
      events: [
        { icon: '✓', text: 'COMPLIANCE=CLEARED — routing to Analyst', color: '#1E9E6A' },
        { icon: '◆', text: 'Analyst scoring providers…', color: '#929BB0' },
      ],
    },
    {
      runStatus: 'completed', progress: 100, active: null,
      status: { research: 'completed', compliance: 'cleared', analyst: 'completed' },
      badges: { compliance: 'CLEARED', analyst: 'RECOMMENDATION' },
      banner: { tone: 'green', icon: '✓', title: `Run completed — ${REMITTANCE_CLEARED.winner} recommended`, sub: 'Report written · Telegram-ready message produced.' },
      payoff: 'recommendation',
      events: [
        { icon: '✓', text: `Analyst completed — ${REMITTANCE_CLEARED.winner} wins (0.9k tokens)`, color: '#1E9E6A' },
        { icon: '✓', text: 'Run completed — recommendation ready', color: '#1E9E6A' },
      ],
    },
  ],
}

// ── Remittance: FLAGGED stop (Compliance halts before Analyst) ───────────────
const REMITTANCE_FLAGGED_SCENARIO: Scenario = {
  jobToken: '$3,500 → Bogotá',
  stations: REMITTANCE_STATIONS,
  frames: [
    {
      runStatus: 'pending', progress: 0, active: null,
      status: { research: 'idle', compliance: 'idle', analyst: 'idle' },
      events: [{ icon: '▸', text: 'Run started — remittance: $3,500 cash → Bogotá', color: '#2F6BFF' }],
    },
    {
      runStatus: 'running', progress: 20, active: 'research',
      status: { research: 'running', compliance: 'idle', analyst: 'idle' },
      events: [
        { icon: '▸', text: 'Run started — remittance: $3,500 cash → Bogotá', color: '#2F6BFF' },
        { icon: '◆', text: 'Research gathering provider quotes…', color: '#929BB0' },
      ],
    },
    {
      runStatus: 'running', progress: 55, active: 'compliance',
      status: { research: 'completed', compliance: 'running', analyst: 'idle' },
      events: [
        { icon: '✓', text: 'Research completed — brief: $3,500 USD→COP cash', color: '#1E9E6A' },
        { icon: '◆', text: 'Compliance screening transfer…', color: '#929BB0' },
      ],
    },
    {
      runStatus: 'completed', progress: 100, active: null,
      status: { research: 'completed', compliance: 'flagged', analyst: 'idle' },
      badges: { compliance: 'FLAGGED' },
      banner: { tone: 'red', icon: '⚠', title: 'Transfer on hold — FLAGGED by Compliance', sub: '$3,500 exceeds the $3,000 AML reporting threshold. Analyst was not run.' },
      payoff: 'flagged',
      events: [
        { icon: '✕', text: 'COMPLIANCE=FLAGGED — $3,500 over $3,000 AML threshold', color: '#E5484D' },
        { icon: '❚', text: 'Run halted at Compliance — no recommendation produced', color: '#E5484D' },
      ],
    },
  ],
}

// ── Dev Pipeline: reject-loop + human approval → ship (secondary) ────────────
const DEV_STATIONS: ScenarioStation[] = [
  { id: 'coder',    name: 'Coder',    mg: 'Co', accent: '#2F6BFF', task: 'Implement auth-refactor: JWT middleware + token refresh' },
  { id: 'reviewer', name: 'Reviewer', mg: 'Rv', accent: '#F4A024', task: 'Review the auth refactor for security and correctness' },
  { id: 'deployer', name: 'Deployer', mg: 'Dp', accent: '#1E9E6A', task: 'Deploy auth-refactor to production' },
]

const DEV_SCENARIO: Scenario = {
  jobToken: 'auth-refactor',
  stations: DEV_STATIONS,
  approveTargetFrame: 8,
  frames: [
    { runStatus: 'pending', progress: 0, active: null, status: { coder: 'idle', reviewer: 'idle', deployer: 'idle' },
      events: [{ icon: '▸', text: 'Run started — auth-refactor', color: '#2F6BFF' }] },
    { runStatus: 'running', progress: 10, active: 'coder', status: { coder: 'running', reviewer: 'idle', deployer: 'idle' },
      events: [{ icon: '▸', text: 'Run started — auth-refactor', color: '#2F6BFF' }, { icon: '◆', text: 'Coder is working…', color: '#929BB0' }] },
    { runStatus: 'running', progress: 30, active: 'reviewer', status: { coder: 'completed', reviewer: 'running', deployer: 'idle' },
      events: [{ icon: '✓', text: 'Coder completed (1.2k tokens)', color: '#1E9E6A' }, { icon: '◆', text: 'Reviewer is reviewing…', color: '#929BB0' }] },
    { runStatus: 'running', progress: 36, active: 'coder', status: { coder: 'running', reviewer: 'rejected', deployer: 'idle' }, badges: { coder: '↻ rev 1', reviewer: 'REJECTED' },
      banner: { tone: 'amber', icon: '↻', title: 'Feedback loop active — iteration 1 of 3', sub: 'Reviewer rejected. Coder is revising. Max 3 loops before forced completion.' },
      events: [{ icon: '✕', text: 'Reviewer rejected — loop 1/3', color: '#E5484D' }, { icon: '◆', text: 'Coder is revising…', color: '#929BB0' }] },
    { runStatus: 'running', progress: 55, active: 'reviewer', status: { coder: 'completed', reviewer: 'running', deployer: 'idle' }, badges: { coder: '↻ rev 1' },
      events: [{ icon: '✓', text: 'Coder revision complete (0.9k tokens)', color: '#1E9E6A' }, { icon: '◆', text: 'Reviewer is re-reviewing…', color: '#929BB0' }] },
    { runStatus: 'running', progress: 68, active: null, status: { coder: 'completed', reviewer: 'completed', deployer: 'idle' }, badges: { coder: '↻ rev 1', reviewer: 'APPROVED' },
      events: [{ icon: '✓', text: 'Reviewer approved — routing to Deployer', color: '#1E9E6A' }] },
    { runStatus: 'running', progress: 74, active: 'deployer', status: { coder: 'completed', reviewer: 'completed', deployer: 'running' }, badges: { reviewer: 'APPROVED' },
      events: [{ icon: '✓', text: 'Reviewer approved — routing to Deployer', color: '#1E9E6A' }, { icon: '◆', text: 'Deployer preparing…', color: '#929BB0' }] },
    { runStatus: 'awaiting_approval', progress: 78, active: 'deployer', status: { coder: 'completed', reviewer: 'completed', deployer: 'awaiting_approval' }, badges: { reviewer: 'APPROVED' }, showApproval: true,
      banner: { tone: 'amber', icon: '❚', title: 'Awaiting human approval', sub: 'Pipeline paused. Deployer is ready to ship to production.' },
      events: [{ icon: '✓', text: 'Reviewer approved — routing to Deployer', color: '#1E9E6A' }, { icon: '❚', text: 'Awaiting human approval — deploy to production', color: '#F4A024' }] },
    { runStatus: 'running', progress: 85, active: 'deployer', status: { coder: 'completed', reviewer: 'completed', deployer: 'running' }, badges: { reviewer: 'APPROVED' },
      events: [{ icon: '✓', text: 'Human approved — deploying now', color: '#1E9E6A' }, { icon: '◆', text: 'Deployer is deploying…', color: '#929BB0' }] },
    { runStatus: 'running', progress: 95, active: null, status: { coder: 'completed', reviewer: 'completed', deployer: 'completed' }, badges: { reviewer: 'APPROVED' },
      events: [{ icon: '✓', text: 'Deployer completed (0.7k tokens)', color: '#1E9E6A' }, { icon: '▸', text: 'Finalizing run…', color: '#2F6BFF' }] },
    { runStatus: 'completed', progress: 100, active: null, status: { coder: 'completed', reviewer: 'completed', deployer: 'completed' }, badges: { reviewer: 'APPROVED' }, payoff: 'shipped',
      banner: { tone: 'green', icon: '✓', title: 'Run completed — auth-refactor shipped to production' },
      events: [{ icon: '✓', text: 'Deployer completed (0.7k tokens)', color: '#1E9E6A' }, { icon: '✓', text: 'Run completed — auth-refactor shipped', color: '#1E9E6A' }] },
  ],
}

const SCENARIO_KEY: Record<string, 'remittance' | 'remittanceFlagged' | 'dev'> = {
  'run-1042': 'remittance',
  'run-1043': 'remittanceFlagged',
}
const SCENARIOS = {
  remittance: REMITTANCE_CLEARED_SCENARIO,
  remittanceFlagged: REMITTANCE_FLAGGED_SCENARIO,
  dev: DEV_SCENARIO,
}

// ── Status → color / label / tint helpers ────────────────────────────────────
function statusColor(s: string): string {
  switch (s) {
    case 'running': return '#2F6BFF'
    case 'completed': case 'cleared': return '#1E9E6A'
    case 'failed': case 'flagged': case 'rejected': return '#E5484D'
    case 'awaiting_approval': return '#F4A024'
    default: return '#929BB0'
  }
}
function statusLabel(s: string): string {
  switch (s) {
    case 'idle': case 'pending': return 'PENDING'
    case 'cleared': return 'CLEARED'
    case 'flagged': return 'FLAGGED'
    case 'rejected': return 'REJECTED'
    case 'awaiting_approval': return 'APPROVAL'
    case 'running': return 'RUNNING'
    case 'completed': return 'COMPLETED'
    default: return s.toUpperCase()
  }
}
function statusBg(s: string): string {
  switch (s) {
    case 'running': return '#EAF0FF'
    case 'completed': case 'cleared': return '#E2F4EC'
    case 'failed': case 'flagged': case 'rejected': return '#FCE9E9'
    case 'awaiting_approval': return '#FDF1DC'
    default: return '#EEF1F6'
  }
}
const BANNER_STYLE: Record<Banner['tone'], { bg: string; border: string; text: string }> = {
  amber: { bg: '#FDF1DC', border: '#F4A024', text: '#B8740A' },
  green: { bg: '#E2F4EC', border: '#1E9E6A', text: '#147A4F' },
  red:   { bg: '#FCE9E9', border: '#E5484D', text: '#B0232A' },
}

function done(s: StationStatus) { return s === 'completed' || s === 'cleared' }

function StationChip({ mg, accent, status, isActive, isTerminal, symbol }: {
  mg?: string; accent?: string; status?: StationStatus
  isActive?: boolean; isTerminal?: boolean; symbol?: string
}) {
  const sc = status ? statusColor(status) : '#929BB0'
  const running = status === 'running'
  if (isTerminal) {
    return (
      <div style={{ width: 46, height: 46, borderRadius: 10, background: symbol === '▶' ? 'var(--navy)' : 'white', border: symbol !== '▶' ? '2px solid var(--line)' : 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, color: symbol === '▶' ? 'white' : 'var(--ink3)', flexShrink: 0 }}>
        {symbol}
      </div>
    )
  }
  return (
    <div style={{ position: 'relative', display: 'inline-block', flexShrink: 0 }}>
      <div style={{
        width: 46, height: 46, borderRadius: 10,
        background: accent ? `${accent}1A` : 'var(--surface2)',
        border: `2px solid ${isActive ? (accent ?? '#2F6BFF') : 'var(--line)'}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: isActive ? `0 0 0 3px ${accent}33` : 'none',
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13, color: accent ?? 'var(--ink2)' }}>{mg}</span>
      </div>
      <div
        className={running ? 'yo-blink' : undefined}
        style={{ position: 'absolute', top: -3, right: -3, width: 10, height: 10, borderRadius: 5, background: sc, border: '2px solid white' }}
      />
    </div>
  )
}

function Belt({ active }: { active: boolean }) {
  return (
    <div style={{
      flex: 1, height: 12, borderRadius: 6,
      background: active
        ? 'repeating-linear-gradient(90deg, #C8D2E8 0px, #C8D2E8 12px, #E1E6F0 12px, #E1E6F0 14px)'
        : '#E1E6F0',
      animation: active ? 'yoBelt 0.6s linear infinite' : 'none',
    }} />
  )
}

function ComplianceChip({ status }: { status: 'CLEARED' | 'FLAGGED' }) {
  const ok = status === 'CLEARED'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 8, background: ok ? '#E2F4EC' : '#FCE9E9', color: ok ? '#147A4F' : '#B0232A', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, letterSpacing: '0.5px' }}>
      {ok ? '✓' : '⚠'} COMPLIANCE={status}
    </span>
  )
}

function TelegramPreview({ text }: { text: string }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '1px', textTransform: 'uppercase', marginBottom: 6 }}>📨 Telegram-ready message</div>
      <div style={{ background: 'var(--surface2)', border: '1px solid var(--line)', borderRadius: 10, padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
        {text}
      </div>
    </div>
  )
}

export default function RunView({ runId, setScreen }: Props) {
  const snapshot = MOCK_RUNS[runId]
  const scenario = SCENARIOS[SCENARIO_KEY[runId] ?? 'dev']
  const [runFrame, setRunFrame] = useState(0)
  const [runPlaying, setRunPlaying] = useState(false)
  const [decision, setDecision] = useState<null | 'approved' | 'rejected'>(null)

  const frames = scenario.frames
  const frame = frames[runFrame]
  const approveFrame = scenario.approveTargetFrame ?? -1

  useEffect(() => {
    if (!runPlaying) return
    // Pause at the approval gate until the human decides.
    if (frame.showApproval && decision === null) { setRunPlaying(false); return }
    if (runFrame >= frames.length - 1) { setRunPlaying(false); return }
    const t = setTimeout(() => setRunFrame(f => f + 1), 1250)
    return () => clearTimeout(t)
  }, [runPlaying, runFrame, frame, decision, frames.length])

  // Reset a stale decision when scrubbing back before the gate.
  useEffect(() => {
    if (approveFrame >= 0 && runFrame < approveFrame && decision !== null) setDecision(null)
  }, [runFrame, approveFrame, decision])

  function handleApprove() {
    setDecision('approved')
    if (approveFrame >= 0) setRunFrame(approveFrame)
    setRunPlaying(true)
  }
  function handleReject() {
    setDecision('rejected')
    setRunPlaying(false)
  }
  function handlePlay() {
    if (runFrame >= frames.length - 1) { setRunFrame(0); setDecision(null); return }
    setRunPlaying(p => !p)
  }
  function handleRestart() {
    setRunFrame(0); setRunPlaying(false); setDecision(null)
  }

  const activeName = snapshot?.workflow?.name ?? 'Workflow run'
  const tokens = snapshot?.total_tokens ?? 0
  const cost = snapshot?.total_cost ?? 0

  const showApproval = !!frame.showApproval && decision === null
  const showRejected = !!frame.showApproval && decision === 'rejected'

  return (
    <div>
      {/* Toolbar */}
      <div style={{ background: 'var(--surface)', borderBottom: '1px solid var(--line)', padding: '0 28px', display: 'flex', alignItems: 'center', gap: 14, height: 56, position: 'sticky', top: 60, zIndex: 90 }}>
        <button onClick={() => setScreen('dashboard')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink2)', fontSize: 18, padding: 0, lineHeight: 1 }}>‹</button>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)', lineHeight: 1.2 }}>{activeName}</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)' }}>{runId} · {scenario.jobToken}</div>
        </div>
        <div style={{ padding: '3px 10px', borderRadius: 20, background: statusBg(frame.runStatus), display: 'flex', alignItems: 'center', gap: 5 }}>
          <div className={frame.runStatus === 'running' ? 'yo-blink' : undefined} style={{ width: 6, height: 6, borderRadius: 3, background: statusColor(frame.runStatus) }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: statusColor(frame.runStatus), letterSpacing: '0.8px', textTransform: 'uppercase', fontWeight: 600 }}>
            {statusLabel(frame.runStatus)}
          </span>
        </div>
        <div style={{ flex: 1, height: 5, borderRadius: 3, background: 'var(--line)', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${frame.progress}%`, background: statusColor(frame.runStatus), borderRadius: 3, transition: 'width 0.4s ease' }} />
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink3)', flexShrink: 0 }}>{frame.progress}%</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink3)', flexShrink: 0 }}>${cost.toFixed(3)} / {tokens.toLocaleString()} tok</div>
        <button onClick={handleRestart} style={{ background: 'var(--surface2)', border: '1px solid var(--line)', borderRadius: 8, padding: '5px 10px', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink2)' }}>↺</button>
        <button
          onClick={handlePlay}
          style={{ padding: '7px 16px', borderRadius: 10, border: 'none', background: 'var(--blue)', color: 'white', fontSize: 13, fontFamily: 'var(--font-ui)', cursor: 'pointer', fontWeight: 600, boxShadow: 'var(--shadow-cta)', flexShrink: 0 }}
        >
          {runFrame >= frames.length - 1 ? 'Run again' : runPlaying ? 'Pause' : 'Play'}
        </button>
      </div>

      {/* Production line strip */}
      <div style={{ background: 'var(--surface)', borderBottom: '1px solid var(--line)', padding: '24px 28px 18px' }}>
        <div style={{ maxWidth: 760, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          <StationChip isTerminal symbol="▶" />
          {scenario.stations.map((st, i) => {
            const beltActive = i === 0
              ? frame.status[st.id] !== 'idle'
              : done(frame.status[scenario.stations[i - 1].id])
            const isActive = frame.active === st.id
            return (
              <div key={st.id} style={{ display: 'contents' }}>
                <Belt active={beltActive} />
                <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                  {isActive && (
                    <div className="yo-bob" style={{ position: 'absolute', top: -28, background: 'var(--navy)', color: 'white', borderRadius: 8, padding: '3px 9px', fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 600, whiteSpace: 'nowrap', boxShadow: 'var(--shadow-dark)' }}>
                      {scenario.jobToken}
                    </div>
                  )}
                  <StationChip mg={st.mg} accent={st.accent} status={frame.status[st.id]} isActive={isActive} />
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink3)', letterSpacing: '0.5px' }}>
                    {frame.badges?.[st.id]?.startsWith('↻') ? frame.badges[st.id] : st.name}
                  </div>
                </div>
              </div>
            )
          })}
          <Belt active={done(frame.status[scenario.stations[scenario.stations.length - 1].id])} />
          <StationChip isTerminal symbol="◼" />
        </div>
      </div>

      {/* Banner */}
      {frame.banner && (
        <div style={{ padding: '10px 28px 0' }}>
          {(() => {
            const b = frame.banner!
            const st = BANNER_STYLE[b.tone]
            return (
              <div style={{ background: st.bg, border: `1px solid ${st.border}`, borderRadius: 10, padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 16 }}>{b.icon}</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: st.text }}>{b.title}</div>
                  {b.sub && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: st.text, opacity: 0.85 }}>{b.sub}</div>}
                </div>
              </div>
            )
          })()}
        </div>
      )}

      {/* Body */}
      <div style={{ maxWidth: 1240, margin: '0 auto', padding: '20px 28px 64px', display: 'grid', gridTemplateColumns: '1.35fr 1fr', gap: 20 }}>

        {/* Left: step timeline */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {scenario.stations.map(st => {
            const s = frame.status[st.id]
            const badge = frame.badges?.[st.id]
            return (
              <div key={st.id} style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 14, padding: '16px', boxShadow: 'var(--shadow-card)', position: 'relative' }}>
                <div style={{ position: 'absolute', top: -3, left: 18, display: 'flex', gap: 3 }}>
                  <div style={{ width: 5, height: 5, borderRadius: 2, background: st.accent }} />
                  <div style={{ width: 5, height: 5, borderRadius: 2, background: st.accent }} />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ position: 'relative', flexShrink: 0 }}>
                    <div style={{ width: 40, height: 40, borderRadius: 10, background: `${st.accent}1A`, border: `1px solid ${st.accent}33`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13, color: st.accent }}>{st.mg}</span>
                    </div>
                    <div className={s === 'running' ? 'yo-blink' : undefined} style={{ position: 'absolute', top: -2, right: -2, width: 9, height: 9, borderRadius: 5, background: statusColor(s), border: '2px solid white' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)' }}>{st.name}</div>
                      {badge && (
                        <div style={{ padding: '2px 7px', borderRadius: 6, background: statusBg(s), color: statusColor(s), fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600 }}>{badge}</div>
                      )}
                    </div>
                    <div style={{ padding: '3px 8px', borderRadius: 6, background: statusBg(s), color: statusColor(s), fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.8px', textTransform: 'uppercase', fontWeight: 600, display: 'inline-block', marginTop: 4 }}>
                      {statusLabel(s)}
                    </div>
                  </div>
                </div>
                {s !== 'idle' && (
                  <div style={{ marginTop: 12, background: 'var(--surface2)', borderRadius: 8, padding: '10px 12px' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink2)', lineHeight: 1.5 }}>{st.task}</div>
                  </div>
                )}
              </div>
            )
          })}

          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', textAlign: 'center', paddingTop: 4 }}>
            Simulated run — mock data, not a live Goose execution
          </div>
        </div>

        {/* Right: payoff / approval / events */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Approval card (dev) */}
          {showApproval && (
            <div style={{ background: 'var(--surface)', border: '2px solid #F4A024', borderRadius: 14, padding: '20px', boxShadow: 'var(--shadow-card)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#F4A024', letterSpacing: '1.5px', textTransform: 'uppercase', marginBottom: 8 }}>HUMAN APPROVAL NEEDED</div>
              <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--ink)', marginBottom: 6 }}>Deploy auth-refactor to production?</div>
              <div style={{ fontSize: 13, color: 'var(--ink2)', marginBottom: 16, lineHeight: 1.5 }}>Reviewer approved the code. Deployer is ready to push to production. This action cannot be undone.</div>
              <div style={{ display: 'flex', gap: 10 }}>
                <button onClick={handleApprove} style={{ flex: 1, padding: '10px 0', borderRadius: 10, border: 'none', background: '#1E9E6A', color: 'white', fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-ui)', cursor: 'pointer' }}>Approve &amp; ship ✓</button>
                <button onClick={handleReject} style={{ padding: '10px 16px', borderRadius: 10, border: '2px solid #E5484D', background: 'white', color: '#E5484D', fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-ui)', cursor: 'pointer' }}>Reject</button>
              </div>
            </div>
          )}
          {showRejected && (
            <div style={{ background: '#FCE9E9', border: '2px solid #E5484D', borderRadius: 14, padding: '16px 20px' }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: '#B0232A', marginBottom: 4 }}>Deploy rejected — run halted</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#B0232A', opacity: 0.85 }}>The Deployer step was not executed. Restart to run again.</div>
            </div>
          )}

          {/* Payoff: remittance RECOMMENDATION */}
          {frame.payoff === 'recommendation' && (
            <div style={{ background: 'var(--surface)', border: '2px solid #1E9E6A', borderRadius: 14, padding: '20px', boxShadow: 'var(--shadow-card)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <div style={{ padding: '3px 9px', borderRadius: 6, background: '#1E9E6A', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'white', fontWeight: 700, letterSpacing: '1px' }}>RECOMMENDATION</div>
                <ComplianceChip status="CLEARED" />
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink)', marginBottom: 2 }}>🏆 {REMITTANCE_CLEARED.winner}</div>
              <div style={{ fontSize: 13, color: 'var(--ink2)', marginBottom: 14 }}>Best deal for {REMITTANCE_CLEARED.request}</div>

              {/* Provider comparison */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                {REMITTANCE_CLEARED.providers.map((p, i) => {
                  const isWinner = p.name === REMITTANCE_CLEARED.winner
                  const c = isWinner ? '#1E9E6A' : '#929BB0'
                  return (
                    <div key={p.name} style={{ background: isWinner ? '#E2F4EC' : 'var(--surface2)', borderRadius: 10, padding: '10px 12px', border: isWinner ? '1px solid #1E9E6A' : '1px solid var(--line)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--ink)' }}>{i + 1}. {p.name}</div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink)' }}>{p.receive}</div>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', marginBottom: 6 }}>
                        <span>Fee {p.fee} · Rate {p.rate}</span>
                        <span>{p.detail}</span>
                      </div>
                      <div style={{ height: 4, borderRadius: 2, background: 'var(--line)', overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${Math.round(p.score * 100)}%`, background: c, borderRadius: 2 }} />
                      </div>
                    </div>
                  )
                })}
              </div>

              <TelegramPreview text={REMITTANCE_CLEARED.telegram} />

              <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink2)' }}>
                <span style={{ color: 'var(--ink3)' }}>📄 Report:</span>
                <span style={{ background: 'var(--surface2)', border: '1px solid var(--line)', borderRadius: 6, padding: '2px 8px', color: 'var(--ink)' }}>{REMITTANCE_CLEARED.reportPath}</span>
              </div>

              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '1px', textTransform: 'uppercase', marginBottom: 8 }}>Compliance notes</div>
                {REMITTANCE_CLEARED.complianceNotes.map((n, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12, color: 'var(--ink2)', marginBottom: 5, lineHeight: 1.5 }}>
                    <span style={{ color: '#1E9E6A', flexShrink: 0 }}>✓</span><span>{n}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Payoff: remittance FLAGGED */}
          {frame.payoff === 'flagged' && (
            <div style={{ background: 'var(--surface)', border: '2px solid #E5484D', borderRadius: 14, padding: '20px', boxShadow: 'var(--shadow-card)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <div style={{ padding: '3px 9px', borderRadius: 6, background: '#E5484D', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'white', fontWeight: 700, letterSpacing: '1px' }}>ON HOLD</div>
                <ComplianceChip status="FLAGGED" />
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 6, lineHeight: 1.4 }}>⚠ {REMITTANCE_FLAGGED.issue}</div>
              <div style={{ fontSize: 13, color: 'var(--ink2)', marginBottom: 8 }}>For {REMITTANCE_FLAGGED.request}</div>
              <div style={{ background: '#FDF1DC', border: '1px solid #F4A024', borderRadius: 10, padding: '10px 12px', fontSize: 12, color: '#B8740A', lineHeight: 1.5, marginBottom: 16 }}>
                <strong>Required:</strong> {REMITTANCE_FLAGGED.required}
              </div>

              <TelegramPreview text={REMITTANCE_FLAGGED.telegram} />

              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '1px', textTransform: 'uppercase', marginBottom: 8 }}>Compliance notes</div>
                {REMITTANCE_FLAGGED.complianceNotes.map((n, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12, color: 'var(--ink2)', marginBottom: 5, lineHeight: 1.5 }}>
                    <span style={{ color: '#E5484D', flexShrink: 0 }}>•</span><span>{n}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Payoff: dev shipped */}
          {frame.payoff === 'shipped' && (
            <div style={{ background: 'var(--navy)', borderRadius: 14, padding: '18px', boxShadow: 'var(--shadow-dark)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <div style={{ padding: '3px 9px', borderRadius: 6, background: '#1E9E6A', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'white', fontWeight: 700, letterSpacing: '1px' }}>SHIPPED</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>auth-refactor · v1.4.2</div>
              </div>
              {['✓ JWT middleware added to api/middleware.ts', '✓ Token refresh endpoint at POST /auth/refresh', '✓ Tests updated: 14 passing, 0 failing', '✓ Deployed to production at 10:07:42Z'].map((line, i) => (
                <div key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#1E9E6A', lineHeight: 1.8 }}>{line}</div>
              ))}
            </div>
          )}

          {/* Events stream */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 14, padding: '16px', boxShadow: 'var(--shadow-card)', flex: 1 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '1px', textTransform: 'uppercase', marginBottom: 12 }}>EVENTS</div>
            {frame.events.map((ev, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: ev.color, flexShrink: 0, lineHeight: 1.6 }}>{ev.icon}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink2)', lineHeight: 1.6 }}>{ev.text}</div>
              </div>
            ))}
            {/* Frame scrubber */}
            <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)' }}>Frame {runFrame + 1} / {frames.length}</div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => { setRunPlaying(false); setRunFrame(f => Math.max(0, f - 1)) }} disabled={runFrame === 0} style={{ width: 26, height: 26, borderRadius: 6, border: '1px solid var(--line)', background: 'var(--surface2)', cursor: 'pointer', fontSize: 12, color: 'var(--ink2)' }}>‹</button>
                  <button onClick={() => { setRunPlaying(false); setRunFrame(f => Math.min(frames.length - 1, f + 1)) }} disabled={runFrame === frames.length - 1} style={{ width: 26, height: 26, borderRadius: 6, border: '1px solid var(--line)', background: 'var(--surface2)', cursor: 'pointer', fontSize: 12, color: 'var(--ink2)' }}>›</button>
                </div>
              </div>
              <input type="range" min={0} max={frames.length - 1} value={runFrame} onChange={e => { setRunPlaying(false); setRunFrame(Number(e.target.value)) }} style={{ width: '100%', accentColor: 'var(--blue)' }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
