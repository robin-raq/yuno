import type { Screen } from '../types'
import { MOCK_KITS } from '../mockData'

interface Props {
  setScreen: (s: Screen) => void
}

export default function Gallery({ setScreen }: Props) {
  return (
    <div style={{ maxWidth: 1240, margin: '0 auto', padding: '30px 28px 64px' }}>

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--blue)', letterSpacing: '1.5px', textTransform: 'uppercase', marginBottom: 8 }}>▸ STARTER KITS</div>
        <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.8px', color: 'var(--ink)', margin: '0 0 8px' }}>Snap-together blueprints.</h1>
        <p style={{ color: 'var(--ink2)', margin: 0, fontSize: 15 }}>Pick a kit, load it onto the canvas, and start running in seconds.</p>
      </div>

      {/* Kit grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))', gap: 18 }}>
        {MOCK_KITS.map(kit => (
          <div key={kit.id} style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 16, overflow: 'hidden', boxShadow: 'var(--shadow-card)' }}>

            {/* Lid */}
            <div style={{ background: kit.color, padding: '20px 22px 18px', position: 'relative' }}>
              {/* Stud tabs */}
              <div style={{ position: 'absolute', top: -4, left: 22, display: 'flex', gap: 6 }}>
                <div style={{ width: 10, height: 10, borderRadius: 4, background: 'rgba(255,255,255,0.3)' }} />
                <div style={{ width: 10, height: 10, borderRadius: 4, background: 'rgba(255,255,255,0.3)' }} />
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'rgba(255,255,255,0.6)', letterSpacing: '1.5px', marginBottom: 6 }}>{kit.code}</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: 'white', marginBottom: 8 }}>{kit.name}</div>
              <div style={{ display: 'inline-block', padding: '3px 9px', borderRadius: 20, background: 'rgba(255,255,255,0.18)', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'rgba(255,255,255,0.85)', letterSpacing: '0.5px' }}>
                {kit.tag}
              </div>
            </div>

            {/* Blueprint preview strip */}
            <div style={{
              background: '#F4F6FB',
              backgroundImage: 'linear-gradient(#E7EBF4 1px,transparent 1px), linear-gradient(90deg,#E7EBF4 1px,transparent 1px)',
              backgroundSize: '24px 24px, 24px 24px',
              padding: '16px 22px',
              display: 'flex', alignItems: 'center', gap: 8,
              borderBottom: '1px solid var(--line)',
            }}>
              {kit.stations.length === 0 ? (
                <div style={{ flex: 1, textAlign: 'center', border: '1.5px dashed #CBD3E4', borderRadius: 10, padding: '12px 0', color: 'var(--ink3)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                  ＋ empty floor
                </div>
              ) : (
                <>
                  <div style={{ width: 10, height: 10, borderRadius: 5, background: '#9098AC', flexShrink: 0 }} />
                  {kit.stations.map((m, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ width: 36, height: 36, position: 'relative', flexShrink: 0 }}>
                        {/* Studs */}
                        <div style={{ position: 'absolute', top: -3, left: 8, display: 'flex', gap: 3 }}>
                          <div style={{ width: 5, height: 5, borderRadius: 2, background: 'white', opacity: 0.8 }} />
                          <div style={{ width: 5, height: 5, borderRadius: 2, background: 'white', opacity: 0.8 }} />
                        </div>
                        <div style={{ width: 36, height: 36, borderRadius: 8, background: 'white', border: `1.5px solid ${kit.color}55`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 10, color: kit.color }}>{m}</span>
                        </div>
                      </div>
                      {i < kit.stations.length - 1 && (
                        <div style={{ width: 20, height: 4, borderRadius: 2, background: '#CBD3E4', flexShrink: 0 }} />
                      )}
                    </div>
                  ))}
                  <div style={{ width: 8, height: 8, borderRadius: 4, border: '2px solid #9098AC', flexShrink: 0 }} />
                </>
              )}
            </div>

            {/* Body */}
            <div style={{ padding: '16px 22px 20px' }}>
              <p style={{ color: 'var(--ink2)', fontSize: 13, lineHeight: 1.5, margin: '0 0 12px' }}>{kit.description}</p>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink3)' }}>
                  {kit.stations.length > 0 ? `${kit.stations.length} stations` : 'custom'} · {kit.costEstimate}
                </div>
              </div>
              <button
                onClick={() => setScreen('canvas')}
                style={{
                  width: '100%', padding: '10px 0', borderRadius: 10, border: 'none',
                  background: 'var(--navy)', color: 'white', fontSize: 14, fontWeight: 600,
                  fontFamily: 'var(--font-ui)', cursor: 'pointer', boxShadow: 'var(--shadow-dark)',
                }}
              >
                Use kit →
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
