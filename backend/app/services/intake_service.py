"""A file dropped on the project form, read into a draft (``POST /projects/intake``).

The file's text is read here (TXT, MD, CSV and JSON decoded; DOCX through the
standard ``zipfile`` and ``defusedxml``; PDF through ``pypdf`` when it is
installed), then the draft is filled by the model when one is configured, else
by rules (``app.agents.intake``). Nothing is saved to a project: the reading is
stored in ``project_intakes`` so the saved project can cite it, and the person
presses Save on the form.
"""

from __future__ import annotations

import csv
import hashlib
import importlib
import io
import json
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeET
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import intake as reader
from app.agents.base import AgentRuntime, GeminiUnavailable, agent_runtime
from app.config import get_settings
from app.data import catalogues
from app.db.repositories.missions import MissionRepository
from app.db.repositories.projects import ProjectRepository
from app.db.repositories.sites import SiteRepository
from app.services import audit_service, settings_service
from app.services.auth_service import Claims

log = logging.getLogger(__name__)

MEDIA_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
    "json": "application/json",
}
#: The largest uncompressed document.xml a DOCX may hold (a zip bomb stops here).
DOCX_XML_MAX = 40 * 1024 * 1024
EXCERPT_CHARS = 4000
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class BadFile(ValueError):
    """The file cannot be read: its kind is not taken, or it is empty or damaged."""


@dataclass
class Extracted:
    doc: reader.Doc
    warnings: list[str] = field(default_factory=list)
    #: A PDF whose text could not be read here (no pypdf, or scanned pages).
    pdf_unread: bool = False


def clean_filename(name: str) -> str:
    base = PureWindowsPath(PurePosixPath(name or "").name).name.strip()
    return "".join(c for c in base if ord(c) >= 32)[:255] or "file"


def extension(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in MEDIA_TYPES:
        raise BadFile(
            f"'{filename}' is not a kind of file the reader takes " f"({', '.join(MEDIA_TYPES)})."
        )
    return ext


def decode(data: bytes) -> tuple[str, str | None]:
    """Text from bytes: UTF-8 (with or without a BOM), else Windows-1252, said so."""
    try:
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), (
            "The file is not UTF-8 text; it was read as Windows-1252, so a few characters "
            "may be wrong."
        )


def _json_lines(obj: Any, path: tuple[str, ...] = ()) -> list[str]:
    """'mission name: Athena' lines from a JSON object, so labels read as they do in prose."""
    if isinstance(obj, dict):
        return [ln for k, v in obj.items() for ln in _json_lines(v, (*path, str(k)))]
    if isinstance(obj, list):
        if all(not isinstance(v, dict | list) for v in obj):
            label = " ".join(path).replace("_", " ")
            return [f"{label}: {', '.join(str(v) for v in obj)}"] if obj else []
        return [ln for v in obj for ln in _json_lines(v, path)]
    if obj is None:
        return []
    label = " ".join(path).replace("_", " ")
    return [f"{label}: {obj}" if label else str(obj)]


def _csv_lines(text: str) -> list[str]:
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if rows and all(len(r) == 2 for r in rows):
        return [f"{a.strip()}: {b.strip()}" for a, b in rows]
    if len(rows) > 1 and len(rows[0]) <= 30:
        head = [h.strip() for h in rows[0]]
        return [
            "; ".join(f"{h}: {c.strip()}" for h, c in zip(head, r, strict=False) if c.strip())
            for r in rows[1:]
        ]
    return [" | ".join(c.strip() for c in r) for r in rows]


def docx_text(data: bytes) -> str:
    """Each paragraph of a DOCX (body and tables) as one line."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > DOCX_XML_MAX:
                raise BadFile("The DOCX is too large to read once unpacked.")
            xml = z.read(info)
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise BadFile("This is not a readable DOCX file.") from exc
    try:
        root = SafeET.fromstring(xml)
    except (SafeET.ParseError, DefusedXmlException) as exc:
        raise BadFile("The DOCX's text could not be read.") from exc
    lines = []
    for p in root.iter(f"{_W}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag in (f"{_W}tab", f"{_W}br"):
                parts.append(" ")
        lines.append("".join(parts))
    return "\n".join(lines)


def pdf_pages(data: bytes) -> list[str] | None:
    """Each page's text, or None when ``pypdf`` is not installed (it is optional)."""
    try:
        pypdf = importlib.import_module("pypdf")
    except ImportError:
        return None
    try:
        pdf = pypdf.PdfReader(io.BytesIO(data))
        return [str(page.extract_text() or "") for page in pdf.pages]
    except Exception as exc:  # pypdf raises its own many kinds on a damaged file
        raise BadFile("This PDF could not be opened.") from exc


