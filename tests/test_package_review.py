import struct
import zlib
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts import package_review


def _chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _png(extra_chunk: bytes = b"") -> bytes:
    raw_pixel = b"\x00\x00\x00\x00"
    return (
        package_review.PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + extra_chunk
        + _chunk(b"IDAT", zlib.compress(raw_pixel))
        + _chunk(b"IEND", b"")
    )


def _archive(tmp_path, files):
    destination = tmp_path / "review.zip"
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return destination, tuple(files)


def test_binary_png_bytes_that_resemble_windows_path_are_accepted(tmp_path):
    separator = bytes((92,))
    binary_payload = b"\x00\xffC:" + separator + separator.join((b"Users", b"casual-match", b"file.bin")) + b"\x80"
    png = _png(_chunk(b"raND", binary_payload))
    name = f"{package_review.PREFIX}/docs/screenshots/image.png"
    archive, expected = _archive(tmp_path, {name: png})

    package_review.verify(expected, archive)


@pytest.mark.parametrize("png", [b"not-a-png", _png()[:-1]])
def test_invalid_or_corrupt_png_is_rejected_without_exposing_content(tmp_path, png):
    name = f"{package_review.PREFIX}/docs/screenshots/image.png"
    archive, expected = _archive(tmp_path, {name: png})

    with pytest.raises(AssertionError) as error:
        package_review.verify(expected, archive)

    assert "PNG" in str(error.value)
    assert "C:" + chr(92) not in str(error.value)


@pytest.mark.parametrize(
    ("secret_content", "category"),
    [
        (
            "cartella=C:" + chr(92) + chr(92).join(("Users", "mario.rossi", "Desktop", "privato")),
            "percorso Windows assoluto",
        ),
        ("cartella=" + "/".join(("", "home", "mario.rossi", "privato")), "percorso POSIX assoluto"),
        ("api" + "_key=super-secret-value", "dato sensibile"),
    ],
)
def test_sensitive_text_is_rejected_without_exposing_value(tmp_path, secret_content, category):
    name = f"{package_review.PREFIX}/notes.txt"
    archive, expected = _archive(tmp_path, {name: secret_content.encode()})

    with pytest.raises(AssertionError) as error:
        package_review.verify(expected, archive)

    message = str(error.value)
    assert category in message
    assert secret_content not in message
    assert "mario.rossi" not in message
    assert "super-secret-value" not in message


def test_current_project_archive_with_three_screenshots_is_accepted(tmp_path):
    destination = tmp_path / "project-review.zip"

    expected = package_review.build(destination)
    package_review.verify(expected, destination)

    screenshot_entries = {
        name for name in expected if name.startswith(f"{package_review.PREFIX}/docs/screenshots/")
    }
    assert screenshot_entries == {
        f"{package_review.PREFIX}/docs/screenshots/demo-overview.png",
        f"{package_review.PREFIX}/docs/screenshots/cost-comparison.png",
        f"{package_review.PREFIX}/docs/screenshots/proposal-detail.png",
    }
