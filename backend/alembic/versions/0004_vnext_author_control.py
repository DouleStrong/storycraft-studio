from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_vnext_author_control"
down_revision = "0003_character_library_links"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()

    if "story_bibles" in tables:
        story_bible_columns = _column_names("story_bibles")
        if "addressing_rules" not in story_bible_columns:
            op.add_column("story_bibles", sa.Column("addressing_rules", sa.Text(), nullable=False, server_default=""))
        if "timeline_rules" not in story_bible_columns:
            op.add_column("story_bibles", sa.Column("timeline_rules", sa.Text(), nullable=False, server_default=""))

    if "story_bible_revisions" not in tables:
        op.create_table(
            "story_bible_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("story_bible_id", sa.Integer(), sa.ForeignKey("story_bibles.id"), nullable=False),
            sa.Column("revision_index", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("world_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("style_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("writing_rules", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("addressing_rules", sa.Text(), nullable=False, server_default=""),
            sa.Column("timeline_rules", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=40), nullable=False, server_default="system"),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("source_job_id", sa.Integer(), sa.ForeignKey("generation_jobs.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_story_bible_revisions_project_id", "story_bible_revisions", ["project_id"], unique=False)
        op.create_index("ix_story_bible_revisions_story_bible_id", "story_bible_revisions", ["story_bible_id"], unique=False)
        op.create_index("ix_story_bible_revisions_created_by_user_id", "story_bible_revisions", ["created_by_user_id"], unique=False)
        op.create_index("ix_story_bible_revisions_source_job_id", "story_bible_revisions", ["source_job_id"], unique=False)

    if "content_revisions" not in tables:
        op.create_table(
            "content_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("chapters.id"), nullable=False),
            sa.Column("story_bible_revision_id", sa.Integer(), sa.ForeignKey("story_bible_revisions.id"), nullable=True),
            sa.Column("source_job_id", sa.Integer(), sa.ForeignKey("generation_jobs.id"), nullable=True),
            sa.Column("revision_kind", sa.String(length=40), nullable=False, server_default="draft"),
            sa.Column("created_by", sa.String(length=40), nullable=False, server_default="agent"),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_content_revisions_project_id", "content_revisions", ["project_id"], unique=False)
        op.create_index("ix_content_revisions_chapter_id", "content_revisions", ["chapter_id"], unique=False)
        op.create_index("ix_content_revisions_story_bible_revision_id", "content_revisions", ["story_bible_revision_id"], unique=False)
        op.create_index("ix_content_revisions_source_job_id", "content_revisions", ["source_job_id"], unique=False)
        op.create_index("ix_content_revisions_created_by_user_id", "content_revisions", ["created_by_user_id"], unique=False)

    if "project_snapshots" not in tables:
        op.create_table(
            "project_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_by", sa.String(length=40), nullable=False, server_default="user"),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_project_snapshots_project_id", "project_snapshots", ["project_id"], unique=False)
        op.create_index("ix_project_snapshots_created_by_user_id", "project_snapshots", ["created_by_user_id"], unique=False)

    if "chapters" in tables:
        chapter_columns = _column_names("chapters")
        if "source_story_bible_revision_id" not in chapter_columns:
            op.add_column("chapters", sa.Column("source_story_bible_revision_id", sa.Integer(), nullable=True))

    for table_name in ("narrative_blocks", "scenes", "dialogue_blocks"):
        if table_name not in tables:
            continue
        columns = _column_names(table_name)
        if "is_locked" not in columns:
            op.add_column(table_name, sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "is_user_edited" not in columns:
            op.add_column(table_name, sa.Column("is_user_edited", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "source_revision_id" not in columns:
            op.add_column(table_name, sa.Column("source_revision_id", sa.Integer(), nullable=True))
        if "last_editor_type" not in columns:
            op.add_column(table_name, sa.Column("last_editor_type", sa.String(length=40), nullable=False, server_default="agent"))

    story_bibles = sa.table(
        "story_bibles",
        sa.column("id", sa.Integer()),
        sa.column("project_id", sa.Integer()),
        sa.column("world_notes", sa.Text()),
        sa.column("style_notes", sa.Text()),
        sa.column("writing_rules", sa.JSON()),
        sa.column("addressing_rules", sa.Text()),
        sa.column("timeline_rules", sa.Text()),
    )
    story_bible_revisions = sa.table(
        "story_bible_revisions",
        sa.column("id", sa.Integer()),
        sa.column("project_id", sa.Integer()),
        sa.column("story_bible_id", sa.Integer()),
        sa.column("revision_index", sa.Integer()),
        sa.column("world_notes", sa.Text()),
        sa.column("style_notes", sa.Text()),
        sa.column("writing_rules", sa.JSON()),
        sa.column("addressing_rules", sa.Text()),
        sa.column("timeline_rules", sa.Text()),
        sa.column("created_by", sa.String()),
        sa.column("created_at", sa.DateTime()),
    )
    chapters = sa.table(
        "chapters",
        sa.column("id", sa.Integer()),
        sa.column("project_id", sa.Integer()),
        sa.column("source_story_bible_revision_id", sa.Integer()),
    )

    if "story_bibles" in tables and "story_bible_revisions" in _table_names():
        existing_revision_ids = {
            row.story_bible_id
            for row in bind.execute(sa.select(story_bible_revisions.c.story_bible_id)).fetchall()
        }
        rows = bind.execute(
            sa.select(
                story_bibles.c.id,
                story_bibles.c.project_id,
                story_bibles.c.world_notes,
                story_bibles.c.style_notes,
                story_bibles.c.writing_rules,
                story_bibles.c.addressing_rules,
                story_bibles.c.timeline_rules,
            )
        ).fetchall()
        created_revision_by_project: dict[int, int] = {}
        for row in rows:
            if row.id in existing_revision_ids:
                latest_revision_id = bind.execute(
                    sa.select(story_bible_revisions.c.id)
                    .where(story_bible_revisions.c.story_bible_id == row.id)
                    .order_by(story_bible_revisions.c.id.desc())
                    .limit(1)
                ).scalar()
                if latest_revision_id:
                    created_revision_by_project[row.project_id] = latest_revision_id
                continue
            created_revision_id = bind.execute(
                story_bible_revisions.insert()
                .returning(story_bible_revisions.c.id)
                .values(
                    project_id=row.project_id,
                    story_bible_id=row.id,
                    revision_index=1,
                    world_notes=row.world_notes or "",
                    style_notes=row.style_notes or "",
                    writing_rules=row.writing_rules or [],
                    addressing_rules=row.addressing_rules or "",
                    timeline_rules=row.timeline_rules or "",
                    created_by="migration",
                    created_at=sa.func.now(),
                )
            ).scalar()
            if created_revision_id:
                created_revision_by_project[row.project_id] = int(created_revision_id)

        chapter_rows = bind.execute(sa.select(chapters.c.id, chapters.c.project_id, chapters.c.source_story_bible_revision_id)).fetchall()
        for chapter in chapter_rows:
            if chapter.source_story_bible_revision_id:
                continue
            revision_id = created_revision_by_project.get(chapter.project_id)
            if revision_id:
                bind.execute(
                    chapters.update()
                    .where(chapters.c.id == chapter.id)
                    .values(source_story_bible_revision_id=revision_id)
                )


def downgrade() -> None:
    pass
