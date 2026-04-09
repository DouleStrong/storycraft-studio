from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_character_library_links"
down_revision = "0002_job_streaming_and_status"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def _column_map(table_name: str) -> dict[str, dict]:
    bind = op.get_bind()
    return {column["name"]: column for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()
    if "characters" not in tables:
        return

    character_columns = _column_map("characters")
    if "owner_id" not in character_columns:
        op.add_column(
            "characters",
            sa.Column("owner_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_characters_owner_id_users",
            "characters",
            "users",
            ["owner_id"],
            ["id"],
        )
        op.create_index("ix_characters_owner_id", "characters", ["owner_id"], unique=False)

    character_columns = _column_map("characters")
    if not character_columns["project_id"].get("nullable", True):
        with op.batch_alter_table("characters") as batch_op:
            batch_op.alter_column("project_id", existing_type=sa.Integer(), nullable=True)

    if "project_characters" not in tables:
        op.create_table(
            "project_characters",
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), primary_key=True, nullable=False),
            sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id"), primary_key=True, nullable=False),
        )

    characters = sa.table(
        "characters",
        sa.column("id", sa.Integer()),
        sa.column("project_id", sa.Integer()),
        sa.column("owner_id", sa.Integer()),
    )
    projects = sa.table(
        "projects",
        sa.column("id", sa.Integer()),
        sa.column("owner_id", sa.Integer()),
    )

    rows = bind.execute(
        sa.select(characters.c.id, projects.c.owner_id)
        .select_from(characters.join(projects, characters.c.project_id == projects.c.id))
        .where(characters.c.owner_id.is_(None))
    ).fetchall()
    for row in rows:
        bind.execute(
            characters.update().where(characters.c.id == row.id).values(owner_id=row.owner_id)
        )


def downgrade() -> None:
    pass
