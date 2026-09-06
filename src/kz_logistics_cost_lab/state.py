"""Session-local input lifecycle, independently testable without Streamlit."""
import hashlib
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from .domain import ModelConfig
from .io import SCHEMAS
from .reporting import json_text
from .validation import date_value

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
RESULT_KEYS = ("analysis_result", "report_bytes", "report_error", "selected_proposal", "selected_pair", "selected_shipment", "zone_filter")


@dataclass(frozen=True)
class Upload:
    name: str
    content: bytes


def uploaded_files(uploads: Sequence[Upload]) -> tuple[dict[str, bytes], tuple[str, ...]]:
    required = {name for name, _ in SCHEMAS}
    names = [upload.name for upload in uploads]
    errors = []
    if len(names) != 3 or set(names) != required:
        errors.append("Caricare esattamente shipments.csv, packages.csv e tariffs.csv, senza file inattesi o nomi duplicati.")
    if len(names) != len(set(names)):
        errors.append("Nomi di file duplicati.")
    for upload in uploads:
        if not isinstance(upload.content, bytes):
            errors.append("Contenuto file illeggibile.")
        elif len(upload.content) > MAX_UPLOAD_BYTES:
            errors.append(f"{upload.name}: limite di 10 MiB per file superato.")
    return ({} if errors else {upload.name: upload.content for upload in uploads}), tuple(errors)


def parse_calendar(text: str) -> ModelConfig:
    tokens = [token.strip() for token in text.replace(",", "\n").splitlines() if token.strip()]
    try:
        return ModelConfig(nonworking_dates=frozenset(date_value(token) for token in tokens))
    except ValueError as exc:
        raise ValueError("Date non lavorative: usare YYYY-MM-DD, una data per riga o separate da virgole. " + str(exc)) from exc


def request_signature(mode: str, uploads: Sequence[Upload], calendar_text: str, sample_name: str = "") -> str:
    payload = {"mode": mode, "sample": sample_name, "calendar_input": calendar_text,
               "files": sorted((u.name, hashlib.sha256(u.content).hexdigest()) for u in uploads)}
    return hashlib.sha256(json_text(payload).encode()).hexdigest()


def synchronize(state: MutableMapping, signature: str) -> bool:
    changed = state.get("request_signature") != signature
    if changed:
        for key in RESULT_KEYS:
            state.pop(key, None)
        state["request_signature"] = signature
    return changed
