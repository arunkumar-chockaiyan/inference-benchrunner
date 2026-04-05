"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-04-03 00:00:00.000000

Creates all Phase 1 tables:
  prompts, prompt_suites, suite_prompts, projects,
  run_configs, runs, request_records,
  saved_comparisons, engine_models
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # projects — no FK deps
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # prompts — no FK deps
    # ------------------------------------------------------------------
    op.create_table(
        "prompts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # prompt_suites — no FK deps
    # ------------------------------------------------------------------
    op.create_table(
        "prompt_suites",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # suite_prompts — composite PK, FKs to prompts + prompt_suites
    # ------------------------------------------------------------------
    op.create_table(
        "suite_prompts",
        sa.Column(
            "suite_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("prompt_suites.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "prompt_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("prompts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index("ix_suite_prompts_suite_id", "suite_prompts", ["suite_id"])

    # ------------------------------------------------------------------
    # run_configs — FK to prompt_suites + projects
    # ------------------------------------------------------------------
    op.create_table(
        "run_configs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("engine", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column(
            "suite_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("prompt_suites.id"),
            nullable=False,
        ),
        sa.Column("host", sa.String(), nullable=False, server_default="localhost"),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("agent_port", sa.Integer(), nullable=False, server_default="8787"),
        sa.Column("spawn_mode", sa.String(), nullable=False, server_default="attach"),
        sa.Column("health_timeout_s", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="512"),
        sa.Column("top_p", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("request_timeout_s", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("watchdog_interval_s", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("warmup_rounds", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("auto_retry", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("variable_overrides", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_run_configs_engine", "run_configs", ["engine"])

    # ------------------------------------------------------------------
    # runs — FK to run_configs
    # ------------------------------------------------------------------
    op.create_table(
        "runs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "config_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("run_configs.id"),
            nullable=False,
        ),
        sa.Column("config_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warmup_duration_ms", sa.Float(), nullable=True),
        sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("server_owned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("server_pid", sa.Integer(), nullable=True),
        sa.Column("sidecar_pid", sa.Integer(), nullable=True),
        sa.Column("remote_agent_run_id", sa.String(), nullable=True),
        sa.Column("cleanup_warning", sa.Text(), nullable=True),
    )
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_config_id", "runs", ["config_id"])

    # ------------------------------------------------------------------
    # request_records — FK to runs + prompts
    # ------------------------------------------------------------------
    op.create_table(
        "request_records",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "prompt_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("prompts.id"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("ttft_ms", sa.Float(), nullable=True),
        sa.Column("total_latency_ms", sa.Float(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("generated_tokens", sa.Integer(), nullable=False),
        sa.Column("tokens_per_second", sa.Float(), nullable=True),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_request_records_run_id", "request_records", ["run_id"])
    op.create_index("ix_request_records_started_at", "request_records", ["started_at"])

    # ------------------------------------------------------------------
    # saved_comparisons — no FK deps
    # ------------------------------------------------------------------
    op.create_table(
        "saved_comparisons",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("run_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("share_token", sa.String(), nullable=False, unique=True),
    )

    # ------------------------------------------------------------------
    # engine_models — unique constraint on (engine, host, model_id)
    # ------------------------------------------------------------------
    op.create_table(
        "engine_models",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("engine", sa.String(), nullable=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False, server_default=""),
        sa.Column("source", sa.String(), nullable=False, server_default="synced"),
        sa.Column("last_synced", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("engine", "host", "model_id", name="uq_engine_host_model"),
    )
    op.create_index("ix_engine_models_engine", "engine_models", ["engine"])


def downgrade() -> None:
    op.drop_table("engine_models")
    op.drop_table("saved_comparisons")
    op.drop_table("request_records")
    op.drop_table("runs")
    op.drop_table("run_configs")
    op.drop_table("suite_prompts")
    op.drop_table("prompt_suites")
    op.drop_table("prompts")
    op.drop_table("projects")
