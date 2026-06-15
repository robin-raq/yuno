import { useState, useEffect, useRef } from 'react'
import type { Screen } from '../types'

interface Props {
  setScreen: (s: Screen) => void
}

interface AgentDraft {
  name: string
  role: string
  color: string
  instructions: string
  tools: string[]
  persistentMemory: boolean
  teamContext: boolean
  contextWindow: number
  maxLoopIterations: number
  maxCostPerRun: number
  requiresApproval: boolean
  model: string
  temperature: number
}

const ACCENT_COLORS = ['#2F6BFF', '#6E5BFF', '#1FA8A0', '#1E9E6A', '#F4A024', '#E5484D']
const ALL_TOOLS = ['Git', 'Code Exec', 'File I/O', 'Web Search', 'Browser', 'RAG', 'Lint', 'Diff', 'Policy Check', 'CI/CD', 'Secrets', 'Rollback', 'Summarize', 'Format', 'Database', 'Slack']
const MODELS = ['claude-opus-4', 'claude-sonnet-4', 'claude-haiku-4']
const TEST_LINES = [
  '$ initializing runtime environment…',
  '$ loading agent context and tools',
  '$ executing: test prompt',
  '$ tool_call: code_execution → success',
  '✓ Test passed · 2.1k tokens · ~$0.04',
]

function monogram(name: string) {
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase() || 'AG'
}

const SECTION_STYLE = {
  background: 'var(--surface)', border: '1px solid var(--line)',
  borderRadius: 14, padding: '20px', boxShadow: 'var(--shadow-card)', marginBottom: 14,
}

const LABEL_STYLE: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--blue)',
  letterSpacing: '1.5px', textTransform: 'uppercase', marginBottom: 14, display: 'block',
}

const INPUT_STYLE: React.CSSProperties = {
  width: '100%', padding: '9px 12px', borderRadius: 10, border: '1px solid var(--line)',
  background: 'var(--surface2)', fontSize: 13, fontFamily: 'var(--font-ui)', color: 'var(--ink)',
  outline: 'none',
}

