import { useCallback, useEffect, useMemo, useState } from 'react'
import type { RunSnapshot, RunStatus } from '../types'
import {
  approveTask,
  getRun,
  getRunEvents,
  listAgents,
  listWorkflows,
  rejectTask,
  startWorkflowRun,
  type WorkflowRow,
} from '../api/client'
import { useSSE, type LiveEvent } from '../hooks/useSSE'

const STATUS_COLOR: Record<RunStatus, string> = {
  pending: '#929BB0',
  running: '#2F6BFF',
  awaiting_approval: '#F4A024',
  completed: '#1E9E6A',
  failed: '#E5484D',
  cancelled: '#929BB0',
}

function eventLabel(ev: LiveEvent): string {
  const d = ev.data
  switch (ev.type) {
    case 'workflow_started':
      return 'Run started'
    case 'task_started':
      return `Task started (${String(d.task_id ?? '').slice(0, 8)}…)`
    case 'task_completed':
      return `Task completed — ${String(d.output_preview ?? '').slice(0, 60)}`
    case 'task_failed':
      return `Task failed — ${String(d.error ?? 'unknown')}`
    case 'feedback_sent':
      return `Feedback loop iteration ${String(d.iteration ?? '?')}`
    case 'feedback_loop_capped':
      return 'Feedback loop capped (forced complete path)'
    case 'approval_required':
      return `Approval required — ${String(d.description ?? 'human gate')}`
    case 'approval_resolved':
      return `Approval ${String(d.resolution ?? 'resolved')}`
    case 'workflow_completed':
      return d.forced_complete ? 'Run completed (forced)' : 'Run completed'
    case 'workflow_failed':
      return `Run failed — ${String(d.reason ?? 'unknown')}`
    case 'message_sent':
      return 'Message sent between agents'
    case 'tool_called':
      return `Tool called: ${String(d.tool ?? 'unknown')}`
    default:
      return ev.type
  }
}

