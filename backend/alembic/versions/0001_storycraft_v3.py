from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

from app.database import Base
from app.models import *  # noqa: F401,F403

revision = "0001_storycraft_v3"
down_revision = None
branch_labels = None
depends_on = None


def _extract_target_chapter_count(value: str | None) -> int:
    if not value:
        return 6
    match = re.search(r"(\d+)", value)
    if not match:
        return 6
    return max(1, min(24, int(match.group(1))))


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)

    inspector = sa.inspect(bind)
    if "projects" in inspector.get_table_names():
        project_columns = {column["name"] for column in inspector.get_columns("projects")}
        if "target_chapter_count" not in project_columns:
            op.add_column(
                "projects",
                sa.Column("target_chapter_count", sa.Integer(), nullable=False, server_default="6"),
            )

        projects = sa.table(
            "projects",
            sa.column("id", sa.Integer()),
            sa.column("target_length", sa.String()),
            sa.column("target_chapter_count", sa.Integer()),
        )
        rows = bind.execute(sa.select(projects.c.id, projects.c.target_length, projects.c.target_chapter_count)).fetchall()
        for row in rows:
            current_value = row.target_chapter_count if row.target_chapter_count is not None else _extract_target_chapter_count(row.target_length)
            bind.execute(
                projects.update()
                .where(projects.c.id == row.id)
                .values(target_chapter_count=current_value)
            )


def downgrade() -> None:
    pass
