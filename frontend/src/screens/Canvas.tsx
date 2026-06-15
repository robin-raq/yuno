import { useState } from 'react'
import type { Screen } from '../types'

interface Props {
  setScreen: (s: Screen) => void
}

type Template = 'remittance' | 'dev'

const REMITTANCE_NODES = [
  { id: 'start',      x: 40,  y: 160, kind: 'terminal', label: 'START',      symbol: '▶', fill: '#1B2440', textColor: 'white' },
  { id: 'research',   x: 160, y: 150, kind: 'station',  label: 'Research',   mg: 'Rs', accent: '#6E5BFF', role: 'Remittance researcher' },
  { id: 'compliance', x: 400, y: 150, kind: 'station',  label: 'Compliance', mg: 'Cm', accent: '#1FA8A0', role: 'Compliance (scripted)' },
  { id: 'analyst',    x: 640, y: 150, kind: 'station',  label: 'Analyst',    mg: 'An', accent: '#7C3AED', role: 'Remittance analyst' },
  { id: 'end',        x: 860, y: 160, kind: 'terminal', label: 'END',        symbol: '◼', fill: 'white', textColor: '#929BB0', border: true },
]

const DEV_NODES = [
  { id: 'start',      x: 40,  y: 160, kind: 'terminal', label: 'START',      symbol: '▶', fill: '#1B2440', textColor: 'white' },
  { id: 'coder',      x: 160, y: 150, kind: 'station',  label: 'Coder',      mg: 'Co', accent: '#2F6BFF', role: 'Software Engineer' },
  { id: 'reviewer',   x: 400, y: 150, kind: 'station',  label: 'Reviewer',   mg: 'Rv', accent: '#F4A024', role: 'Code Reviewer' },
  { id: 'deployer',   x: 640, y: 150, kind: 'station',  label: 'Deployer',   mg: 'Dp', accent: '#1E9E6A', role: 'DevOps Engineer' },
  { id: 'end',        x: 860, y: 160, kind: 'terminal', label: 'END',        symbol: '◼', fill: 'white', textColor: '#929BB0', border: true },
]

const TEMPLATE_META: Record<Template, { name: string; stations: number; links: number; forwardEdgeLabel: string; forwardEdgeColor: string; loopEdgeLabel: string; loopEdgeColor: string }> = {
  remittance: { name: 'Remittance Comparison', stations: 3, links: 4, forwardEdgeLabel: 'COMPLIANCE=CLEARED', forwardEdgeColor: '#1E9E6A', loopEdgeLabel: 'ANALYST=NEEDS_MORE_DATA · ↻ MAX 2×', loopEdgeColor: '#F4A024' },
  dev:        { name: 'Dev Pipeline',          stations: 3, links: 4, forwardEdgeLabel: 'APPROVED',           forwardEdgeColor: '#1E9E6A', loopEdgeLabel: 'REJECTED · ↻ MAX 3×',                loopEdgeColor: '#E5484D' },
}

const AGENT_LIBRARY: Record<Template, { mg: string; name: string; accent: string }[]> = {
  remittance: [
    { mg: 'Rs', name: 'Research',   accent: '#6E5BFF' },
    { mg: 'Cm', name: 'Compliance', accent: '#1FA8A0' },
    { mg: 'An', name: 'Analyst',    accent: '#7C3AED' },
  ],
  dev: [
    { mg: 'Co', name: 'Coder',    accent: '#2F6BFF' },
    { mg: 'Rv', name: 'Reviewer', accent: '#F4A024' },
    { mg: 'Dp', name: 'Deployer', accent: '#1E9E6A' },
  ],
}

const NODE_W = 160
const NODE_H = 86
const TERM_W = 96
const TERM_H = 54

// Edge: bezier control offset
function fwdEdge(x1: number, y1: number, x2: number, y2: number) {
  const dx = x2 - x1
  const cx = Math.max(46, Math.abs(dx) * 0.45)
  return `M ${x1} ${y1} C ${x1 + cx} ${y1}, ${x2 - cx} ${y2}, ${x2} ${y2}`
}

// Backward loop bowing downward 78px
function loopEdge(x1: number, y1: number, x2: number, y2: number) {
  const cy = y1 + 78
  return `M ${x1} ${y1} C ${x1} ${cy}, ${x2} ${cy}, ${x2} ${y2}`
}

