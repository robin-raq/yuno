"""SQLAlchemy Core table definitions matching BUILD_SPEC §5.2 exactly."""
from sqlalchemy import (
    MetaData, Table, Column, Text, Integer, Float, ForeignKey, Index, CheckConstraint
)

metadata = MetaData()

agents = Table(
    "agents", metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("role", Text, nullable=False),
    Column("system_prompt", Text, nullable=False, server_default=""),
    Column("model", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="active"),
    Column("created_at", Text, nullable=False, server_default="(datetime('now'))"),
    CheckConstraint("status IN ('active','inactive','error')", name="ck_agents_status"),
)

agent_config = Table(
    "agent_config", metadata,
    Column("id", Text, primary_key=True),
    Column("agent_id", Text, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("extensions", Text, nullable=False, server_default='["developer"]'),
    Column("requires_approval", Integer, nullable=False, server_default="0"),
    Column("max_tokens_per_run", Integer, nullable=False, server_default="50000"),
    Column("max_runs_per_minute", Integer, nullable=False, server_default="6"),
    Column("blocked_extensions", Text, nullable=False, server_default="[]"),
    Column("max_feedback_iterations", Integer, nullable=False, server_default="2"),
    Column("max_turns", Integer, nullable=False, server_default="10"),
    Column("timeout_seconds", Integer, nullable=False, server_default="180"),
)

memory_entries = Table(
    "memory_entries", metadata,
    Column("id", Text, primary_key=True),
    Column("agent_id", Text, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
    Column("key", Text, nullable=False),
    Column("value", Text, nullable=False),
    Column("created_at", Text, nullable=False, server_default="(datetime('now'))"),
)

skills = Table(
    "skills", metadata,
    Column("id", Text, primary_key=True),
    Column("agent_id", Text, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("steps", Text, nullable=False, server_default="[]"),
)

schedules = Table(
    "schedules", metadata,
    Column("id", Text, primary_key=True),
    Column("agent_id", Text, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
    Column("trigger_type", Text, nullable=False, server_default="cron"),
    Column("expression", Text, nullable=False),
    Column("trigger_workflow_id", Text, ForeignKey("workflows.id"), nullable=True),
    Column("task_prompt", Text, nullable=False, server_default=""),
    Column("enabled", Integer, nullable=False, server_default="1"),
    CheckConstraint("trigger_type IN ('cron','interval')", name="ck_schedules_type"),
)

channel_connections = Table(
    "channel_connections", metadata,
    Column("id", Text, primary_key=True),
    Column("agent_id", Text, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
    Column("channel_type", Text, nullable=False, server_default="telegram"),
    Column("channel_id", Text, nullable=False),
    Column("trigger_workflow_id", Text, ForeignKey("workflows.id"), nullable=True),
    Column("active", Integer, nullable=False, server_default="1"),
)

workflows = Table(
    "workflows", metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("template_key", Text, nullable=True),
)

workflow_nodes = Table(
    "workflow_nodes", metadata,
    Column("id", Text, primary_key=True),
    Column("workflow_id", Text, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
    Column("agent_id", Text, ForeignKey("agents.id"), nullable=False),
    Column("node_type", Text, nullable=False, server_default="middle"),
    Column("task_prompt", Text, nullable=False, server_default=""),
    Column("position_x", Integer, nullable=False, server_default="0"),
    Column("position_y", Integer, nullable=False, server_default="0"),
    CheckConstraint("node_type IN ('start','middle','end')", name="ck_nodes_type"),
)

workflow_edges = Table(
    "workflow_edges", metadata,
    Column("id", Text, primary_key=True),
    Column("from_node_id", Text, ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False),
    Column("to_node_id", Text, ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False),
    Column("condition", Text, nullable=False, server_default="always"),
    Column("max_iterations", Integer, nullable=True),
)

workflow_runs = Table(
    "workflow_runs", metadata,
    Column("id", Text, primary_key=True),
    Column("workflow_id", Text, ForeignKey("workflows.id"), nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("forced_complete", Integer, nullable=False, server_default="0"),
    Column("started_at", Text, nullable=True),
    Column("completed_at", Text, nullable=True),
    Column("total_tokens", Integer, nullable=False, server_default="0"),
    Column("total_cost", Float, nullable=False, server_default="0.0"),
    CheckConstraint(
        "status IN ('pending','running','awaiting_approval','completed','failed','cancelled')",
        name="ck_runs_status",
    ),
)

agent_tasks = Table(
    "agent_tasks", metadata,
    Column("id", Text, primary_key=True),
    # run_id and node_id are NULLABLE — standalone (conversational/scheduled) tasks have neither
    Column("run_id", Text, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True),
    Column("node_id", Text, ForeignKey("workflow_nodes.id"), nullable=True),
    Column("agent_id", Text, ForeignKey("agents.id"), nullable=False),
    Column("source", Text, nullable=False, server_default="workflow"),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("input", Text, nullable=False, server_default=""),
    Column("output", Text, nullable=True),
    Column("feedback_iteration_count", Integer, nullable=False, server_default="0"),
    Column("tokens_used", Integer, nullable=False, server_default="0"),
    Column("cost_usd", Float, nullable=False, server_default="0.0"),
    Column("started_at", Text, nullable=True),
    Column("completed_at", Text, nullable=True),
    CheckConstraint("source IN ('workflow','conversational','scheduled')", name="ck_tasks_source"),
    CheckConstraint(
        "status IN ('pending','running','awaiting_feedback','completed','failed','cancelled')",
        name="ck_tasks_status",
    ),
)

agent_messages = Table(
    "agent_messages", metadata,
    Column("id", Text, primary_key=True),
    Column("run_id", Text, ForeignKey("workflow_runs.id"), nullable=True),
    Column("from_task_id", Text, ForeignKey("agent_tasks.id"), nullable=True),
    Column("to_task_id", Text, ForeignKey("agent_tasks.id"), nullable=True),
    Column("msg_type", Text, nullable=False),
    Column("payload", Text, nullable=False, server_default="{}"),
    Column("created_at", Text, nullable=False, server_default="(datetime('now'))"),
    CheckConstraint(
        "msg_type IN ('task_output','feedback','channel_inbound','channel_outbound')",
        name="ck_messages_type",
    ),
)

approval_requests = Table(
    "approval_requests", metadata,
    Column("id", Text, primary_key=True),
    Column("run_id", Text, ForeignKey("workflow_runs.id"), nullable=False),
    Column("task_id", Text, ForeignKey("agent_tasks.id"), nullable=False),
    Column("description", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("created_at", Text, nullable=False, server_default="(datetime('now'))"),
    Column("resolved_at", Text, nullable=True),
    CheckConstraint("status IN ('pending','approved','rejected')", name="ck_approvals_status"),
)

execution_events = Table(
    "execution_events", metadata,
    Column("id", Text, primary_key=True),
    Column("run_id", Text, ForeignKey("workflow_runs.id"), nullable=True),
    Column("agent_id", Text, ForeignKey("agents.id"), nullable=True),
    Column("task_id", Text, ForeignKey("agent_tasks.id"), nullable=True),
    Column("event_type", Text, nullable=False),
    Column("data", Text, nullable=False, server_default="{}"),
    Column("created_at", Text, nullable=False, server_default="(datetime('now'))"),
)

# Indexes matching BUILD_SPEC §5.2
Index("idx_agent_tasks_run_id", agent_tasks.c.run_id)
Index("idx_agent_messages_run_id", agent_messages.c.run_id)
Index("idx_execution_events_run_id", execution_events.c.run_id)