def extract(data: bytes, ext: str) -> Extracted:
    """The file's text as a :class:`reader.Doc`, with what could not be read said."""
    if not data:
        raise BadFile("The file is empty.")
    warnings: list[str] = []
    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            raise BadFile("This is not a PDF file.")
        pages = pdf_pages(data)
        if pages is None:
            return Extracted(reader.Doc(()), warnings, pdf_unread=True)
        blank = [i for i, p in enumerate(pages, 1) if not p.strip()]
        if blank and len(blank) == len(pages):
            warnings.append(
                "No text could be read from the PDF's pages; they may be scanned images."
            )
            return Extracted(reader.Doc((), paged=True), warnings, pdf_unread=True)
        if blank:
            listed = ", ".join(str(i) for i in blank[:10])
            warnings.append(
                f"No text could be read from page{'s' if len(blank) > 1 else ''} {listed}; "
                "they may be scanned images."
            )
        return Extracted(reader.Doc.from_pages(pages), warnings)
    if ext == "docx":
        return Extracted(reader.Doc.from_text(docx_text(data)), warnings)
    text, note = decode(data)
    if note:
        warnings.append(note)
    if ext == "json":
        try:
            text = "\n".join(_json_lines(json.loads(text)))
        except ValueError:
            warnings.append("The JSON could not be parsed; it was read as plain text.")
    elif ext == "csv":
        text = "\n".join(_csv_lines(text))
    if not text.strip():
        raise BadFile("The file has no text in it.")
    return Extracted(reader.Doc.from_text(text), warnings)


async def lexicon(session: AsyncSession) -> reader.Lexicon:
    """The names a reading looks for: the catalogues, the missions' providers and landers,
    and the surveyed sites."""

    def records(name: str) -> tuple[Any, ...]:
        try:
            return catalogues.load(name).records
        except catalogues.CatalogueError:
            return ()

    missions = await MissionRepository(session).find()
    sites, _ = await SiteRepository(session).list_sites(kind=None, limit=1000)
    return reader.Lexicon(
        vehicles=tuple(reader.vehicle_names(v.id, v.name) for v in records("vehicles")),
        pads=tuple(reader.pad_names(p.id, p.name) for p in records("launch_sites")),
        relays=tuple(
            reader.plain_names(r.id, r.name) for r in records("relays") if r.role == "relay"
        ),
        providers=tuple(
            sorted({m.provider for m in missions if m.provider}, key=len, reverse=True)
        ),
        landers=tuple(sorted({m.lander for m in missions if m.lander}, key=len, reverse=True)),
        sites=tuple(reader.SiteName(s.id, s.name, s.lat_deg, s.lon_deg) for s in sites),
    )


#: Bounds the form takes (``ProjectIn``): a reading outside them is not kept.
_BOUNDS: dict[str, tuple[float, float]] = {
    "planned_surface_days": (0.0, 3650.0),
    "lifecycle.flight_days": (0.0, 1000.0),
    "lifecycle.mass_kg": (0.0, 1.0e6),
}
_LIMITS = {"name": 160, "provider": 120, "lander": 120, "vehicle_name": 80, "task_order": 40}


