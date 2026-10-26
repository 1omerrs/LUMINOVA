"""Bulk customer import from CSV or XLSX.

The file arrives base64 encoded in JSON, so no multipart dependency is needed. XLSX is
read with the standard library (zip + XML) and only the first worksheet is used.
"""

import base64
import binascii
import csv
import io
import re
import uuid
import zipfile
from xml.etree import ElementTree

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import AuditLog
from app.modules.customers.matching import normalize_name, phone_key
from app.modules.customers.models import Customer
from app.modules.customers.schemas import (
    CustomerInput,
    ImportDuplicate,
    ImportError_,
    ImportMapping,
    ImportPreview,
    ImportReport,
)
from app.services.auth import Member
from app.services.automation import emit

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000
FIELDS = ("name", "email", "phone", "note")
HINTS = {
    "name": ("ad", "adı", "isim", "unvan", "ünvan", "firma", "müşteri", "musteri", "şirket", "sirket", "name", "company", "customer"),
    "email": ("e-posta", "eposta", "email", "e-mail", "mail"),
    "phone": ("telefon", "tel", "gsm", "cep", "phone", "mobile"),
    "note": ("not", "açıklama", "aciklama", "note", "notes", "description"),
}
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class ImportFailure(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail


def _decode(content: str) -> bytes:
    try:
        raw = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError):
        raise ImportFailure("Dosya okunamadı.") from None
    if len(raw) > MAX_BYTES:
        raise ImportFailure("Dosya 2 MB sınırını aşıyor.")
    if not raw:
        raise ImportFailure("Dosya boş.")
    return raw


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    index = 0
    for letter in letters.group(0) if letters else "A":
        index = index * 26 + (ord(letter) - 64)
    return index - 1


def _read_xlsx(raw: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as book:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in book.namelist():
                root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
                shared = ["".join(node.text or "" for node in item.iter(f"{{{_NS['m']}}}t")) for item in root.findall("m:si", _NS)]
            sheets = sorted(name for name in book.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))
            if not sheets:
                raise ImportFailure("Excel dosyasında çalışma sayfası bulunamadı.")
            root = ElementTree.fromstring(book.read(sheets[0]))
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError):
        raise ImportFailure("Excel dosyası okunamadı. Dosyayı CSV olarak kaydedip yeniden deneyin.") from None
    rows: list[list[str]] = []
    for row in root.iter(f"{{{_NS['m']}}}row"):
        values: dict[int, str] = {}
        for cell in row.findall("m:c", _NS):
            kind = cell.get("t")
            value = cell.find("m:v", _NS)
            if kind == "inlineStr":
                text = "".join(node.text or "" for node in cell.iter(f"{{{_NS['m']}}}t"))
            elif value is None or value.text is None:
                text = ""
            elif kind == "s":
                text = shared[int(value.text)] if int(value.text) < len(shared) else ""
            else:
                text = value.text
                if re.fullmatch(r"-?\d+\.0", text):
                    text = text[:-2]
            values[_column_index(cell.get("r", "A1"))] = text.strip()
        if values:
            rows.append([values.get(index, "") for index in range(max(values) + 1)])
    return rows


