import { useEffect, useRef } from 'react'

const EVENT_TYPES = [
  'workflow_started',
  'workflow_completed',
  'workflow_failed',
  'task_started',
  'task_completed',
  'task_failed',
  'tool_called',
  'message_sent',
  'feedback_sent',
  'feedback_loop_capped',
  'approval_required',
  'approval_resolved',
  'guardrail_triggered',
  'cost_updated',
  'schedule_fired',
] as const

export interface LiveEvent {
  type: string
  data: Record<string, unknown>
}

export function useSSE(
  runId: string | null,
  onEvent: (event: LiveEvent) => void,
): void {
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    if (!runId) return

    let es: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let closed = false

    const connect = () => {
      es = new EventSource(`/events?run_id=${encodeURIComponent(runId)}`)

      const dispatch = (type: string, raw: MessageEvent) => {
        try {
          const data = JSON.parse(raw.data) as Record<string, unknown>
          handlerRef.current({ type, data })
        } catch {
          handlerRef.current({ type, data: { raw: raw.data } })
        }
      }

      for (const t of EVENT_TYPES) {
        es.addEventListener(t, (e) => dispatch(t, e as MessageEvent))
      }

      es.onerror = () => {
        es?.close()
        if (!closed) {
          reconnectTimer = setTimeout(connect, 2000)
        }
      }
    }

    connect()

    return () => {
      closed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      es?.close()
    }
  }, [runId])
}
