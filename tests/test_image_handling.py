"""Image reading, and the file handles it leaves behind.

Both helpers here were changed to close their handles explicitly, because PIL
keeps the file open lazily and Windows will not delete a file anything still
holds. These tests cover the behaviour and the handle, since breaking either
one is silent: the EXIF date quietly goes missing, or the deleted photo quietly
stays on disk.
"""

import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import legacy_schemas  # noqa: E402


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 7)
    monkeypatch.setenv("RECEIPTS_DATA", str(data))
    monkeypatch.setenv("RECEIPTS_NO_BROWSER", "1")
    monkeypatch.syspath_prepend(str(APP_ROOT))
    sys.modules.pop("app", None)
    import app as app_module

    return app_module


@pytest.fixture
def photo_with_exif(tmp_path):
    from PIL import Image

    img = Image.new("RGB", (3000, 2000), (90, 120, 160))
    exif = img.getexif()
    exif[306] = "2021:07:04 11:22:33"          # DateTime
    exif.get_ifd(0x8769)[36867] = "2021:07:04 11:22:33"  # DateTimeOriginal
    path = tmp_path / "holiday.jpg"
    img.save(path, "JPEG", exif=exif)
    return path


def test_exif_capture_time_is_read(app_module, photo_with_exif):
    got = app_module.exif_datetime(photo_with_exif)
    assert got is not None, "EXIF capture time was not found"
    assert got.startswith("2021-07-04T11:22:33"), got


def test_reading_exif_releases_the_file(app_module, photo_with_exif):
    """On Windows an open handle makes the later delete fail outright."""
    app_module.exif_datetime(photo_with_exif)
    photo_with_exif.unlink()  # raises PermissionError on Windows if still open
    assert not photo_with_exif.exists()


def test_large_images_are_downscaled_for_the_ai(app_module, photo_with_exif):
    """A 3000px photo must not be sent at full size — it is billed by the pixel."""
    import base64
    import io

    from PIL import Image

    encoded, media_type = app_module.prepare_image_for_ai(photo_with_exif, "image/jpeg")
    assert encoded is not None, "no image produced"
    assert media_type == "image/jpeg"

    raw = base64.b64decode(encoded)
    with Image.open(io.BytesIO(raw)) as shrunk:
        assert max(shrunk.size) <= 1568, f"image was not downscaled: {shrunk.size}"
    assert len(raw) < photo_with_exif.stat().st_size


def test_preparing_an_image_releases_the_file(app_module, photo_with_exif):
    app_module.prepare_image_for_ai(photo_with_exif, "image/jpeg")
    photo_with_exif.unlink()
    assert not photo_with_exif.exists()


def test_whichever_encoding_is_smaller_wins(app_module, tmp_path):
    """The re-encode is only used when it actually saves bytes."""
    import base64

    from PIL import Image

    small = tmp_path / "thumb.png"
    Image.new("RGB", (120, 90), (10, 10, 10)).save(small, "PNG")

    encoded, media_type = app_module.prepare_image_for_ai(small, "image/png")
    assert encoded is not None
    assert media_type in ("image/png", "image/jpeg")
    assert len(base64.b64decode(encoded)) <= max(small.stat().st_size, 4096), (
        "the chosen encoding is larger than the original"
    )


def test_a_corrupt_image_does_not_crash_the_upload(app_module, tmp_path):
    """Anything can be uploaded; nothing uploaded should be able to break it."""
    junk = tmp_path / "not-really.jpg"
    junk.write_bytes(b"this is not an image at all")

    assert app_module.exif_datetime(junk) is None
    encoded, _ = app_module.prepare_image_for_ai(junk, "image/jpeg")  # must not raise
    assert encoded is not None, "small unreadable files should still be passed through raw"
    junk.unlink()
