import type { RunSnapshot } from '../types'

export interface WorkflowRow {
  id: string
  name: string
  description: string
  template_key: string | null
}

export interface AgentRow {
  id: string
  name: string
  role: string
}

export interface ExecutionEventRow {
  id: string
  run_id: string | null
  agent_id: string | null
  task_id: string | null
  event_type: string
  data: Record<string, unknown>
  created_at: string
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body.detail?.message ?? body.detail ?? res.statusText
  } catch {
    return res.statusText
  }
}

export async function listWorkflows(): Promise<WorkflowRow[]> {
  const res = await fetch('/workflows')
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function listAgents(): Promise<AgentRow[]> {
  const res = await fetch('/agents')
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function startWorkflowRun(workflowId: string, input = ''): Promise<{ run_id: string }> {
  const res = await fetch(`/workflows/${workflowId}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function getRun(runId: string): Promise<RunSnapshot> {
  const res = await fetch(`/runs/${runId}`)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function getRunEvents(runId: string): Promise<ExecutionEventRow[]> {
  const res = await fetch(`/runs/${runId}/events`)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function approveTask(runId: string, taskId: string): Promise<void> {
  const res = await fetch(`/runs/${runId}/tasks/${taskId}/approve`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseError(res))
}

export async function rejectTask(runId: string, taskId: string): Promise<void> {
  const res = await fetch(`/runs/${runId}/tasks/${taskId}/reject`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseError(res))
}
