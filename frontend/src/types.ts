// Frozen against GET /runs/{id} response shape in backend/app/services/workflow_service.py

export type RunStatus = 'pending' | 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'cancelled'
export type TaskStatus = 'pending' | 'running' | 'awaiting_feedback' | 'completed' | 'failed' | 'cancelled'
export type MsgType = 'task_output' | 'feedback' | 'channel_inbound' | 'channel_outbound'

export interface WorkflowMeta {
  id: string
  name: string
  description: string
  template_key: string | null
}

export interface AgentTask {
  id: string
  run_id: string
  node_id: string
  agent_id: string
  source: 'workflow' | 'conversational' | 'scheduled'
  status: TaskStatus
  input: string
  output: string | null
  feedback_iteration_count: number
  tokens_used: number
  cost_usd: number
  started_at: string | null
  completed_at: string | null
}

export interface AgentMessage {
  id: string
  run_id: string
  from_task_id: string | null
  to_task_id: string | null
  msg_type: MsgType
  payload: { content: string; chat_id: string | null; agent_id: string | null }
  created_at: string
}

export interface ApprovalRequest {
  id: string
  run_id: string
  task_id: string
  description: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  resolved_at: string | null
}

export interface RunSnapshot {
  run_id: string
  workflow_id: string
  status: RunStatus
  forced_complete: boolean
  started_at: string | null
  completed_at: string | null
  total_tokens: number | null
  total_cost: number | null
  workflow: WorkflowMeta | null
  tasks: AgentTask[]
  messages: AgentMessage[]
  pending_approval: ApprovalRequest | null
}

// UI-only types — not from backend

export type Screen = 'dashboard' | 'builder' | 'canvas' | 'run' | 'gallery'

export interface AgentConfig {
  id: string
  name: string
  role: string
  model: string
  accent: string  // MOCK: derived from agent identity, not stored in backend
  monogram: string  // MOCK: 2-letter abbreviation
}

export interface RunSummary {
  id: string
  name: string
  status: RunStatus
  progress: number  // MOCK: not yet in backend RunSnapshot; derived from task states
  cost: string  // MOCK: formatted string
  started: string  // MOCK: human-readable relative time
}

export interface KitCard {
  id: string
  code: string
  name: string
  tag: string
  color: string  // MOCK: kit header accent color
  description: string
  stations: string[]  // MOCK: monogram list
  costEstimate: string
}
