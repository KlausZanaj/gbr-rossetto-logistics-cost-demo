"""Build and verify a deterministic, source-only review archive."""
from pathlib import Path, PurePosixPath
import re
import struct
import zlib
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "review" / "kz-logistics-cost-lab-review.zip"
PREFIX = "kz-logistics-cost-lab"
ROOT_FILES = (
    ".gitattributes",
    ".gitignore",
    "LICENSE",
    "README.md",
    "app.py",
    "pyproject.toml",
    "requirements-lock.txt",
    "requirements.txt",
)
TREES = (".streamlit", "data/sample", "docs", "scripts", "src", "tests")
FORBIDDEN_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".audit", "outputs", "uploads", "dist", "node_modules"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".log"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".csv", ".json", ".yml", ".yaml"}
TEXT_FILENAMES = {"LICENSE", ".gitignore", ".gitattributes"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def has_forbidden_part(parts) -> bool:
    return bool(FORBIDDEN_PARTS.intersection(parts)) or any(part.endswith(".egg-info") for part in parts)


def source_files() -> list[Path]:
    files = [ROOT / name for name in ROOT_FILES]
    for tree in TREES:
        files.extend(path for path in (ROOT / tree).rglob("*") if path.is_file())
    selected = []
    for path in files:
        relative = path.relative_to(ROOT)
        if has_forbidden_part(relative.parts) or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            continue
        selected.append(path)
    missing = [str(path.relative_to(ROOT)) for path in (ROOT / name for name in ROOT_FILES) if not path.is_file()]
    if missing:
        raise FileNotFoundError("File di progetto mancanti: " + ", ".join(missing))
    return sorted(set(selected), key=lambda path: path.relative_to(ROOT).as_posix())


def build(output: Path = OUTPUT) -> tuple[str, ...]:
    output.parent.mkdir(parents=True, exist_ok=True)
    expected = []
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in source_files():
            relative = PurePosixPath(PREFIX) / PurePosixPath(path.relative_to(ROOT).as_posix())
            name = str(relative)
            expected.append(name)
            info = ZipInfo(name, date_time=(2026, 9, 6, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return tuple(expected)


def is_text_file(path: PurePosixPath) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_FILENAMES


def _display_name(name: str) -> str:
    """Return an archive-relative name, never a host filesystem path."""
    path = PurePosixPath(name)
    if path.parts and path.parts[0] == PREFIX:
        return str(PurePosixPath(*path.parts[1:]))
    return path.name or "voce ZIP"


def _finding(name: str, category: str) -> AssertionError:
    return AssertionError(f"Finding in {_display_name(name)}: {category}.")


def _content_finding(content: str) -> str | None:
    backslash = re.escape(chr(92))
    slash = re.escape(chr(47))
    if re.search(r"(?i)(?<![A-Za-z0-9])[A-Za-z]:" + backslash + r"[^\s<>'\"]+", content):
        return "percorso Windows assoluto"
    local_roots = ("Users", "home", "root", "tmp", "var/tmp", "private/tmp")
    posix_path = r"(?<![:/])" + slash + r"(?:" + "|".join(local_roots) + r")" + slash + r"[^\s<>'\"]+"
    wsl_path = r"(?<![:/])" + slash + r"mnt" + slash + r"[a-zA-Z]" + slash + r"[^\s<>'\"]+"
    if re.search(posix_path, content) or re.search(wsl_path, content):
        return "percorso POSIX assoluto"
    assignment = re.compile(
        r"(?i)\b(?:password|passwd|api[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token)\b"
        r"\s*[:=]\s*['\"]?[^\s'\"<>{}]{6,}"
    )
    if assignment.search(content):
        return "dato sensibile"
    private_key_marker = "-" * 5 + "BEGIN " + "PRIVATE KEY" + "-" * 5
    credential_prefixes = ("gh" + "p_", "gh" + "o_", "AK" + "IA")
    if private_key_marker in content or any(prefix in content for prefix in credential_prefixes):
        return "dato sensibile"
    return None


def _decode_png_metadata(chunk_type: bytes, data: bytes) -> str:
    try:
        if chunk_type == b"tEXt":
            return data.decode("latin-1")
        if chunk_type == b"zTXt":
            keyword, remainder = data.split(b"\0", 1)
            if not remainder or remainder[0] != 0:
                raise ValueError
            return keyword.decode("latin-1") + "\n" + zlib.decompress(remainder[1:]).decode("latin-1")
        if chunk_type == b"iTXt":
            keyword, remainder = data.split(b"\0", 1)
            if len(remainder) < 2:
                raise ValueError
            compressed, method = remainder[0], remainder[1]
            language, translated, text = remainder[2:].split(b"\0", 2)
            if method != 0 or compressed not in (0, 1):
                raise ValueError
            if compressed:
                text = zlib.decompress(text)
            return "\n".join(
                (keyword.decode("latin-1"), language.decode("ascii"), translated.decode("utf-8"), text.decode("utf-8"))
            )
    except (UnicodeDecodeError, ValueError, zlib.error) as exc:
        raise ValueError("metadati testuali PNG non validi") from exc
    return ""


def validate_png(data: bytes, name: str) -> None:
    if not data.startswith(PNG_SIGNATURE):
        raise _finding(name, "firma PNG non valida")

    offset = len(PNG_SIGNATURE)
    chunk_index = 0
    seen_ihdr = False
    seen_idat = False
    seen_iend = False
    idat = bytearray()
    while offset < len(data):
        if len(data) - offset < 12:
            raise _finding(name, "struttura PNG non valida")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise _finding(name, "struttura PNG non valida")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        stored_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        if len(chunk_type) != 4 or not all(chr(value).isalpha() and value < 128 for value in chunk_type):
            raise _finding(name, "tipo chunk PNG non valido")
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != stored_crc:
            raise _finding(name, "CRC PNG non valido")

        if chunk_index == 0 and chunk_type != b"IHDR":
            raise _finding(name, "struttura PNG non valida")
        if chunk_type == b"IHDR":
            if seen_ihdr or length != 13:
                raise _finding(name, "header PNG non valido")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", chunk_data)
            valid_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if (
                width == 0
                or height == 0
                or bit_depth not in valid_depths.get(color_type, set())
                or compression != 0
                or filtering != 0
                or interlace not in (0, 1)
            ):
                raise _finding(name, "header o dimensioni PNG non validi")
            seen_ihdr = True
        elif chunk_type == b"IDAT":
            if not seen_ihdr or seen_iend:
                raise _finding(name, "ordine chunk PNG non valido")
            seen_idat = True
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            if length != 0 or not seen_ihdr or not seen_idat or seen_iend:
                raise _finding(name, "chiusura PNG non valida")
            seen_iend = True
            if chunk_end != len(data):
                raise _finding(name, "dati dopo IEND")
        elif chunk_type in {b"tEXt", b"zTXt", b"iTXt"}:
            try:
                metadata = _decode_png_metadata(chunk_type, chunk_data)
            except ValueError:
                raise _finding(name, "metadati testuali PNG non validi") from None
            category = _content_finding(metadata)
            if category:
                raise _finding(name, "metadati PNG: " + category)

        offset = chunk_end
        chunk_index += 1
        if seen_iend:
            break

    if not (seen_ihdr and seen_idat and seen_iend) or offset != len(data):
        raise _finding(name, "struttura PNG incompleta")
    try:
        decompressed = zlib.decompress(bytes(idat))
    except zlib.error:
        raise _finding(name, "dati immagine PNG non validi") from None
    if not decompressed:
        raise _finding(name, "dati immagine PNG vuoti")


def verify(expected: tuple[str, ...], output: Path = OUTPUT) -> None:
    with ZipFile(output) as archive:
        actual = tuple(archive.namelist())
        if actual != expected or len(actual) != len(set(actual)):
            raise AssertionError("Elenco ZIP inatteso o duplicato.")
        if archive.testzip() is not None:
            raise AssertionError("Contenuto ZIP corrotto.")
        for name in actual:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != PREFIX:
                raise AssertionError("Percorso ZIP non sicuro.")
            if has_forbidden_part(path.parts) or path.suffix.lower() in FORBIDDEN_SUFFIXES:
                raise _finding(name, "artefatto escluso")
            content = archive.read(name)
            if path.suffix.lower() == ".png":
                validate_png(content, name)
            elif is_text_file(path):
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    raise _finding(name, "testo UTF-8 non valido") from None
                category = _content_finding(text)
                if category:
                    raise _finding(name, category)


def main():
    entries = build()
    verify(entries)
    print(f"Creato {OUTPUT} con {len(entries)} file verificati:")
    print("\n".join(entries))


if __name__ == "__main__":
    main()
