"""Duplicate detection for customers.

A match is reported when the email is the same, the phone numbers end in the same
ten digits, or the names are the same after removing case, punctuation and common
company suffixes. Close but different names are reported as "benzer ad".
"""

import re
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer

_SUFFIXES = {
    "ltd", "şti", "sti", "ltd.şti", "a.ş", "aş", "as", "a.s", "san", "tic", "ve", "inş", "ins", "limited", "şirketi", "sirketi",
    "anonim", "ticaret", "sanayi", "co", "inc", "llc", "gmbh",
}
_FOLD = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})
SIMILAR = 0.88


def normalize_name(name: str) -> str:
    lowered = name.replace("I", "ı").replace("İ", "i").lower()
    tokens = [token.strip(".") for token in re.split(r"[\s,;/()\-]+", lowered) if token.strip(".")]
    kept = [token for token in tokens if token not in _SUFFIXES]
    return " ".join(kept or tokens).translate(_FOLD)


def phone_key(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 7 else None


@dataclass(frozen=True)
class Candidate:
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    reason: str


def _reason(name: str, email: str | None, phone: str | None, other: Customer) -> str | None:
    if email and other.email and other.email.lower() == email.lower():
        return "aynı e-posta"
    key = phone_key(phone)
    if key and phone_key(other.phone) == key:
        return "aynı telefon"
    left, right = normalize_name(name), normalize_name(other.name)
    if not left or not right:
        return None
    if left == right:
        return "aynı ad"
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) >= 5 and longer.startswith(shorter + " "):
        return "benzer ad"
    if len(left) >= 4 and len(right) >= 4 and SequenceMatcher(None, left, right).ratio() >= SIMILAR:
        return "benzer ad"
    return None


def find_matches(
    db: Session,
    company_id: uuid.UUID,
    *,
    name: str,
    email: str | None,
    phone: str | None,
    exclude: uuid.UUID | None = None,
    limit: int = 5,
) -> list[Candidate]:
    normalized = normalize_name(name)
    tokens = [token for token in normalized.split() if len(token) >= 3]
    conditions = []
    if email:
        conditions.append(func.lower(Customer.email) == email.lower())
    key = phone_key(phone)
    if key:
        conditions.append(func.right(func.regexp_replace(Customer.phone, r"\D", "", "g"), 10) == key)
    for token in tokens[:3]:
        conditions.append(func.translate(func.lower(Customer.name), "ıişğüöç", "iisguoc").contains(token[:4]))
    if not conditions:
        return []
    statement = select(Customer).where(Customer.company_id == company_id, Customer.deleted_at.is_(None), or_(*conditions)).limit(200)
    if exclude is not None:
        statement = statement.where(Customer.id != exclude)
    found: list[Candidate] = []
    order = {"aynı e-posta": 0, "aynı telefon": 1, "aynı ad": 2, "benzer ad": 3}
    for other in db.scalars(statement):
        reason = _reason(name, email, phone, other)
        if reason:
            found.append(Candidate(id=other.id, name=other.name, email=other.email, phone=other.phone, reason=reason))
    found.sort(key=lambda item: order[item.reason])
    return found[:limit]