def fit(reading: reader.Reading) -> reader.Reading:
    """Keep the draft inside what the form accepts; anything outside is not kept, and said."""
    d = reading.draft
    for path, (lo, hi) in _BOUNDS.items():
        key = path.removeprefix("lifecycle.")
        holder = d.get("lifecycle", {}) if path.startswith("lifecycle.") else d
        v = holder.get(key)
        if v is not None and not (lo < float(v) <= hi):
            holder.pop(key, None)
            reading.fields[path] = {
                "confidence": "not_found",
                "evidence": reading.fields[path].get("evidence"),
                "page": reading.fields[path].get("page"),
                "note": f"The file gives {v:g}, which is outside what the form takes.",
            }
    for key, n in _LIMITS.items():
        if isinstance(d.get(key), str):
            d[key] = d[key][:n]
    pays = []
    for p in (d.get("payloads") or [])[:60]:
        pays.append(
            {
                "name": str(p["name"])[:200],
                "acronym": (p.get("acronym") or None) and str(p["acronym"])[:40],
                "organisation": (p.get("organisation") or None) and str(p["organisation"])[:200],
                "instrument_types": list(p.get("instrument_types") or [])[:12],
                "purpose": (p.get("purpose") or None) and str(p["purpose"])[:2000],
            }
        )
    if "payloads" in d:
        d["payloads"] = pays
    t = d.get("target")
    if isinstance(t, dict) and "lat_deg" in t:
        if not (-90.0 <= float(t["lat_deg"]) <= 90.0):
            d.pop("target")
            reading.fields["target"]["confidence"] = "not_found"
            reading.fields["target"]["note"] = "The latitude is out of range."
        else:
            t["lon_deg"] = float(t["lon_deg"]) % 360.0
            if "name" in t:
                t["name"] = str(t["name"])[:160]
    return reading


async def read_file(
    session: AsyncSession, who: Claims, data: bytes, filename: str, media_type: str | None
) -> dict[str, Any]:
    """Read the file into a draft, store the reading, and return the contract's ``Intake``."""
    if not who.named:
        raise audit_service.NotNamed("Changes are recorded against a name; this session has none.")
    name = clean_filename(filename)
    ext = extension(name)
    media = (media_type or "").split(";")[0].strip().lower() or MEDIA_TYPES[ext]
    extracted = extract(data, ext)
    lex = await lexicon(session)
    s = get_settings()
    ai = await settings_service.ai_settings(session)
    warnings = list(extracted.warnings)
    reading: reader.Reading | None = None
    method, model = "rules", None
    if s.agents_enabled and ai.enabled:
        try:
            runtime = AgentRuntime(enabled=True, models=ai.models, models_light=ai.models_light)
            with agent_runtime(runtime):
                reading, model = await reader.read_with_model(
                    session,
                    extracted.doc,
                    lex,
                    filename=name,
                    data=data,
                    media_type=media,
                    is_pdf=ext == "pdf",
                )
            method = "model"
        except GeminiUnavailable:
            reading = None
        except reader.ModelFailed as exc:
            warnings.append(
                f"The AI model could not read the file ({exc}), so it was read by rules: "
                "dates, coordinates, masses and catalogue names only."
            )
    if reading is None:
        if extracted.pdf_unread:
            warnings.append(
                "A PDF's text cannot be read here without the AI model, so nothing was "
                "filled in. Fill in the form, or drop the same document as DOCX or text."
            )
            reading = reader.assemble([], [])
        else:
            reading = reader.read_rules(extracted.doc, lex)
    reading = fit(reading)
    warnings += reading.warnings
    text = extracted.doc.text
    sha = hashlib.sha256(data).hexdigest()
    extracted_json = {
        "draft": reading.draft,
        "fields": reading.fields,
        "characters_read": len(text),
    }
    intake_id = await ProjectRepository(session).save_intake(
        filename=name,
        media_type=media[:127],
        size_bytes=len(data),
        sha256=sha,
        method=method,
        model=model,
        extracted=extracted_json,
        warnings=warnings,
        text_excerpt=text[:EXCERPT_CHARS],
        created_by=who.user_id,
    )
    found = sorted(p for p, f in reading.fields.items() if f["confidence"] != "not_found")
    await audit_service.record(
        session,
        who,
        action="read_file",
        entity="intake",
        entity_id=str(intake_id),
        before=None,
        after={
            "filename": name,
            "size_bytes": len(data),
            "sha256": sha,
            "method": method,
            "model": model,
            "found": found,
        },
    )
    return {
        "intake_id": intake_id,
        "filename": name,
        "media_type": media,
        "size_bytes": len(data),
        "method": method,
        "model": model,
        "draft": reading.draft,
        "fields": reading.fields,
        "warnings": warnings,
        "characters_read": len(text),
    }
