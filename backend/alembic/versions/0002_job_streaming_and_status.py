from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_job_streaming_and_status"
down_revision = "0001_storycraft_v3"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    job_columns = _column_names("generation_jobs")
    if "status_message" not in job_columns:
        op.add_column(
            "generation_jobs",
            sa.Column("status_message", sa.Text(), nullable=False, server_default=""),
        )

    agent_run_columns = _column_names("agent_runs")
    if "stream_text" not in agent_run_columns:
        op.add_column(
            "agent_runs",
            sa.Column("stream_text", sa.Text(), nullable=False, server_default=""),
        )
    if "public_notes" not in agent_run_columns:
        op.add_column(
            "agent_runs",
            sa.Column("public_notes", sa.JSON(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    pass