def _read_csv(raw: bytes) -> list[list[str]]:
    for encoding in ("utf-8-sig", "cp1254"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportFailure("Dosyanın karakter kodlaması okunamadı. UTF-8 olarak kaydedin.")
    sample = text[:4096]
    delimiter = max((";", ",", "\t"), key=sample.count)
    return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def read_rows(filename: str, content: str) -> list[list[str]]:
    raw = _decode(content)
    rows = _read_xlsx(raw) if filename.lower().endswith(".xlsx") or raw[:2] == b"PK" else _read_csv(raw)
    rows = [row for row in rows if any(cell for cell in row)]
    if len(rows) < 2:
        raise ImportFailure("Dosyada başlık satırı ve en az bir kayıt olmalı.")
    if len(rows) - 1 > MAX_ROWS:
        raise ImportFailure(f"Bir seferde en çok {MAX_ROWS} satır aktarılabilir.")
    return rows


def _suggest(headers: list[str]) -> ImportMapping:
    folded = [header.strip().lower().replace("İ", "i") for header in headers]
    chosen: dict[str, int | None] = {}
    used: set[int] = set()
    for field in FIELDS:
        match = next((index for index, header in enumerate(folded) if index not in used and any(hint == header or hint in header.split() for hint in HINTS[field])), None)
        if match is None:
            match = next((index for index, header in enumerate(folded) if index not in used and any(hint in header for hint in HINTS[field])), None)
        chosen[field] = match
        if match is not None:
            used.add(match)
    return ImportMapping(**chosen)


def preview(filename: str, content: str) -> ImportPreview:
    rows = read_rows(filename, content)
    headers = rows[0]
    width = max(len(row) for row in rows)
    headers = headers + [f"Sütun {index + 1}" for index in range(len(headers), width)]
    return ImportPreview(headers=headers, sample=[row + [""] * (width - len(row)) for row in rows[1:6]], total_rows=len(rows) - 1, mapping=_suggest(headers))


def run_import(db: Session, member: Member, filename: str, content: str, mapping: ImportMapping, *, dry_run: bool) -> ImportReport:
    if mapping.name is None:
        raise ImportFailure("Müşteri adının hangi sütunda olduğunu seçin.")
    rows = read_rows(filename, content)[1:]
    existing = db.scalars(select(Customer).where(Customer.company_id == member.company.id, Customer.deleted_at.is_(None))).all()
    by_email = {customer.email.lower(): customer for customer in existing if customer.email}
    by_phone = {key: customer for customer in existing if (key := phone_key(customer.phone))}
    by_name = {normalize_name(customer.name): customer for customer in existing}
    seen: dict[str, int] = {}
    report = ImportReport(total=len(rows), dry_run=dry_run)
    accepted: list[CustomerInput] = []

    def cell(row: list[str], index: int | None) -> str | None:
        return row[index] if index is not None and index < len(row) else None

    for number, row in enumerate(rows, start=2):
        try:
            data = CustomerInput(name=cell(row, mapping.name) or "", email=cell(row, mapping.email), phone=cell(row, mapping.phone), note=cell(row, mapping.note))
        except ValidationError as error:
            first = error.errors()[0]
            field = {"name": "Ad", "email": "E-posta", "phone": "Telefon", "note": "Not"}.get(str(first["loc"][0]), str(first["loc"][0]))
            message = "Geçerli bir e-posta adresi girin." if field == "E-posta" else str(first["msg"]).removeprefix("Value error, ")
            report.errors.append(ImportError_(row=number, message=f"{field}: {message}"))
            continue
        match = None
        reason = ""
        if data.email and data.email in by_email:
            match, reason = by_email[data.email], "aynı e-posta"
        elif (key := phone_key(data.phone)) and key in by_phone:
            match, reason = by_phone[key], "aynı telefon"
        elif normalize_name(data.name) in by_name:
            match, reason = by_name[normalize_name(data.name)], "aynı ad"
        if match is not None:
            report.duplicates.append(ImportDuplicate(row=number, name=data.name, reason=reason, existing_id=match.id, existing_name=match.name))
            continue
        keys = [f"e:{data.email}" if data.email else None, f"p:{phone_key(data.phone)}" if phone_key(data.phone) else None, f"n:{normalize_name(data.name)}"]
        repeated = next((seen[key] for key in keys if key and key in seen), None)
        if repeated is not None:
            report.duplicates.append(ImportDuplicate(row=number, name=data.name, reason=f"dosyada {repeated}. satırla aynı", existing_id=None, existing_name=None))
            continue
        for key in keys:
            if key:
                seen[key] = number
        accepted.append(data)

    report.valid = len(accepted)
    if dry_run or not accepted:
        return report
    for data in accepted:
        customer = Customer(id=uuid.uuid4(), company_id=member.company.id, name=data.name, email=data.email, phone=data.phone, note=data.note, created_by=member.user.id)
        db.add(customer)
        emit(db, member, "customer.created", {"id": str(customer.id), "name": customer.name, "email": customer.email, "phone": customer.phone})
    db.add(
        AuditLog(
            company_id=member.company.id,
            actor_user_id=member.user.id,
            action="customer.imported",
            entity_type="customer",
            entity_id=None,
            summary={"created": len(accepted), "duplicates": len(report.duplicates), "errors": len(report.errors), "file": filename[:120]},
            source="api",
        )
    )
    db.commit()
    report.created = len(accepted)
    return report