export default function Builder({ setScreen }: Props) {
  const [draft, setDraft] = useState<AgentDraft>({
    name: '', role: '', color: '#2F6BFF',
    instructions: '',
    tools: ['Git', 'Code Exec', 'File I/O'],
    persistentMemory: true, teamContext: false, contextWindow: 64,
    maxLoopIterations: 3, maxCostPerRun: 2.0, requiresApproval: false,
    model: 'claude-sonnet-4', temperature: 0.3,
  })

  const [testRunning, setTestRunning] = useState(false)
  const [testLines, setTestLines] = useState<string[]>([])
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function patch<K extends keyof AgentDraft>(key: K, val: AgentDraft[K]) {
    setDraft(d => ({ ...d, [key]: val }))
  }

  function toggleTool(tool: string) {
    setDraft(d => ({
      ...d,
      tools: d.tools.includes(tool) ? d.tools.filter(t => t !== tool) : [...d.tools, tool],
    }))
  }

  function runTest() {
    if (testRunning) return
    setTestRunning(true)
    setTestLines([])
    let i = 0
    intervalRef.current = setInterval(() => {
      i++
      setTestLines(TEST_LINES.slice(0, i))
      if (i >= TEST_LINES.length) {
        clearInterval(intervalRef.current!)
        setTestRunning(false)
      }
    }, 350)
  }

  useEffect(() => () => { if (intervalRef.current) clearInterval(intervalRef.current) }, [])

  const displayName = draft.name || 'New Agent'
  const mg = monogram(displayName)

  return (
    <div>
      {/* Sub-header */}
      <div style={{ background: 'var(--surface)', borderBottom: '1px solid var(--line)', padding: '0 28px', height: 52, display: 'flex', alignItems: 'center', gap: 16, position: 'sticky', top: 60, zIndex: 90 }}>
        <button onClick={() => setScreen('dashboard')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink2)', fontSize: 18, padding: 0, lineHeight: 1 }}>‹</button>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', letterSpacing: '1.5px', textTransform: 'uppercase' }}>FACTORY / AGENTS</div>
        <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--ink)', flex: 1 }}>{draft.name ? `Edit: ${draft.name}` : 'New agent block'}</div>
        <button style={{ padding: '7px 14px', borderRadius: 10, border: '1px solid var(--line)', background: 'white', fontSize: 13, fontFamily: 'var(--font-ui)', cursor: 'pointer', color: 'var(--ink)' }}>Test agent</button>
        <button style={{ padding: '7px 16px', borderRadius: 10, border: 'none', background: 'var(--blue)', color: 'white', fontSize: 13, fontFamily: 'var(--font-ui)', cursor: 'pointer', fontWeight: 600, boxShadow: 'var(--shadow-cta)' }}>Save block</button>
      </div>

      <div style={{ maxWidth: 1240, margin: '0 auto', padding: '24px 28px 64px', display: 'grid', gridTemplateColumns: '1.45fr 0.95fr', gap: 24 }}>

        {/* Left: form */}
        <div>
          {/* 01 Identity */}
          <div style={SECTION_STYLE}>
            <span style={LABEL_STYLE}>01 · IDENTITY</span>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
              {ACCENT_COLORS.map(c => (
                <div
                  key={c}
                  onClick={() => patch('color', c)}
                  style={{ width: 26, height: 26, borderRadius: 13, background: c, cursor: 'pointer', outline: draft.color === c ? `2px solid white` : 'none', boxShadow: draft.color === c ? `0 0 0 4px ${c}` : 'none' }}
                />
              ))}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <div style={{ fontSize: 12, color: 'var(--ink2)', marginBottom: 5 }}>Agent name</div>
                <input value={draft.name} onChange={e => patch('name', e.target.value)} placeholder="e.g. Coder" style={INPUT_STYLE} />
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--ink2)', marginBottom: 5 }}>Role</div>
                <input value={draft.role} onChange={e => patch('role', e.target.value)} placeholder="e.g. Software Engineer" style={INPUT_STYLE} />
              </div>
            </div>
          </div>

          {/* 02 System instructions */}
          <div style={SECTION_STYLE}>
            <span style={LABEL_STYLE}>02 · SYSTEM INSTRUCTIONS</span>
            <textarea
              value={draft.instructions}
              onChange={e => patch('instructions', e.target.value)}
              placeholder="You are a skilled software engineer. Your job is to…"
              rows={5}
              style={{ ...INPUT_STYLE, fontFamily: 'var(--font-mono)', fontSize: 12, resize: 'vertical', minHeight: 128 }}
            />
          </div>

          {/* 03 Tools */}
          <div style={SECTION_STYLE}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <span style={{ ...LABEL_STYLE, marginBottom: 0 }}>03 · TOOLS & CAPABILITIES</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink3)' }}>{draft.tools.length} installed</span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
              {ALL_TOOLS.map(tool => {
                const on = draft.tools.includes(tool)
                return (
                  <div
                    key={tool}
                    onClick={() => toggleTool(tool)}
                    style={{
                      padding: '5px 11px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontFamily: 'var(--font-mono)',
                      background: on ? `${draft.color}1A` : 'var(--surface2)',
                      border: `1px solid ${on ? draft.color : 'var(--line)'}`,
                      color: on ? draft.color : 'var(--ink2)',
                      display: 'flex', alignItems: 'center', gap: 5,
                    }}
                  >
                    <div style={{ width: 5, height: 5, borderRadius: 3, background: on ? draft.color : 'var(--ink3)' }} />
                    {tool}
                  </div>
                )
              })}
            </div>
          </div>

          {/* 04 Memory */}
          <div style={SECTION_STYLE}>
            <span style={LABEL_STYLE}>04 · MEMORY</span>
            <Toggle label="Persistent memory" value={draft.persistentMemory} onChange={v => patch('persistentMemory', v)} />
            <Toggle label="Share team context" value={draft.teamContext} onChange={v => patch('teamContext', v)} />
            <div style={{ marginTop: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <div style={{ fontSize: 12, color: 'var(--ink2)' }}>Context window</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--blue)' }}>{draft.contextWindow}k tokens</div>
              </div>
              <input type="range" min={8} max={200} step={8} value={draft.contextWindow} onChange={e => patch('contextWindow', Number(e.target.value))} style={{ width: '100%', accentColor: 'var(--blue)' }} />
            </div>
          </div>

          {/* 05 Safety */}
          <div style={SECTION_STYLE}>
            <span style={LABEL_STYLE}>05 · SAFETY LIMITS</span>
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <div style={{ fontSize: 12, color: 'var(--ink2)' }}>Max loop iterations</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--amber)' }}>{draft.maxLoopIterations}×</div>
              </div>
              <input type="range" min={1} max={10} step={1} value={draft.maxLoopIterations} onChange={e => patch('maxLoopIterations', Number(e.target.value))} style={{ width: '100%', accentColor: 'var(--amber)' }} />
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)', marginTop: 4 }}>Caps feedback loops so they can't run forever</div>
            </div>
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <div style={{ fontSize: 12, color: 'var(--ink2)' }}>Max cost / run</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink2)' }}>${draft.maxCostPerRun.toFixed(2)}</div>
              </div>
              <input type="range" min={0.25} max={10} step={0.25} value={draft.maxCostPerRun} onChange={e => patch('maxCostPerRun', Number(e.target.value))} style={{ width: '100%', accentColor: 'var(--ink2)' }} />
            </div>
            <Toggle label="Require human approval" value={draft.requiresApproval} onChange={v => patch('requiresApproval', v)} />
          </div>

          {/* 06 Engine */}
          <div style={SECTION_STYLE}>
            <span style={LABEL_STYLE}>06 · ENGINE</span>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
              {MODELS.map(m => (
                <button
                  key={m}
                  onClick={() => patch('model', m)}
                  style={{
                    padding: '7px 14px', borderRadius: 10, border: 'none', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11,
                    background: draft.model === m ? 'var(--navy)' : 'var(--surface2)',
                    color: draft.model === m ? 'white' : 'var(--ink2)',
                  }}
                >
                  {m}
                </button>
              ))}
            </div>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <div style={{ fontSize: 12, color: 'var(--ink2)' }}>Temperature</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--navy)' }}>{draft.temperature.toFixed(2)}</div>
              </div>
              <input type="range" min={0} max={1} step={0.05} value={draft.temperature} onChange={e => patch('temperature', Number(e.target.value))} style={{ width: '100%', accentColor: 'var(--navy)' }} />
            </div>
          </div>
        </div>

        {/* Right: live preview */}
        <div style={{ position: 'sticky', top: 112, alignSelf: 'flex-start' }}>
          {/* Preview panel */}
          <div style={{
            background: 'white', border: '1px solid var(--line)', borderRadius: 16, overflow: 'hidden',
            boxShadow: 'var(--shadow-float)', marginBottom: 14,
          }}>
            <div style={{
              padding: '14px 18px', borderBottom: '1px solid var(--line)',
              backgroundImage: 'radial-gradient(#D6DCE8 1px, transparent 1px)',
              backgroundSize: '22px 22px', backgroundPosition: '0 0',
            }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink3)', letterSpacing: '2px', textTransform: 'uppercase', marginBottom: 3 }}>LIVE PREVIEW</div>
              <div style={{ fontSize: 11, color: 'var(--ink3)' }}>snaps into any workflow</div>
            </div>

            {/* The block */}
            <div style={{ padding: '24px 18px 18px' }}>
              <div style={{ position: 'relative', width: 286, margin: '0 auto' }}>
                {/* 3 studs */}
                <div style={{ position: 'absolute', top: -5, left: 14, display: 'flex', gap: 5 }}>
                  {[0,1,2].map(i => <div key={i} style={{ width: 8, height: 8, borderRadius: 3, background: draft.color }} />)}
                </div>
                {/* Card */}
                <div style={{ borderRadius: 14, border: '1px solid var(--line)', overflow: 'hidden', boxShadow: '0 4px 12px rgba(20,27,46,0.08)' }}>
                  {/* Color band */}
                  <div style={{ height: 5, background: draft.color }} />
                  <div style={{ padding: '14px 16px' }}>
                    {/* Header row */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                      <div style={{ width: 38, height: 38, borderRadius: 10, background: `${draft.color}1A`, border: `1px solid ${draft.color}33`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13, color: draft.color }}>{mg}</span>
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)' }}>{displayName}</div>
                        <div style={{ fontSize: 11, color: 'var(--ink3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{draft.role || 'No role set'}</div>
                      </div>
                      <div className="yo-pulse" style={{ width: 8, height: 8, borderRadius: 4, background: '#1E9E6A', flexShrink: 0 }} />
                    </div>
                    {/* Modules */}
                    <div style={{ background: 'var(--surface2)', borderRadius: 8, padding: '10px 12px', marginBottom: 12 }}>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink3)', letterSpacing: '1.5px', textTransform: 'uppercase', marginBottom: 7 }}>INSTALLED MODULES</div>
                      {draft.tools.length === 0 ? (
                        <div style={{ border: '1.5px dashed var(--line)', borderRadius: 7, padding: '8px 10px', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)' }}>
                          No modules yet — snap on some capabilities.
                        </div>
                      ) : (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                          {draft.tools.map(t => (
                            <div key={t} style={{ padding: '2px 7px', borderRadius: 5, background: `${draft.color}14`, border: `1px solid ${draft.color}30`, fontFamily: 'var(--font-mono)', fontSize: 9, color: draft.color, display: 'flex', alignItems: 'center', gap: 3 }}>
                              <div style={{ width: 4, height: 4, borderRadius: 2, background: draft.color }} />
                              {t}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    {/* Footer */}
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)' }}>{draft.model}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink3)' }}>temp {draft.temperature.toFixed(2)}</div>
                    </div>
                  </div>
                  {/* Connector nubs */}
                  <div style={{ display: 'flex', justifyContent: 'center', gap: 10, padding: '0 0 8px' }}>
                    {[0,1,2].map(i => <div key={i} style={{ width: 14, height: 5, borderRadius: '0 0 3px 3px', background: '#D6DCE8' }} />)}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Test bench */}
          <div style={{ background: 'var(--navy)', borderRadius: 14, padding: '16px', boxShadow: 'var(--shadow-dark)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'rgba(255,255,255,0.4)', letterSpacing: '1.5px', textTransform: 'uppercase' }}>TEST BENCH</div>
              <button
                onClick={runTest}
                disabled={testRunning}
                style={{ padding: '5px 12px', borderRadius: 7, border: 'none', background: '#1E9E6A', color: 'white', fontSize: 12, fontFamily: 'var(--font-mono)', cursor: testRunning ? 'wait' : 'pointer', fontWeight: 600 }}
              >
                {testRunning ? 'running…' : 'Run test'}
              </button>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.7, minHeight: 96 }}>
              {testLines.length === 0 && !testRunning && (
                <div style={{ color: 'rgba(255,255,255,0.3)' }}>$ awaiting test run…</div>
              )}
              {testLines.map((line, i) => (
                <div key={i} style={{ color: line.startsWith('✓') ? '#1E9E6A' : 'rgba(255,255,255,0.65)' }}>{line}</div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
      <div style={{ fontSize: 13, color: 'var(--ink)' }}>{label}</div>
      <div
        onClick={() => onChange(!value)}
        style={{
          width: 40, height: 22, borderRadius: 11, cursor: 'pointer', position: 'relative',
          background: value ? 'var(--blue)' : '#D6DCE8', transition: 'background 0.15s',
        }}
      >
        <div style={{
          position: 'absolute', top: 2, left: value ? 20 : 2,
          width: 18, height: 18, borderRadius: 9, background: 'white',
          boxShadow: '0 1px 3px rgba(0,0,0,0.15)', transition: 'left 0.15s',
        }} />
      </div>
    </div>
  )
}
