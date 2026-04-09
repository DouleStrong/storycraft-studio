import base64
from pathlib import Path

from app.storage import LocalAssetStore


TRUNCATED_PROVIDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4HWP4DwQACfsDfQ6OeuQAAAAASUVORK5CYII="
)


def test_save_generated_image_accepts_small_provider_png(tmp_path: Path):
    store = LocalAssetStore(
        storage_dir=tmp_path / "storage",
        export_dir=tmp_path / "exports",
    )

    image_path, thumb_path = store.save_generated_image(
        category="illustrations",
        basename="scene_1_candidate_1",
        payload=TRUNCATED_PROVIDER_PNG,
        media_type="image/png",
    )

    assert Path(image_path).exists()
    assert Path(thumb_path).exists()
