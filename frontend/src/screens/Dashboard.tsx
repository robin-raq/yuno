import type { Screen } from '../types'
import { MOCK_AGENTS, MOCK_RUN_SUMMARIES, MOCK_KITS, REMITTANCE_CLEARED, STATUS_COLOR, STATUS_BG, STATUS_LABEL } from '../mockData'

interface Props {
  setScreen: (s: Screen) => void
  setSelectedRunId: (id: string) => void
}

// Honest, defensible counts — no invented success rate. The cost figure is
// labelled illustrative because no analytics API backs it yet.
const KPI_TILES = [
  { label: 'Agents',            value: '6',      delta: 'Research·Compliance·Analyst +3', status: 'completed' },
  { label: 'Templates',         value: '2',      delta: 'Remittance · Dev',               status: 'completed' },
  { label: 'Providers compared', value: '3',     delta: 'WU · MoneyGram · Wise',          status: 'running'   },
  { label: 'Avg cost / run',    value: '~$0.03', delta: 'illustrative',                   status: 'running'   },
]

// Flagship workflow team, shown in the hero card.
const HERO_TEAM = [
  { mg: 'Rs', name: 'Research',   accent: '#6E5BFF' },
  { mg: 'Cm', name: 'Compliance', accent: '#1FA8A0' },
  { mg: 'An', name: 'Analyst',    accent: '#7C3AED' },
]

