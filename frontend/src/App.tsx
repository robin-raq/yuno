import { useEffect, useRef, useState } from 'react'

interface Agent {
  id: string
  name: string
  role: string
  model: string
}

interface ExecutionEvent {
  id: string
  event_type: string
  data: string
  created_at: string
}

interface TaskResult {
  id: string
  status: string
  output: string | null
  tokens_used: number
  cost_usd: number
  events: ExecutionEvent[]
}

export default function App() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<TaskResult | null>(null)
  const [error, setError] = useState('')
  // Finding #16 fix: ref-based guard prevents double-submit before React re-renders the disabled state.
  const submitting = useRef(false)

  useEffect(() => {
    fetch('/agents')
      .then(r => r.json())
      .then(setAgents)
      .catch(() => setError('Could not reach API — is the backend running?'))
  }, [])

  async function handleSubmit() {
    if (!selectedId || !input.trim() || submitting.current) return
    submitting.current = true
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const res = await fetch(`/agents/${selectedId}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input }),
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`${res.status} — ${text}`)
      }
      const data: TaskResult = await res.json()
      setResult(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      submitting.current = false
      setLoading(false)
    }
  }

  const selectedAgent = agents.find(a => a.id === selectedId)

  return (
    <div style={{ fontFamily: 'monospace', maxWidth: 860, margin: '40px auto', padding: '0 20px' }}>
      <h1 style={{ borderBottom: '2px solid #333', paddingBottom: 8 }}>
        Yuno — Agent Runner
      </h1>

      <div style={{ marginBottom: 16 }}>
        <label><strong>Agent</strong></label><br />
        <select
          value={selectedId}
          onChange={e => setSelectedId(e.target.value)}
          style={{ width: '100%', padding: 6, marginTop: 4, fontSize: 14 }}
        >
          <option value="">— select an agent —</option>
          {agents.map(a => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.role})
            </option>
          ))}
        </select>
        {selectedAgent && (
          <div style={{ fontSize: 12, color: '#555', marginTop: 4 }}>
            model: {selectedAgent.model}
          </div>
        )}
      </div>

      <div style={{ marginBottom: 16 }}>
        <label><strong>Task</strong></label><br />
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          rows={5}
          placeholder="Describe what the agent should do..."
          style={{ width: '100%', padding: 6, marginTop: 4, fontSize: 14, boxSizing: 'border-box' }}
        />
      </div>

      <button
        onClick={handleSubmit}
        disabled={loading || !selectedId || !input.trim()}
        style={{ padding: '8px 20px', fontSize: 14, cursor: loading ? 'wait' : 'pointer' }}
      >
        {loading ? 'Running…' : 'Submit Task'}
      </button>

      {error && (
        <div style={{ marginTop: 20, color: 'red', whiteSpace: 'pre-wrap' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 24 }}>
          <h2>Result</h2>
          <div style={{ marginBottom: 8, fontSize: 13, color: '#555' }}>
            status: <strong>{result.status}</strong> &nbsp;|&nbsp;
            tokens: {result.tokens_used} &nbsp;|&nbsp;
            cost: ~${result.cost_usd.toFixed(5)}
          </div>
          <pre style={{
            background: '#f5f5f5',
            border: '1px solid #ccc',
            padding: 12,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            maxHeight: 400,
            overflowY: 'auto',
          }}>
            {result.output ?? '(no output)'}
          </pre>

          <h3>Execution Events ({result.events.length})</h3>
          {result.events.length === 0 ? (
            <p style={{ color: '#888' }}>No events recorded.</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#eee' }}>
                  <th style={th}>Type</th>
                  <th style={th}>Data</th>
                  <th style={th}>Time</th>
                </tr>
              </thead>
              <tbody>
                {result.events.map(ev => (
                  <tr key={ev.id} style={{ borderBottom: '1px solid #ddd' }}>
                    <td style={td}>{ev.event_type}</td>
                    <td style={{ ...td, maxWidth: 500, wordBreak: 'break-all' }}>
                      <details>
                        <summary style={{ cursor: 'pointer' }}>show</summary>
                        <pre style={{ margin: '4px 0', fontSize: 11 }}>
                          {JSON.stringify(JSON.parse(ev.data || '{}'), null, 2)}
                        </pre>
                      </details>
                    </td>
                    <td style={td}>{ev.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

const th: React.CSSProperties = {
  padding: '6px 8px', textAlign: 'left', borderBottom: '2px solid #999'
}
const td: React.CSSProperties = {
  padding: '4px 8px', verticalAlign: 'top'
}
