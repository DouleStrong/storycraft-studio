from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from pypdf import PdfReader
from reportlab.lib import colors

from app.exporting import _build_pdf_styles
from app.services import export_project_bundle, serialize_export
from app.storage import LocalAssetStore


def make_dialogue(order_index: int, speaker: str, content: str, parenthetical: str = ""):
    return SimpleNamespace(
        order_index=order_index,
        speaker=speaker,
        content=content,
        parenthetical=parenthetical,
    )


def make_scene(order_index: int, image_path: str):
    return SimpleNamespace(
        order_index=order_index,
        title="控制室试探",
        scene_type="INT",
        location="广播站控制室",
        time_of_day="NIGHT",
        objective="让角色在第一次交换线索时暴露彼此的防备。",
        emotional_tone="冷静、克制、暗流翻涌",
        dialogue_blocks=[
            make_dialogue(1, "林听", "如果今晚不把话说清楚，明天就没有机会了。"),
            make_dialogue(2, "顾昼", "你不是在追真相，你是在逼自己别回头。"),
        ],
        illustrations=[
            SimpleNamespace(
                is_canonical=True,
                file_path=image_path,
                candidate_index=1,
                prompt_text="cinematic still",
            )
        ],
    )


def make_chapter(order_index: int, image_path: str):
    return SimpleNamespace(
        id=order_index,
        order_index=order_index,
        title=f"第{order_index}章·雨幕里的回声",
        summary="一条被延迟播出的新闻，把几个人重新推回同一条命运轨道。",
        chapter_goal="把旧案线索和人物关系危机压到同一时刻爆发。",
        hook="有人比主角更早拿到了广播带原件。",
        narrative_blocks=[
            SimpleNamespace(order_index=1, content="暴雨把街区压成一层近乎失真的银灰，广播信号却在凌晨准时亮起。"),
            SimpleNamespace(order_index=2, content="林听知道这次不是巧合，她听见的不是新闻，而是有人刻意留下的邀请。"),
        ],
        scenes=[make_scene(order_index, image_path)],
    )


def build_project_fixture(tmp_path: Path):
    illustration_path = tmp_path / "canonical.png"
    Image.new("RGB", (1280, 720), (58, 74, 94)).save(illustration_path, format="PNG")

    characters = [
        SimpleNamespace(
            name="林听",
            role="调查记者",
            signature_line="她总在沉默里先听见真正的危险。",
            personality="冷静、敏锐、克制",
            goal="找回失踪师父留下的广播带",
            speech_style="短句、节制、逼近核心",
            appearance="黑发、瘦削、常穿深色风衣",
        ),
        SimpleNamespace(
            name="顾昼",
            role="电台修复师",
            signature_line="他修复的从来不只是机器，而是被人故意擦掉的证据。",
            personality="寡言、锋利、背负旧案",
            goal="阻止广播站旧案再次吞掉无辜者",
            speech_style="慢，像在给每句话找代价",
            appearance="高瘦、眉骨分明、旧衬衫与工装夹克",
        ),
    ]

    chapters = [make_chapter(1, str(illustration_path)), make_chapter(2, str(illustration_path))]
    project = SimpleNamespace(
        id=7,
        title="长夜回声",
        genre="都市悬疑",
        tone="克制、电影感、人物驱动",
        era="当代",
        target_length="8章，短剧节奏",
        logline="一段深夜广播重启十年前的旧案，三名主角被迫在真相和彼此之间重新站队。",
        characters=characters,
        chapters=chapters,
    )
    return project