export default function Dashboard({ setScreen, setSelectedRunId }: Props) {
  function runFlagship(id: string) {
    setSelectedRunId(id)
    setScreen('run')
  }

  return (
    <div style={{ maxWidth: 1240, margin: '0 auto', padding: '30px 28px 64px' }}>

      {/* Greeting row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 22 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--blue)', letterSpacing: '1.5px', textTransform: 'uppercase', marginBottom: 8 }}>▸ FACTORY FLOOR</div>
          <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.8px', color: 'var(--ink)', margin: '0 0 8px' }}>Build and run agent workflows.</h1>
          <p style={{ color: 'var(--ink2)', margin: 0, fontSize: 15 }}>A general agent-orchestration platform — shown here through a live money-transfer comparison.</p>
        </div>
        {/* Secondary actions — subordinate to the flagship CTA below */}
        <div style={{ display: 'flex', gap: 8, flexShrink: 0, paddingTop: 4 }}>
          <button
            onClick={() => setScreen('builder')}
            style={{ padding: '8px 14px', background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 10, cursor: 'pointer', fontFamily: 'var(--font-ui)', fontSize: 13, color: 'var(--ink2)', fontWeight: 500 }}
          >
            New agent
          </button>
          <button
            onClick={() => setScreen('canvas')}
            style={{ padding: '8px 14px', background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 10, cursor: 'pointer', fontFamily: 'var(--font-ui)', fontSize: 13, color: 'var(--ink2)', fontWeight: 500 }}
          >
            New workflow
          </button>
        </div>
      </div>

      {/* ── Flagship hero card: Money Transfer Comparison ── */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 18, overflow: 'hidden', boxShadow: 'var(--shadow-card)', marginBottom: 22 }}>
        <div style={{ height: 5, background: 'linear-gradient(90deg, #6E5BFF, #1FA8A0, #7C3AED)' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 24, padding: '22px 26px', flexWrap: 'wrap' }}>
          {/* Left: identity + team */}
          <div style={{ flex: 1, minWidth: 320 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#6E5BFF', letterSpacing: '1.5px', textTransform: 'uppercase', marginBottom: 8 }}>▸ FLAGSHIP WORKFLOW</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)', letterSpacing: '-0.5px', marginBottom: 6 }}>Money Transfer Comparison</div>
            <div style={{ fontSize: 14, color: 'var(--ink2)', marginBottom: 16, lineHeight: 1.5 }}>
              {REMITTANCE_CLEARED.request}. Research gathers provider quotes, Compliance screens the
              transfer, Analyst picks the best deal and drafts the Telegram reply.
            </div>
            {/* Team chips: Rs → Cm → An */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {HERO_TEAM.map((a, i) => (
                <div key={a.mg} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 34, height: 34, borderRadius: 8, background: `${a.accent}1A`, border: `1px solid ${a.accent}33`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, color: a.accent }}>{a.mg}</span>
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--ink2)', fontWeight: 500 }}>{a.name}</span>
                  </div>
                  {i < HERO_TEAM.length - 1 && <span style={{ color: 'var(--ink3)', fontSize: 13 }}>→</span>}
                </div>
              ))}
            </div>
          </div>
          {/* Right: CTAs */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 220 }}>
            <button
              onClick={() => runFlagship('run-1042')}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '13px 22px', borderRadius: 12, border: 'none', background: 'var(--blue)', color: 'white', fontSize: 15, fontWeight: 600, fontFamily: 'var(--font-ui)', cursor: 'pointer', boxShadow: 'var(--shadow-cta)' }}
            >
              <div style={{ width: 0, height: 0, borderLeft: '10px solid white', borderTop: '6px solid transparent', borderBottom: '6px solid transparent' }} />
              Run this workflow
            </button>
            <button
              onClick={() => runFlagship('run-1043')}
              style={{ padding: '9px 18px', borderRadius: 10, border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink2)', fontSize: 13, fontFamily: 'var(--font-ui)', cursor: 'pointer', fontWeight: 500 }}
            >
              View FLAGGED example →
            </button>
            <button
              onClick={() => setScreen('canvas')}
              style={{ background: 'none', border: 'none', color: 'var(--blue)', fontSize: 12, fontFamily: 'var(--font-ui)', cursor: 'pointer', padding: '2px 0' }}
            >
              Open in canvas →
            </button>
          </div>
        </div>
      </div>

      {/* KPI tiles */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 22 }}>
        {KPI_TILES.map(kpi => (
          <div key={kpi.label} style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 14, padding: '18px 20px', boxShadow: 'var(--shadow-card)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 10 }}>
              <div style={{ width: 6, height: 6, borderRadius: 3, background: STATUS_COLOR[kpi.status] }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '1px', textTransform: 'uppercase' }}>{kpi.label}</span>
            </div>
            <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: '-1px', color: 'var(--ink)', lineHeight: 1, marginBottom: 5 }}>{kpi.value}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink3)' }}>{kpi.delta}</div>
          </div>
        ))}
      </div>

      {/* Two-column: Recent runs + Agent library */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.55fr 1fr', gap: 16, marginBottom: 22 }}>

        {/* Recent runs */}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 14, padding: '20px', boxShadow: 'var(--shadow-card)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--ink)' }}>Recent runs</div>
            <button onClick={() => { setSelectedRunId('run-1042'); setScreen('run') }} style={{ fontSize: 12, color: 'var(--blue)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-ui)' }}>View all →</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {MOCK_RUN_SUMMARIES.map(run => (
              <div
                key={run.id}
                onClick={() => { setSelectedRunId(run.id); setScreen('run') }}
                style={{ display: 'grid', gridTemplateColumns: '14px 1fr auto auto', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 10, background: 'var(--surface2)', cursor: 'pointer' }}
              >
                <div
                  className={run.status === 'running' ? 'yo-blink' : undefined}
                  style={{ width: 8, height: 8, borderRadius: 4, background: STATUS_COLOR[run.status] }}
                />
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--ink)', marginBottom: 2 }}>{run.name}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '0.5px', marginBottom: 5 }}>{run.id} · {run.started}</div>
                  <div style={{ height: 3, borderRadius: 2, background: 'var(--line)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${run.progress}%`, background: STATUS_COLOR[run.status], borderRadius: 2 }} />
                  </div>
                </div>
                <div style={{ padding: '3px 8px', borderRadius: 6, background: STATUS_BG[run.status], color: STATUS_COLOR[run.status], fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.8px', textTransform: 'uppercase', fontWeight: 600, whiteSpace: 'nowrap' }}>
                  {STATUS_LABEL[run.status]}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink3)', whiteSpace: 'nowrap' }}>{run.cost}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Agent library */}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 14, padding: '20px', boxShadow: 'var(--shadow-card)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--ink)' }}>Agent library</div>
            <button onClick={() => setScreen('builder')} style={{ fontSize: 12, color: 'var(--blue)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-ui)' }}>+ New</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {MOCK_AGENTS.map(agent => (
              <div
                key={agent.id}
                onClick={() => setScreen('builder')}
                style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 12, padding: '11px 12px', borderRadius: 10, background: 'var(--surface2)', cursor: 'pointer' }}
              >
                {/* Studs */}
                <div style={{ position: 'absolute', top: -3, left: 18, display: 'flex', gap: 3 }}>
                  <div style={{ width: 5, height: 5, borderRadius: 2, background: agent.accent }} />
                  <div style={{ width: 5, height: 5, borderRadius: 2, background: agent.accent }} />
                </div>
                {/* Monogram chip */}
                <div style={{ width: 32, height: 32, borderRadius: 8, background: `${agent.accent}1A`, border: `1px solid ${agent.accent}33`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, color: agent.accent }}>{agent.monogram}</span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--ink)' }}>{agent.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--ink3)' }}>{agent.role}</div>
                </div>
                <div style={{ width: 7, height: 7, borderRadius: 4, background: '#1E9E6A', flexShrink: 0 }} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Starter kits */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
          <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--ink)' }}>Starter kits</div>
          <button onClick={() => setScreen('gallery')} style={{ fontSize: 12, color: 'var(--blue)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-ui)' }}>Browse all →</button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
          {MOCK_KITS.map(kit => (
            <div
              key={kit.id}
              onClick={() => setScreen('gallery')}
              style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 14, overflow: 'hidden', cursor: 'pointer', boxShadow: 'var(--shadow-card)' }}
            >
              <div style={{ height: 5, background: kit.color }} />
              <div style={{ padding: '14px 16px' }}>
                <div style={{ display: 'flex', gap: 6, marginBottom: 10, minHeight: 26 }}>
                  {kit.stations.map((m, i) => (
                    <div key={i} style={{ width: 26, height: 26, borderRadius: 6, background: 'var(--surface2)', border: '1px solid var(--line)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 700, color: 'var(--ink2)' }}>{m}</span>
                    </div>
                  ))}
                </div>
                <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)', marginBottom: 4 }}>{kit.name}</div>
                <div style={{ fontSize: 12, color: 'var(--ink2)', marginBottom: 12, lineHeight: 1.45 }}>{kit.description}</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--blue)', letterSpacing: '0.5px' }}>Open kit →</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)' }}>{kit.costEstimate}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
