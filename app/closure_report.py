from __future__ import annotations

"""Deterministic customer-facing closure artifacts.

This module deliberately has no database or web dependencies.  The control
plane freezes a JSON snapshot first; this renderer can then be contract-tested
and reproduced without consulting mutable operational state.
"""

import csv
import hashlib
import io
import json
import re
import textwrap
import unicodedata
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable

from app.duration_format import format_duration


SCHEMA_VERSION = "raijin.project-closure.v2"


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=json_default,
    ).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip("-.")[:96] or "project"


def safe_csv_cell(value: Any) -> Any:
    """Prevent spreadsheet formula execution in customer-delivered CSVs."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return json_default(value)
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def csv_bytes(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> bytes:
    target = io.StringIO(newline="")
    writer = csv.writer(target, lineterminator="\n")
    writer.writerow(list(headers))
    for row in rows:
        writer.writerow([safe_csv_cell(value) for value in row])
    return target.getvalue().encode("utf-8-sig")


def format_bytes(value: int | float) -> str:
    amount = float(value or 0)
    for unit in ("PB", "TB", "GB", "MB", "KB"):
        factor = {"PB": 1024**5, "TB": 1024**4, "GB": 1024**3,
                  "MB": 1024**2, "KB": 1024}[unit]
        if amount >= factor:
            return f"{amount / factor:,.2f} {unit}"
    return f"{int(amount):,} B"


def _pdf_string(value: str) -> bytes:
    raw = unicodedata.normalize("NFKD", str(value)).encode("cp1252", "replace")
    escaped = bytearray()
    for byte in raw:
        if byte in (40, 41, 92):
            escaped.extend(b"\\" + bytes([byte]))
        elif byte < 32 or byte > 126:
            escaped.extend(f"\\{byte:03o}".encode())
        else:
            escaped.append(byte)
    return bytes(escaped)


def _pdf_lines(snapshot: dict, manifest_hash: str, preview: bool) -> list[tuple[str, int, bool]]:
    project = snapshot["project"]
    totals = snapshot["totals"]
    status = "PREVIA - PROJETO NAO ENCERRADO" if preview else snapshot["closure"]["status"]
    lines: list[tuple[str, int, bool]] = [
        ("RAIJIN DATA MIGRATION", 18, True),
        ("Relatorio final de encerramento", 16, True),
        (f"Projeto: {project['name']}", 12, True),
        (f"Relatorio: {snapshot['report_id']} | Revisao: R{snapshot['revision']}", 9, False),
        (f"Emitido em: {snapshot['generated_at']} | Base temporal: UTC", 9, False),
        (f"Status: {status}", 12, True),
        ("", 8, False),
        ("Resumo executivo", 13, True),
        (f"Sources: {totals['sources']} | Waves: {totals['waves']}", 10, False),
        (f"Objetos entregues: {totals['delivered_objects']:,} de {totals['objects']:,} ({totals['object_percent']:.2f}%)", 10, False),
        (f"Dados entregues: {format_bytes(totals['delivered_bytes'])} de {format_bytes(totals['bytes'])} ({totals['byte_percent']:.2f}%)", 10, False),
        (f"Divergencias no destino: {totals['destination_differences']:,}", 10, False),
        ("", 8, False),
        ("Escopo e resultado por source", 13, True),
    ]
    for source in snapshot["sources"]:
        lifecycle = "DESATIVADA" if source["deactivated"] else "ATIVA"
        lines.extend([
            (f"{source['name']} ({lifecycle})", 11, True),
            (f"  Origem: s3://{source['s3_bucket']} ({source['aws_region']})", 9, False),
            (f"  Destino: oci://{source['destination_bucket']}/{source['destination_prefix']}", 9, False),
            (f"  Entrega: {source['delivered_objects']:,}/{source['objects']:,} objetos; {format_bytes(source['delivered_bytes'])}/{format_bytes(source['bytes'])}", 9, False),
            (f"  Reconciliacao OCI: {source['destination_validation_status']} em {source['destination_validated_at'] or '-'}", 9, False),
            (f"  Integridade confirmada no destino: {source['delivery_accepted_objects']:,}/{source['objects']:,}", 9, False),
        ])
    lines.extend([("", 8, False), ("Execucao e desempenho", 13, True)])
    execution = snapshot["execution"]
    lines.extend([
        (f"Restore estimado/realizado: {format_duration(execution['restore_estimated_seconds'])} / {format_duration(execution['restore_actual_seconds'])}", 9, False),
        (f"Transferencia estimada/realizada: {format_duration(execution['transfer_estimated_seconds'])} / {format_duration(execution['transfer_actual_seconds'])}", 9, False),
        (f"Throughput agregado medio: {execution['average_throughput_mbps']:.2f} Mbps; pico: {execution['maximum_throughput_mbps']:.2f} Mbps", 9, False),
        (f"Itens com retry: {execution['items_with_retry']:,}; recuperacoes de lease: {execution['lease_recovery_events']:,}", 9, False),
    ])
    lines.extend([
        ("", 8, False), ("Declaracao de encerramento", 13, True),
        (("Com base no inventario final, nas evidencias persistidas de entrega e na reconciliacao do destino, o projeto encontra-se concluido."
          if not preview else "Esta e uma previa para conferencia e nao comprova o encerramento do projeto."), 10, False),
        ("", 8, False),
        (f"Manifesto SHA-256: {manifest_hash}", 8, False),
        (f"Raijin {snapshot['application']['version']} ({snapshot['application']['revision']}) | modo {snapshot['application']['mode']}", 8, False),
        ("Verifique checksums.sha256 antes de utilizar as evidencias tecnicas.", 8, False),
    ])
    return lines


def simple_pdf(snapshot: dict, manifest_hash: str, *, preview: bool = False) -> bytes:
    """Produce a dependency-free, paginated PDF 1.4 with WinAnsi text."""
    logical = _pdf_lines(snapshot, manifest_hash, preview)
    wrapped: list[tuple[str, int, bool]] = []
    for text, size, bold in logical:
        chunks = textwrap.wrap(text, width=max(45, int(98 * 9 / max(size, 1))),
                               break_long_words=True, break_on_hyphens=False) or [""]
        wrapped.extend((chunk, size, bold) for chunk in chunks)
    pages = [wrapped[index:index + 48] for index in range(0, len(wrapped), 48)] or [[]]
    objects: list[bytes] = []
    def add(value: bytes) -> int:
        objects.append(value)
        return len(objects)
    font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    page_ids: list[int] = []
    content_ids: list[int] = []
    for page_number, page in enumerate(pages, 1):
        commands = [b"BT", b"55 790 Td"]
        for text, size, bold in page:
            commands.append(f"/{'F2' if bold else 'F1'} {size} Tf".encode())
            commands.append(f"0 -{max(12, size + 4)} Td".encode())
            commands.append(b"(" + _pdf_string(text) + b") Tj")
        commands.extend([b"/F1 8 Tf", b"0 -18 Td", b"(Pagina " + str(page_number).encode() + b" de " + str(len(pages)).encode() + b") Tj", b"ET"])
        stream = b"\n".join(commands)
        content_ids.append(add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"))
        page_ids.append(add(b"PENDING"))
    pages_id = add(b"PENDING")
    for index, page_id in enumerate(page_ids):
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] ".encode()
            + f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> ".encode()
            + f"/Contents {content_ids[index]} 0 R >>".encode()
        )
    objects[pages_id - 1] = b"<< /Type /Pages /Count " + str(len(page_ids)).encode() + b" /Kids [" + b" ".join(f"{item} 0 R".encode() for item in page_ids) + b"] >>"
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output)); output.extend(f"{number} 0 obj\n".encode()); output.extend(obj); output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n".encode()); output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]: output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
    return target.getvalue()


def build_artifacts(snapshot: dict, *, preview: bool = False) -> dict[str, Any]:
    sources = snapshot["sources"]
    waves = snapshot["waves"]
    inventory = snapshot["inventory"]
    files: dict[str, bytes] = {
        "project-summary.json": canonical_json(snapshot),
        "sources.csv": csv_bytes(
            ["source_id", "source", "lifecycle", "s3_bucket", "aws_region", "destination_bucket", "destination_prefix", "objects", "bytes", "delivered_objects", "delivered_bytes", "destination_validation", "validated_at"],
            ([s["id"], s["name"], "DEACTIVATED" if s["deactivated"] else "ACTIVE", s["s3_bucket"], s["aws_region"], s["destination_bucket"], s["destination_prefix"], s["objects"], s["bytes"], s["delivered_objects"], s["delivered_bytes"], s["destination_validation_status"], s["destination_validated_at"]] for s in sources),
        ),
        "waves.csv": csv_bytes(
            ["wave_id", "source", "wave", "status", "restore_tier", "restore_days", "objects", "bytes", "restore_requested_at", "first_available_at", "restore_completed_at", "transfer_started_at", "transfer_completed_at"],
            ([w.get(key) for key in ("id", "source_name", "name", "status", "restore_tier", "restore_days", "objects", "bytes", "restore_requested_at", "first_available_at", "restore_completed_at", "transfer_started_at", "transfer_completed_at")] for w in waves),
        ),
        "inventory.csv": csv_bytes(
            ["source", "object_key", "destination_object_key", "version_id", "size_bytes", "storage_class", "state", "wave_id", "transferred_at", "delivery_integrity_status", "checksum_algorithm", "delivery_checksum"],
            ([o.get(key) for key in ("source_name", "object_key", "destination_object_key", "version_id", "size_bytes", "storage_class", "state", "wave_id", "transferred_at", "delivery_integrity_status", "checksum_algorithm", "delivery_checksum")] for o in inventory),
        ),
        "destination-validation.csv": csv_bytes(
            ["source", "status", "validated_at", "missing", "size_mismatches", "metadata_mismatches", "extras"],
            ([s["name"], s["destination_validation_status"], s["destination_validated_at"], s["destination_differences"]["missing"], s["destination_differences"]["size_mismatches"], s["destination_differences"]["metadata_mismatches"], s["destination_differences"]["extras"]] for s in sources),
        ),
        "exceptions.csv": csv_bytes(["code", "description", "accepted", "reason"], ([item["code"], item["description"], item.get("accepted", False), item.get("reason", "")] for item in snapshot["closure"].get("reservations", []))),
    }
    manifest = {"schema": SCHEMA_VERSION, "report_id": snapshot["report_id"],
        "revision": snapshot["revision"], "project": snapshot["project"],
        "generated_at": snapshot["generated_at"], "application": snapshot["application"],
        # The PDF carries the hash of this exact manifest.  The PDF itself is
        # covered by checksums.sha256 and by the immutable database metadata,
        # avoiding an impossible circular PDF <-> manifest hash dependency.
        "files": {name: {"sha256": sha256(data), "bytes": len(data)}
                  for name, data in sorted(files.items())}}
    manifest_bytes = canonical_json(manifest)
    manifest_hash = sha256(manifest_bytes)
    pdf = simple_pdf(snapshot, manifest_hash, preview=preview)
    files["relatorio-final.pdf" if not preview else "relatorio-previa.pdf"] = pdf
    files["manifest.json"] = manifest_bytes
    checksum_lines = [f"{sha256(data)}  {name}" for name, data in sorted(files.items())]
    files["checksums.sha256"] = ("\n".join(checksum_lines) + "\n").encode()
    package = _zip_bytes(files)
    return {"pdf": pdf, "package": package, "manifest": manifest,
            "manifest_bytes": manifest_bytes, "manifest_sha256": manifest_hash,
            "pdf_sha256": sha256(pdf), "package_sha256": sha256(package), "files": files}
