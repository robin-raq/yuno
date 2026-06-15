import { useState } from 'react'
import './styles/tokens.css'
import Dashboard from './screens/Dashboard'
import RunView from './screens/RunView'
import Gallery from './screens/Gallery'
import Builder from './screens/Builder'
import Canvas from './screens/Canvas'
import type { Screen } from './types'

const NAV_LINKS: [Screen, string][] = [
  ['dashboard', 'Factory'],
  ['builder',   'Agents'],
  ['canvas',    'Workflows'],
  ['gallery',   'Templates'],
  ['run',       'Runs'],
]

export default function App() {
  const [screen, setScreen] = useState<Screen>('dashboard')
  const [selectedRunId, setSelectedRunId] = useState<string>('run-1042')

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', fontFamily: 'var(--font-ui)', color: 'var(--ink)' }}>
      {/* Top nav */}
      <nav style={{
        height: 60, background: 'var(--surface)', borderBottom: '1px solid var(--line)',
        display: 'flex', alignItems: 'center', paddingInline: 28, gap: 20,
        position: 'sticky', top: 0, zIndex: 100,
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <div style={{ position: 'relative', width: 30, height: 30 }}>
            <div style={{ position: 'absolute', top: -4, left: 4, display: 'flex', gap: 3 }}>
              <div style={{ width: 7, height: 7, borderRadius: 3, background: '#2F6BFF' }} />
              <div style={{ width: 7, height: 7, borderRadius: 3, background: '#F4A024' }} />
            </div>
            <div style={{
              width: 30, height: 30, borderRadius: 8, background: 'var(--navy)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <span style={{ color: 'white', fontWeight: 700, fontSize: 15, letterSpacing: '-0.5px' }}>Y</span>
            </div>
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 17, color: 'var(--ink)', lineHeight: 1.1 }}>Yuno</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '2px', color: 'var(--ink3)', textTransform: 'uppercase' }}>AGENT FACTORY</div>
          </div>
        </div>

        {/* Nav links */}
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center', gap: 2 }}>
          {NAV_LINKS.map(([s, label]) => (
            <button
              key={s}
              onClick={() => setScreen(s)}
              style={{
                padding: '6px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
                fontSize: 14, fontFamily: 'var(--font-ui)',
                fontWeight: screen === s ? 600 : 400,
                background: screen === s ? 'var(--surface2)' : 'transparent',
                color: screen === s ? 'var(--ink)' : 'var(--ink2)',
                transition: 'background 0.12s',
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Right controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <div style={{
            background: 'var(--surface2)', borderRadius: 10, padding: '6px 12px',
            fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink3)',
          }}>
            Search factory…
          </div>
          <button
            onClick={() => setScreen('builder')}
            style={{
              padding: '7px 14px', borderRadius: 10, border: '1px solid var(--line)',
              background: 'white', fontSize: 13, fontFamily: 'var(--font-ui)',
              cursor: 'pointer', color: 'var(--ink)', fontWeight: 500,
            }}
          >
            Build agent
          </button>
          <button
            onClick={() => setScreen('canvas')}
            style={{
              padding: '7px 14px', borderRadius: 10, border: 'none',
              background: 'var(--blue)', color: 'white', fontSize: 13,
              fontFamily: 'var(--font-ui)', cursor: 'pointer', fontWeight: 600,
              boxShadow: 'var(--shadow-cta)',
            }}
          >
            Build workflow
          </button>
        </div>
      </nav>

      {/* Screens */}
      {screen === 'dashboard' && (
        <Dashboard setScreen={setScreen} setSelectedRunId={setSelectedRunId} />
      )}
      {screen === 'builder' && <Builder setScreen={setScreen} />}
      {screen === 'canvas' && <Canvas setScreen={setScreen} />}
      {screen === 'run' && <RunView runId={selectedRunId} setScreen={setScreen} />}
      {screen === 'gallery' && <Gallery setScreen={setScreen} />}
    </div>
  )
}
