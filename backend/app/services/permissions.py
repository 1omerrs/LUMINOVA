"""Module permissions for members.

Owners and admins can do everything in every enabled module. A member sees only the
modules a manager granted, either read-only ('view') or with changes ('edit').
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.team import MemberPermission
from app.modules.catalog import CATALOG, MODULES
from app.services.auth import Member

LEVELS = ("view", "edit")
LEVEL_LABELS = {"view": "görüntüleme", "edit": "düzenleme"}
MANAGERS = {"owner", "admin"}
# Automation connections carry secrets and are managed by owners and admins only.
GRANTABLE = tuple(module.key for module in CATALOG if module.key != "automation")


class PermissionError_(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def member_levels(db: Session, member: Member) -> dict[str, str]:
    """Module key to level for the signed-in person; managers get 'edit' everywhere."""
    if member.role in MANAGERS:
        return {module.key: "edit" for module in CATALOG}
    return stored_levels(db, member.company.id, member.user.id)


def stored_levels(db: Session, company_id, user_id) -> dict[str, str]:  # type: ignore[no-untyped-def]
    rows = db.scalars(select(MemberPermission).where(MemberPermission.company_id == company_id, MemberPermission.user_id == user_id))
    return {row.module_key: row.level for row in rows}


def level_for(db: Session, member: Member, key: str) -> str | None:
    if member.role in MANAGERS:
        return "edit"
    row = db.get(MemberPermission, (member.company.id, member.user.id, key))
    return row.level if row else None


def normalize(grants: dict[str, str]) -> dict[str, str]:
    """Validates levels and adds read access to the modules a granted module depends on."""
    unknown = [key for key in grants if key not in GRANTABLE]
    if unknown:
        raise PermissionError_(422, f"Bu modül için yetki verilemez: {unknown[0]}")
    if any(level not in LEVELS for level in grants.values()):
        raise PermissionError_(422, "Yetki düzeyi görüntüleme veya düzenleme olmalı.")
    result = dict(grants)
    pending = list(grants)
    while pending:
        for required in MODULES[pending.pop()].requires:
            if required not in result:
                result[required] = "view"
                pending.append(required)
    return result


def replace_levels(db: Session, company_id, user_id, grants: dict[str, str]) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Stores the normalized grants for a member; the caller commits."""
    levels = normalize(grants)
    db.execute(delete(MemberPermission).where(MemberPermission.company_id == company_id, MemberPermission.user_id == user_id))
    for key, level in levels.items():
        db.add(MemberPermission(company_id=company_id, user_id=user_id, module_key=key, level=level))
    return levels


def describe(levels: dict[str, str]) -> str:
    parts = [f"{MODULES[key].name} ({LEVEL_LABELS[level]})" for key, level in sorted(levels.items(), key=lambda item: GRANTABLE.index(item[0]))]
    return ", ".join(parts) if parts else "hiçbir modül"
