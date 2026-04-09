from __future__ import annotations

import hashlib
import io
import textwrap
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFile, ImageOps


def ensure_dirs(*paths: Path):
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


class LocalAssetStore:
    def __init__(self, storage_dir: Path, export_dir: Path):
        self.storage_dir = storage_dir
        self.export_dir = export_dir
        ensure_dirs(self.storage_dir, self.export_dir)

    def save_upload(self, category: str, filename: str, payload: bytes) -> str:
        folder = self.storage_dir / category
        ensure_dirs(folder)
        safe_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
        path = folder / safe_name
        path.write_bytes(payload)
        return str(path)

    def create_story_image(self, category: str, basename: str, title: str, subtitle: str, tone: str) -> tuple[str, str]:
        folder = self.storage_dir / category
        thumb_folder = folder / "thumbs"
        ensure_dirs(folder, thumb_folder)

        seed = hashlib.sha1(f"{title}-{subtitle}-{tone}".encode("utf-8")).hexdigest()
        color_a = tuple(int(seed[i : i + 2], 16) for i in (0, 2, 4))
        color_b = tuple(int(seed[i : i + 2], 16) for i in (6, 8, 10))

        image = Image.new("RGB", (1280, 720), color_a)
        draw = ImageDraw.Draw(image)
        for idx in range(10):
            band_color = tuple((color_b[channel] + idx * 12) % 255 for channel in range(3))
            draw.rectangle((0, idx * 72, 1280, (idx + 1) * 72), fill=band_color)

        overlay = Image.new("RGBA", image.size, (10, 10, 18, 110))
        image = Image.alpha_composite(image.convert("RGBA"), overlay)
        draw = ImageDraw.Draw(image)

        draw.rounded_rectangle((64, 70, 1216, 650), radius=36, outline=(240, 226, 206, 180), width=3)
        draw.text((96, 104), title, fill=(245, 238, 224, 255))

        wrapped_subtitle = textwrap.fill(subtitle, width=24)
        draw.multiline_text((96, 210), wrapped_subtitle, fill=(230, 219, 201, 255), spacing=10)

        wrapped_tone = textwrap.fill(tone, width=32)
        draw.multiline_text((96, 500), wrapped_tone, fill=(198, 184, 167, 255), spacing=8)

        image = image.filter(ImageFilter.GaussianBlur(radius=0.2)).convert("RGB")

        filename = f"{basename}_{uuid.uuid4().hex[:8]}.png"
        image_path = folder / filename
        image.save(image_path, format="PNG")

        thumb_path = thumb_folder / filename
        thumbnail = ImageOps.fit(image, (360, 202))
        thumbnail.save(thumb_path, format="PNG")
        return str(image_path), str(thumb_path)

    def save_generated_image(
        self,
        *,
        category: str,
        basename: str,
        payload: bytes,
        media_type: str | None = None,
    ) -> tuple[str, str]:
        folder = self.storage_dir / category
        thumb_folder = folder / "thumbs"
        ensure_dirs(folder, thumb_folder)

        previous_truncated_setting = ImageFile.LOAD_TRUNCATED_IMAGES
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        try:
            image = Image.open(io.BytesIO(payload))
            image.load()
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = previous_truncated_setting
        image_format = (image.format or self._format_from_media_type(media_type) or "PNG").upper()
        extension = self._extension_for_format(image_format)
        filename = f"{basename}_{uuid.uuid4().hex[:8]}.{extension}"

        image_path = folder / filename
        thumbnail_path = thumb_folder / filename

        saved_image = image.convert("RGBA") if image.mode in {"RGBA", "LA", "P"} else image.convert("RGB")
        if image_format in {"JPEG", "JPG"}:
            saved_image = image.convert("RGB")
        saved_image.save(image_path, format=image_format)

        thumbnail = ImageOps.fit(saved_image.convert("RGB"), (360, 202))
        thumbnail.save(thumbnail_path, format="PNG")
        return str(image_path), str(thumbnail_path)

    @staticmethod
    def _format_from_media_type(media_type: str | None) -> str | None:
        if not media_type:
            return None
        mapping = {
            "image/jpeg": "JPEG",
            "image/jpg": "JPEG",
            "image/png": "PNG",
            "image/webp": "WEBP",
        }
        return mapping.get(media_type.lower())

    @staticmethod
    def _extension_for_format(image_format: str) -> str:
        mapping = {
            "JPEG": "jpg",
            "JPG": "jpg",
            "PNG": "png",
            "WEBP": "webp",
        }
        return mapping.get(image_format.upper(), "png")

    def remove_file(self, file_path: str | None, *, root: Path | None = None):
        if not file_path:
            return

        anchor = (root or self.storage_dir).resolve()
        candidate = Path(file_path).resolve()
        try:
            candidate.relative_to(anchor)
        except ValueError:
            return

        if candidate.exists():
            candidate.unlink()
            self._prune_empty_dirs(candidate.parent, anchor)

    def _prune_empty_dirs(self, start_dir: Path, anchor: Path):
        current = start_dir
        while current != anchor and current.is_dir():
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