def test_export_project_bundle_creates_composed_pdf_and_quality_metadata(tmp_path: Path):
    asset_store = LocalAssetStore(tmp_path / "storage", tmp_path / "exports")
    project = build_project_fixture(tmp_path)
    export_package = SimpleNamespace(
        id=3,
        project=project,
        project_id=project.id,
        status="queued",
        formats=["pdf", "docx"],
        files=[],
        selected_chapter_ids=[],
        selected_illustration_ids=[],
        created_at=datetime.now(UTC),
        completed_at=None,
    )

    export_project_bundle(project, export_package, asset_store)

    assert {item["format"] for item in export_package.files} == {"pdf", "docx"}

    pdf_entry = next(item for item in export_package.files if item["format"] == "pdf")
    assert Path(pdf_entry["path"]).exists()
    assert pdf_entry["size_bytes"] > 0
    assert pdf_entry["page_count"] >= 4
    assert pdf_entry["quality_check"]["status"] == "passed"
    assert pdf_entry["quality_check"]["render_check"]["status"] in {"passed", "skipped"}

    extracted_text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_entry["path"]).pages)
    assert "长夜回声" in extracted_text
    assert "角色档案" in extracted_text
    assert "Chapter 01" in extracted_text
    assert "第1章·雨幕里的回声" in extracted_text

    docx_entry = next(item for item in export_package.files if item["format"] == "docx")
    assert Path(docx_entry["path"]).exists()
    assert docx_entry["size_bytes"] > 0


def test_serialize_export_includes_delivery_summary_and_quality_signals(tmp_path: Path):
    export_root = tmp_path / "exports"
    export_root.mkdir(parents=True, exist_ok=True)
    pdf_path = export_root / "project_7" / "bundle.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4 test")

    project = SimpleNamespace(
        id=7,
        title="长夜回声",
        chapters=[SimpleNamespace(id=1), SimpleNamespace(id=2)],
        characters=[SimpleNamespace(id=1), SimpleNamespace(id=2)],
        illustrations=[SimpleNamespace(id=10, is_canonical=True), SimpleNamespace(id=11, is_canonical=False)],
    )
    export_package = SimpleNamespace(
        id=9,
        project=project,
        status="completed",
        formats=["pdf"],
        files=[
            {
                "format": "pdf",
                "path": str(pdf_path),
                "size_bytes": 12345,
                "page_count": 6,
                "quality_check": {"status": "passed", "checks": [{"key": "title_present", "status": "passed"}]},
            }
        ],
        selected_chapter_ids=[1, 2],
        selected_illustration_ids=[10],
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )

    payload = serialize_export(export_package, export_root)

    assert payload["delivery_summary"]["chapter_count"] == 2
    assert payload["delivery_summary"]["character_count"] == 2
    assert payload["delivery_summary"]["illustration_count"] == 1
    assert payload["delivery_summary"]["quality_status"] == "passed"
    assert payload["delivery_summary"]["total_size_bytes"] == 12345
    assert payload["files"][0]["filename"] == "bundle.pdf"
    assert payload["files"][0]["page_count"] == 6


def test_pdf_styles_use_distinct_contrast_palettes_for_light_and_dark_surfaces():
    styles = _build_pdf_styles()
    black = colors.black

    assert "PageMeta" in styles
    assert "CharacterCardMeta" in styles
    assert "CharacterCardBody" in styles
    assert styles["CoverEyebrow"].textColor == black
    assert styles["CoverTitle"].textColor == black
    assert styles["CoverLead"].textColor == black
    assert styles["CoverTag"].textColor == black
    assert styles["SectionTitle"].textColor == black
    assert styles["SectionTitleMinor"].textColor == black
    assert styles["ChapterEyebrow"].textColor == black
    assert styles["ChapterTitle"].textColor == black
    assert styles["Lead"].textColor == black
    assert styles["Body"].textColor == black
    assert styles["SceneMeta"].textColor == black
    assert styles["Dialogue"].textColor == black
    assert styles["PageMeta"].textColor == black
    assert styles["CharacterName"].textColor == black
    assert styles["CharacterCardBody"].textColor == black
    assert styles["CharacterCardMeta"].textColor == black
    assert styles["ImageCaption"].textColor == black