export default function LiveRunView() {
  const [workflows, setWorkflows] = useState<WorkflowRow[]>([])
  const [workflowId, setWorkflowId] = useState('')
  const [runInput, setRunInput] = useState('Implement user authentication for the API.')
  const [runId, setRunId] = useState<string | null>(null)
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null)
  const [agentNames, setAgentNames] = useState<Record<string, string>>({})
  const [events, setEvents] = useState<LiveEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refreshRun = useCallback(async (id: string) => {
    const snap = await getRun(id)
    setSnapshot(snap)
  }, [])

  useEffect(() => {
    Promise.all([listWorkflows(), listAgents()])
      .then(([wfs, agents]) => {
        setWorkflows(wfs)
        const dev = wfs.find((w) => w.template_key === 'dev_pipeline')
        setWorkflowId(dev?.id ?? wfs[0]?.id ?? '')
        setAgentNames(Object.fromEntries(agents.map((a) => [a.id, a.name])))
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!runId) return
    getRunEvents(runId)
      .then((rows) =>
        setEvents(rows.map((r) => ({ type: r.event_type, data: r.data }))),
      )
      .catch(() => {})
    refreshRun(runId).catch((e: Error) => setError(e.message))
  }, [runId, refreshRun])

  const onLiveEvent = useCallback(
    (ev: LiveEvent) => {
      setEvents((prev) => [...prev, ev])
      if (runId) refreshRun(runId).catch(() => {})
    },
    [runId, refreshRun],
  )

  useSSE(runId, onLiveEvent)

  const startRun = async () => {
    if (!workflowId) return
    setBusy(true)
    setError(null)
    setEvents([])
    try {
      const { run_id } = await startWorkflowRun(workflowId, runInput)
      setRunId(run_id)
      await refreshRun(run_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start run')
    } finally {
      setBusy(false)
    }
  }

  const onApprove = async () => {
    const taskId = snapshot?.pending_approval?.task_id
    if (!runId || !taskId) return
    setBusy(true)
    try {
      await approveTask(runId, taskId)
      await refreshRun(runId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Approve failed')
    } finally {
      setBusy(false)
    }
  }

  const onReject = async () => {
    const taskId = snapshot?.pending_approval?.task_id
    if (!runId || !taskId) return
    setBusy(true)
    try {
      await rejectTask(runId, taskId)
      await refreshRun(runId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reject failed')
    } finally {
      setBusy(false)
    }
  }

  const terminal = snapshot?.status === 'completed' || snapshot?.status === 'failed'
  const showApproval =
    snapshot?.status === 'awaiting_approval' && snapshot.pending_approval

  const sortedEvents = useMemo(() => events, [events])

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '28px 24px 48px' }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: '0 0 6px' }}>Workflow run</h1>
        <p style={{ margin: 0, color: 'var(--ink2)', fontSize: 14 }}>
          Live view — SSE + run snapshot (BUILD_SPEC §17.2)
        </p>
      </header>

      {/* Start run */}
      <section
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--line)',
          borderRadius: 12,
          padding: 16,
          marginBottom: 20,
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <label style={{ flex: '1 1 200px' }}>
            <div style={{ fontSize: 12, color: 'var(--ink3)', marginBottom: 4 }}>Workflow</div>
            <select
              value={workflowId}
              onChange={(e) => setWorkflowId(e.target.value)}
              style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--line)' }}
            >
              {workflows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}{w.template_key ? ` (${w.template_key})` : ''}
                </option>
              ))}
            </select>
          </label>
          <label style={{ flex: '2 1 280px' }}>
            <div style={{ fontSize: 12, color: 'var(--ink3)', marginBottom: 4 }}>Initial input</div>
            <input
              value={runInput}
              onChange={(e) => setRunInput(e.target.value)}
              style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--line)' }}
            />
          </label>
          <button
            type="button"
            onClick={startRun}
            disabled={busy || !workflowId}
            style={{
              padding: '9px 18px',
              borderRadius: 10,
              border: 'none',
              background: 'var(--blue)',
              color: 'white',
              fontWeight: 600,
              cursor: busy ? 'wait' : 'pointer',
              opacity: busy ? 0.7 : 1,
            }}
          >
            {busy ? 'Starting…' : 'Run workflow'}
          </button>
        </div>
        {runId && (
          <div style={{ marginTop: 10, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink3)' }}>
            run_id: {runId}
          </div>
        )}
        {error && (
          <div style={{ marginTop: 10, color: '#E5484D', fontSize: 13 }}>{error}</div>
        )}
      </section>

      {snapshot && (
        <>
          {/* Status + approval */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              marginBottom: 16,
              flexWrap: 'wrap',
            }}
          >
            <span
              style={{
                padding: '4px 10px',
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 600,
                color: 'white',
                background: STATUS_COLOR[snapshot.status],
              }}
            >
              {snapshot.status.replace('_', ' ')}
            </span>
            {snapshot.forced_complete && (
              <span style={{ fontSize: 12, color: 'var(--ink2)' }}>forced_complete</span>
            )}
            {snapshot.workflow && (
              <span style={{ fontSize: 13, color: 'var(--ink2)' }}>{snapshot.workflow.name}</span>
            )}
          </div>

          {showApproval && (
            <div
              style={{
                background: '#FFF8EB',
                border: '1px solid #F4A024',
                borderRadius: 12,
                padding: 16,
                marginBottom: 20,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Awaiting approval</div>
              <div style={{ fontSize: 14, color: 'var(--ink2)', marginBottom: 12 }}>
                {snapshot.pending_approval?.description}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  onClick={onApprove}
                  disabled={busy}
                  style={{
                    padding: '8px 16px',
                    borderRadius: 8,
                    border: 'none',
                    background: '#1E9E6A',
                    color: 'white',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Approve
                </button>
                <button
                  type="button"
                  onClick={onReject}
                  disabled={busy}
                  style={{
                    padding: '8px 16px',
                    borderRadius: 8,
                    border: '1px solid #E5484D',
                    background: 'white',
                    color: '#E5484D',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Reject
                </button>
              </div>
            </div>
          )}

          {/* Tasks */}
          <section style={{ marginBottom: 20 }}>
            <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>Tasks</h2>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {snapshot.tasks.map((t) => (
                <li
                  key={t.id}
                  style={{
                    border: '1px solid var(--line)',
                    borderRadius: 10,
                    padding: '10px 12px',
                    background: 'var(--surface)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <strong>{agentNames[t.agent_id] ?? t.agent_id.slice(0, 8)}</strong>
                    <span style={{ fontSize: 12, color: STATUS_COLOR[t.status as RunStatus] ?? 'var(--ink2)' }}>
                      {t.status}
                    </span>
                  </div>
                  {t.feedback_iteration_count > 0 && (
                    <div style={{ fontSize: 12, color: '#F4A024', marginTop: 4 }}>
                      feedback iteration {t.feedback_iteration_count}
                    </div>
                  )}
                  {t.output && (
                    <pre
                      style={{
                        margin: '8px 0 0',
                        fontSize: 11,
                        fontFamily: 'var(--font-mono)',
                        whiteSpace: 'pre-wrap',
                        color: 'var(--ink2)',
                        maxHeight: 80,
                        overflow: 'auto',
                      }}
                    >
                      {t.output.slice(0, 300)}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          </section>

          {/* Messages */}
          <section style={{ marginBottom: 20 }}>
            <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>Message trail</h2>
            {snapshot.messages.length === 0 ? (
              <p style={{ color: 'var(--ink3)', fontSize: 13 }}>No messages yet.</p>
            ) : (
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {snapshot.messages.map((m) => (
                  <li
                    key={m.id}
                    style={{
                      fontSize: 13,
                      padding: '8px 10px',
                      borderLeft: '3px solid var(--line)',
                      background: 'var(--surface2)',
                    }}
                  >
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink3)' }}>
                      {m.msg_type}
                    </span>
                    <div style={{ marginTop: 4, color: 'var(--ink2)' }}>
                      {(m.payload?.content ?? '').slice(0, 120)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Events */}
          <section>
            <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>Events {terminal ? '' : '(live)'}</h2>
            <ul
              style={{
                listStyle: 'none',
                padding: 0,
                margin: 0,
                maxHeight: 280,
                overflow: 'auto',
                border: '1px solid var(--line)',
                borderRadius: 10,
                background: 'var(--surface)',
              }}
            >
              {sortedEvents.map((ev, i) => (
                <li
                  key={`${ev.type}-${i}`}
                  style={{
                    padding: '8px 12px',
                    borderBottom: i < sortedEvents.length - 1 ? '1px solid var(--line)' : undefined,
                    fontSize: 13,
                  }}
                >
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--blue)' }}>
                    {ev.type}
                  </span>
                  <div style={{ color: 'var(--ink2)', marginTop: 2 }}>{eventLabel(ev)}</div>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}

      {!snapshot && !runId && (
        <p style={{ color: 'var(--ink3)', fontSize: 14 }}>
          Pick a workflow and click Run workflow to start a live run.
        </p>
      )}
    </div>
  )
}