// port helpers (center of right/left/bottom edges)
function rPort(x: number, y: number, w: number, h: number) { return [x + w, y + h / 2] as const }
function lPort(x: number, y: number, h: number)              { return [x,     y + h / 2] as const }
function bPort(x: number, y: number, w: number, h: number)   { return [x + w / 2, y + h] as const }

export default function Canvas({ setScreen }: Props) {
  const [selected, setSelected]       = useState<string | null>(null)
  const [toastVisible, setToastVisible] = useState(false)
  const [template, setTemplate]       = useState<Template>('remittance')

  function showToast() {
    setToastVisible(true)
    setTimeout(() => setToastVisible(false), 2200)
  }

  function switchTemplate(t: Template) {
    setTemplate(t)
    setSelected(null)
  }

  const isRem = template === 'remittance'
  const NODES = isRem ? REMITTANCE_NODES : DEV_NODES
  const meta  = TEMPLATE_META[template]

  const sel = selected ? NODES.find(n => n.id === selected) ?? null : null

  // Named node refs (index-stable for both templates: 0=start, 1=first, 2=second, 3=third, 4=end)
  const [startN, firstN, secondN, thirdN, endN] = NODES

  // Forward edges
  const edgeStartFirst  = fwdEdge(...rPort(startN.x,  startN.y,  TERM_W, TERM_H), ...lPort(firstN.x,  firstN.y,  NODE_H))
  const edgeFirstSecond = fwdEdge(...rPort(firstN.x,  firstN.y,  NODE_W, NODE_H), ...lPort(secondN.x, secondN.y, NODE_H))
  const edgeSecondThird = fwdEdge(...rPort(secondN.x, secondN.y, NODE_W, NODE_H), ...lPort(thirdN.x,  thirdN.y,  NODE_H))
  const edgeThirdEnd    = fwdEdge(...rPort(thirdN.x,  thirdN.y,  NODE_W, NODE_H), ...lPort(endN.x,    endN.y,    TERM_H))

  // Loop edge source differs by template:
  //  dev        — Reviewer (second) → Coder (first)      [REJECTED]
  //  remittance — Analyst  (third)  → Research (first)    [ANALYST=NEEDS_MORE_DATA]
  const loopSrc = isRem ? thirdN : secondN
  const [loopSx, loopSy] = bPort(loopSrc.x, loopSrc.y, NODE_W, NODE_H)
  const [fstBx, fstBy]   = bPort(firstN.x,  firstN.y,  NODE_W, NODE_H)
  const edgeLoop = loopEdge(loopSx, loopSy, fstBx, fstBy)
  const loopLabelX = isRem ? (firstN.x + NODE_W + thirdN.x) / 2 : (firstN.x + NODE_W + secondN.x) / 2

  // FLAGGED halt stub (remittance only): Compliance has NO seeded edge for a
  // FLAGGED outcome — the run ends by end-node fallthrough (KTD2). We draw a
  // dashed red stub to a halt marker, never a solid edge to another agent.
  const [cmpBx, cmpBy] = bPort(secondN.x, secondN.y, NODE_W, NODE_H)
  const flaggedStub = `M ${cmpBx} ${cmpBy} L ${cmpBx} ${cmpBy + 40}`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 60px)' }}>

      {/* Toolbar */}
      <div style={{ background: 'var(--surface)', borderBottom: '1px solid var(--line)', height: 54, display: 'flex', alignItems: 'center', paddingInline: 20, gap: 12, flexShrink: 0 }}>
        {/* Template tabs — remittance is the flagship, listed first */}
        <div style={{ display: 'flex', gap: 2, background: 'var(--surface2)', borderRadius: 10, padding: 3 }}>
          {(['remittance', 'dev'] as Template[]).map(t => (
            <button
              key={t}
              onClick={() => switchTemplate(t)}
              style={{
                padding: '4px 12px', borderRadius: 8, border: 'none', cursor: 'pointer',
                fontSize: 12, fontFamily: 'var(--font-ui)', fontWeight: template === t ? 600 : 400,
                background: template === t ? 'white' : 'transparent',
                color: template === t ? 'var(--ink)' : 'var(--ink3)',
                boxShadow: template === t ? '0 1px 4px rgba(20,27,46,0.10)' : 'none',
                transition: 'all 0.12s',
              }}
            >
              {TEMPLATE_META[t].name}
            </button>
          ))}
        </div>
        <div style={{ width: 1, height: 28, background: 'var(--line)' }} />
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)' }}>
          {meta.stations} stations · {meta.links} links · draft
        </div>
        <div style={{ flex: 1 }} />
        {/* Legend — updates with template */}
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          {(isRem
            ? [['#1E9E6A', 'CLEARED'], ['#F4A024', 'NEEDS_MORE_DATA'], ['#E5484D', 'FLAGGED'], ['#9098AC', 'ALWAYS']]
            : [[meta.forwardEdgeColor, 'APPROVED'], [meta.loopEdgeColor, 'REJECTED'], ['#9098AC', 'ALWAYS']]
          ).map(([color, label]) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <div style={{ width: 6, height: 6, borderRadius: 3, background: color }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink3)', letterSpacing: '0.5px' }}>{label}</span>
            </div>
          ))}
        </div>
        <button onClick={showToast} style={{ padding: '7px 14px', borderRadius: 10, border: '1px solid var(--line)', background: 'white', fontSize: 13, fontFamily: 'var(--font-ui)', cursor: 'pointer', color: 'var(--ink)' }}>Save template</button>
        <button onClick={() => setScreen('run')} style={{ padding: '7px 14px', borderRadius: 10, border: 'none', background: 'var(--blue)', color: 'white', fontSize: 13, fontFamily: 'var(--font-ui)', cursor: 'pointer', fontWeight: 600, boxShadow: 'var(--shadow-cta)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 0, height: 0, borderLeft: '8px solid white', borderTop: '5px solid transparent', borderBottom: '5px solid transparent' }} />
          Run workflow
        </button>
      </div>

      {/* 3-pane body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Left library */}
        <div style={{ width: 224, background: 'var(--surface)', borderRight: '1px solid var(--line)', padding: '16px', flexShrink: 0, overflowY: 'auto' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '1.5px', textTransform: 'uppercase', marginBottom: 6 }}>AGENT LIBRARY</div>
          <div style={{ fontSize: 11, color: 'var(--ink3)', marginBottom: 14 }}>Drag a block onto the floor.</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {AGENT_LIBRARY[template].map(a => (
              <div key={a.mg} style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 10, padding: '10px 10px', borderRadius: 10, background: 'var(--surface2)', border: '1px solid var(--line)', cursor: 'grab', userSelect: 'none' }}>
                <div style={{ position: 'absolute', top: -3, left: 14, display: 'flex', gap: 3 }}>
                  <div style={{ width: 5, height: 5, borderRadius: 2, background: a.accent }} />
                  <div style={{ width: 5, height: 5, borderRadius: 2, background: a.accent }} />
                </div>
                <div style={{ width: 30, height: 30, borderRadius: 7, background: `${a.accent}1A`, border: `1px solid ${a.accent}33`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 10, color: a.accent }}>{a.mg}</span>
                </div>
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--ink)', flex: 1 }}>{a.name}</div>
                <div style={{ color: 'var(--ink3)', fontSize: 14 }}>⠿</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 20, border: '1.5px dashed var(--line)', borderRadius: 10, padding: '14px 10px', textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)' }}>Drop here to add to canvas</div>
          </div>
        </div>

        {/* Canvas */}
        <div
          style={{ flex: 1, overflow: 'auto', position: 'relative' }}
          onClick={e => { if (e.target === e.currentTarget) setSelected(null) }}
        >
          <div style={{
            width: 1180, height: 800, position: 'relative', cursor: 'default',
            backgroundColor: '#F4F6FB',
            backgroundImage: [
              'linear-gradient(#E7EBF4 1px,transparent 1px)',
              'linear-gradient(90deg,#E7EBF4 1px,transparent 1px)',
              'linear-gradient(#DBE2F0 1px,transparent 1px)',
              'linear-gradient(90deg,#DBE2F0 1px,transparent 1px)',
            ].join(','),
            backgroundSize: '24px 24px, 24px 24px, 120px 120px, 120px 120px',
          }}>

            {/* SVG edge overlay */}
            <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
              {/* ALWAYS edges (gray): start→first, first→second (+ third→end for dev) */}
              {[edgeStartFirst, edgeFirstSecond, ...(isRem ? [] : [edgeThirdEnd])].map((d, i) => (
                <g key={i}>
                  <path d={d} fill="none" stroke="#E1E6F0" strokeWidth={12} strokeLinecap="round" />
                  <path d={d} fill="none" stroke="#9098AC" strokeWidth={3.2} strokeDasharray="0.5 13" strokeLinecap="round" className="yo-dash" />
                </g>
              ))}
              {/* Forward edge second→third (APPROVED / COMPLIANCE=CLEARED) */}
              <g>
                <path d={edgeSecondThird} fill="none" stroke="#E1E6F0" strokeWidth={12} strokeLinecap="round" />
                <path d={edgeSecondThird} fill="none" stroke={meta.forwardEdgeColor} strokeWidth={3.2} strokeDasharray="0.5 13" strokeLinecap="round" className="yo-dash" />
                <text x={(secondN.x + NODE_W + thirdN.x) / 2} y={secondN.y + NODE_H / 2 - 10}
                  textAnchor="middle" fontSize={9} fill={meta.forwardEdgeColor} fontFamily="JetBrains Mono" fontWeight={600}>
                  {meta.forwardEdgeLabel}
                </text>
              </g>
              {/* Remittance: Analyst → END as a DASHED fallthrough (no seeded edge; the
                  run ends when Analyst returns RECOMMENDATION and no edge matches). */}
              {isRem && (
                <g>
                  <path d={edgeThirdEnd} fill="none" stroke="#9CC4AE" strokeWidth={2} strokeDasharray="5 6" strokeLinecap="round" />
                  <text x={(thirdN.x + NODE_W + endN.x) / 2} y={thirdN.y + NODE_H / 2 - 10}
                    textAnchor="middle" fontSize={8.5} fill="#5B8A6F" fontFamily="JetBrains Mono" fontWeight={600}>
                    RECOMMENDATION ⤳ done
                  </text>
                </g>
              )}
              {/* Loop edge (REJECTED / ANALYST=NEEDS_MORE_DATA) */}
              <g>
                <path d={edgeLoop} fill="none" stroke="#E1E6F0" strokeWidth={12} strokeLinecap="round" />
                <path d={edgeLoop} fill="none" stroke={meta.loopEdgeColor} strokeWidth={3.2} strokeDasharray="0.5 13" strokeLinecap="round" className="yo-dash" />
                <text x={loopLabelX} y={thirdN.y + NODE_H + 56}
                  textAnchor="middle" fontSize={9} fill={meta.loopEdgeColor} fontFamily="JetBrains Mono" fontWeight={600}>
                  {meta.loopEdgeLabel}
                </text>
              </g>
              {/* Remittance: FLAGGED halt stub from Compliance — dashed red, no target agent */}
              {isRem && (
                <g>
                  <path d={flaggedStub} fill="none" stroke="#E5484D" strokeWidth={2} strokeDasharray="4 5" strokeLinecap="round" />
                  <circle cx={cmpBx} cy={cmpBy + 40} r={3.5} fill="#E5484D" />
                </g>
              )}
              {/* Snap nubs at forward edge targets */}
              {[
                lPort(firstN.x,  firstN.y,  NODE_H),
                lPort(secondN.x, secondN.y, NODE_H),
                lPort(thirdN.x,  thirdN.y,  NODE_H),
                ...(isRem ? [] : [lPort(endN.x, endN.y, TERM_H)]),
                bPort(firstN.x,  firstN.y,  NODE_W, NODE_H),
              ].map(([cx, cy], i) => (
                <circle key={i} cx={cx} cy={cy} r={5} fill="#9098AC" />
              ))}
            </svg>

            {/* Remittance: FLAGGED halt pill (HTML, below Compliance) */}
            {isRem && (
              <div style={{ position: 'absolute', left: secondN.x + 6, top: secondN.y + NODE_H + 48, display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 8, background: '#FCE9E9', border: '1px dashed #E5484D' }}>
                <span style={{ fontSize: 11 }}>⚠</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#B0232A', fontWeight: 600, letterSpacing: '0.5px' }}>FLAGGED → halt (no edge)</span>
              </div>
            )}

            {/* Terminal: START */}
            <div
              onClick={e => { e.stopPropagation(); setSelected('start') }}
              style={{ position: 'absolute', left: startN.x, top: startN.y, width: TERM_W, height: TERM_H, borderRadius: 12, background: startN.fill, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, cursor: 'pointer', boxShadow: selected === 'start' ? '0 0 0 2px #2F6BFF' : 'none' }}
            >
              <div style={{ width: 0, height: 0, borderLeft: '12px solid white', borderTop: '7px solid transparent', borderBottom: '7px solid transparent' }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 10, color: 'rgba(255,255,255,0.7)', letterSpacing: '1px' }}>START</span>
            </div>

            {/* Station nodes */}
            {[firstN, secondN, thirdN].map(n => {
              const isSelected = selected === n.id
              const ag = n as typeof firstN & { mg: string; accent: string; role: string }
              return (
                <div
                  key={n.id}
                  onClick={e => { e.stopPropagation(); setSelected(isSelected ? null : n.id) }}
                  style={{
                    position: 'absolute', left: n.x, top: n.y, width: NODE_W,
                    borderRadius: 12, background: 'white', border: `2px solid ${isSelected ? ag.accent : 'var(--line)'}`,
                    boxShadow: isSelected ? `0 10px 26px rgba(20,27,46,0.18)` : '0 4px 12px rgba(20,27,46,0.08)',
                    cursor: 'pointer', overflow: 'visible',
                  }}
                >
                  {/* Studs */}
                  <div style={{ position: 'absolute', top: -4, left: 12, display: 'flex', gap: 4 }}>
                    <div style={{ width: 7, height: 7, borderRadius: 2, background: ag.accent }} />
                    <div style={{ width: 7, height: 7, borderRadius: 2, background: ag.accent }} />
                  </div>
                  {/* Color band */}
                  <div style={{ height: 4, background: ag.accent, borderRadius: '10px 10px 0 0' }} />
                  <div style={{ padding: '10px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ width: 30, height: 30, borderRadius: 7, background: `${ag.accent}1A`, border: `1px solid ${ag.accent}33`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 10, color: ag.accent }}>{ag.mg}</span>
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--ink)' }}>{n.label}</div>
                        <div style={{ fontSize: 10, color: 'var(--ink3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ag.role}</div>
                      </div>
                      <div style={{ width: 7, height: 7, borderRadius: 4, background: '#1E9E6A', flexShrink: 0 }} />
                    </div>
                  </div>
                </div>
              )
            })}

            {/* Terminal: END */}
            <div
              onClick={e => { e.stopPropagation(); setSelected('end') }}
              style={{ position: 'absolute', left: endN.x, top: endN.y, width: TERM_W, height: TERM_H, borderRadius: 12, background: 'white', border: selected === 'end' ? '2px solid #2F6BFF' : '2px solid var(--line)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, cursor: 'pointer' }}
            >
              <div style={{ width: 10, height: 10, borderRadius: 1, background: '#929BB0' }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 10, color: 'var(--ink3)', letterSpacing: '1px' }}>END</span>
            </div>

            {/* Static stub notice */}
            <div style={{ position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)', padding: '5px 14px', borderRadius: 20, background: 'rgba(255,255,255,0.9)', border: '1px solid var(--line)', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', whiteSpace: 'nowrap', backdropFilter: 'blur(4px)' }}>
              Canvas — static preview · interactive drag/connect coming in a future sprint
            </div>
          </div>
        </div>

        {/* Right inspector */}
        <div style={{ width: 278, background: 'var(--surface)', borderLeft: '1px solid var(--line)', padding: '16px', flexShrink: 0, overflowY: 'auto' }}>
          {!sel ? (
            <>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '1px', textTransform: 'uppercase', marginBottom: 14 }}>WORKFLOW</div>
              <div style={{ background: 'var(--surface2)', borderRadius: 10, padding: '14px', marginBottom: 14 }}>
                <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)', marginBottom: 10 }}>{meta.name}</div>
                {[['Stations', String(meta.stations)], ['Belts', String(meta.links)], ['Est. cost', isRem ? '~$0.03/run' : '~$0.84/run']].map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <div style={{ fontSize: 12, color: 'var(--ink2)' }}>{k}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink)' }}>{v}</div>
                  </div>
                ))}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '1px', textTransform: 'uppercase', marginBottom: 10 }}>SIGNAL STATES</div>
              {(isRem
                ? [
                    { color: '#929BB0', label: 'PENDING',         desc: 'Waiting in queue' },
                    { color: '#2F6BFF', label: 'RUNNING',         desc: 'Agent is working' },
                    { color: '#1E9E6A', label: 'CLEARED',         desc: 'Compliance passed → Analyst' },
                    { color: '#F4A024', label: 'NEEDS_MORE_DATA', desc: 'Analyst loops back to Research' },
                    { color: '#E5484D', label: 'FLAGGED',         desc: 'Compliance halt — no edge, run ends' },
                  ]
                : [
                    { color: '#929BB0', label: 'PENDING',   desc: 'Waiting in queue' },
                    { color: '#2F6BFF', label: 'RUNNING',   desc: 'Agent is working' },
                    { color: '#1E9E6A', label: 'COMPLETED', desc: 'Task succeeded' },
                    { color: '#E5484D', label: 'REJECTED',  desc: 'Reviewer loops back to Coder' },
                    { color: '#F4A024', label: 'APPROVAL',  desc: 'Human gate before deploy' },
                  ]
              ).map(s => (
                <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <div style={{ width: 8, height: 8, borderRadius: 4, background: s.color, flexShrink: 0 }} />
                  <div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: s.color, fontWeight: 600 }}>{s.label}</div>
                    <div style={{ fontSize: 11, color: 'var(--ink3)' }}>{s.desc}</div>
                  </div>
                </div>
              ))}
            </>
          ) : (
            <>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '1px', textTransform: 'uppercase', marginBottom: 12 }}>STATION</div>
              {sel.kind === 'station' ? (() => {
                const ag = sel as typeof firstN & { mg: string; accent: string; role: string }
                return (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                      <div style={{ width: 38, height: 38, borderRadius: 10, background: `${ag.accent}1A`, border: `1px solid ${ag.accent}33`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13, color: ag.accent }}>{ag.mg}</span>
                      </div>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--ink)' }}>{sel.label}</div>
                        <div style={{ fontSize: 12, color: 'var(--ink3)' }}>{ag.role}</div>
                      </div>
                    </div>
                    {isRem && sel.id === 'compliance' && (
                      <div style={{ background: '#E6F6F4', border: '1px solid #1FA8A0', borderRadius: 8, padding: '8px 10px', marginBottom: 12, fontSize: 11, color: '#0F6E68', lineHeight: 1.5 }}>
                        Deterministic rules engine (no LLM). Emits <span style={{ fontFamily: 'var(--font-mono)' }}>COMPLIANCE=CLEARED</span> or <span style={{ fontFamily: 'var(--font-mono)' }}>FLAGGED</span>.
                      </div>
                    )}
                    <button onClick={() => setScreen('builder')} style={{ width: '100%', padding: '9px 0', borderRadius: 10, border: 'none', background: 'var(--navy)', color: 'white', fontSize: 13, fontFamily: 'var(--font-ui)', cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Edit this block →</button>
                    <button onClick={() => setSelected(null)} style={{ width: '100%', padding: '9px 0', borderRadius: 10, border: 'none', background: '#FCE9E9', color: '#E5484D', fontSize: 13, fontFamily: 'var(--font-ui)', cursor: 'pointer', fontWeight: 500 }}>Remove from canvas</button>
                  </>
                )
              })() : (
                <div style={{ fontSize: 13, color: 'var(--ink2)' }}>Terminal node — {sel.label}</div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Toast */}
      {toastVisible && (
        <div style={{ position: 'fixed', bottom: 28, left: '50%', transform: 'translateX(-50%)', background: 'var(--navy)', color: 'white', padding: '10px 20px', borderRadius: 12, fontFamily: 'var(--font-mono)', fontSize: 13, boxShadow: 'var(--shadow-dark)', zIndex: 200, whiteSpace: 'nowrap' }}>
          ✓ Template saved
        </div>
      )}
    </div>
  )
}
