from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import AuditLog, Company
from app.models.modules import CompanyModule
from app.modules.catalog import CATALOG, MODULES, ModuleDefinition, with_requirements
from app.schemas.modules import ModuleItem, ModuleListResponse
from app.services.auth import Member
from app.services.notifications import notify
from app.services.permissions import MANAGERS, level_for, member_levels


class ModuleError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def list_modules(db: Session, member: Member) -> ModuleListResponse:
    """Company modules as the signed-in person sees them: a member's ungranted modules come back disabled."""
    rows = _rows(db, member)
    levels = member_levels(db, member)
    items = []
    for module in CATALOG:
        item = _item(module, rows.get(module.key))
        item.company_enabled = item.enabled
        item.access = levels.get(module.key) if item.enabled else None  # type: ignore[assignment]
        if item.access is None:
            item.enabled = False
            item.enabled_at = None
        items.append(item)
    return ModuleListResponse(modules=items)


def module_access(db: Session, member: Member, key: str, *, write: bool = False) -> ModuleItem:
    module = MODULES.get(key)
    if module is None:
        raise ModuleError(404, "Modül bulunamadı.")
    if member.company.setup_completed_at is None:
        raise ModuleError(403, "Önce çalışma alanı kurulumunu tamamlayın.")
    row = _rows(db, member).get(key)
    if not _is_enabled(row):
        raise ModuleError(403, "Bu modül çalışma alanınızda açık değil.")
    level = level_for(db, member, key)
    if level is None:
        raise ModuleError(403, f"{module.name} modülüne erişim yetkiniz yok. Çalışma alanı yöneticinizden yetki isteyebilirsiniz.")
    if write and level != "edit":
        raise ModuleError(403, f"{module.name} modülünde yalnızca görüntüleme yetkiniz var.")
    item = _item(module, row)
    item.company_enabled = True
    item.access = level  # type: ignore[assignment]
    return item


def visible_keys(db: Session, member: Member) -> set[str]:
    """Enabled modules the person may at least view. Business rules keep using enabled_keys."""
    enabled = enabled_keys(db, member)
    if member.role in MANAGERS:
        return enabled
    return enabled & set(member_levels(db, member))


def can_edit(db: Session, member: Member, key: str) -> bool:
    return key in enabled_keys(db, member) and level_for(db, member, key) == "edit"


def complete_setup(db: Session, member: Member, keys: list[str]) -> ModuleListResponse:
    target = _target(member, keys)
    company = _lock_company(db, member)
    if company.setup_completed_at is not None:
        raise ModuleError(409, "Çalışma alanı kurulumu zaten tamamlandı.")

    added, _ = _apply(db, member, target)
    company.setup_completed_at = datetime.now(UTC)
    company.updated_at = company.setup_completed_at
    notify(
        db,
        member,
        category="workspace",
        title="Çalışma alanınız hazır.",
        body=f"{len(added)} modül açıldı. Modül tercihlerinizi profilinizden değiştirebilirsiniz.",
        link="/panel/profil",
        dedupe_key="workspace.setup_completed",
    )
    db.commit()
    return list_modules(db, member)


def update_selection(db: Session, member: Member, keys: list[str]) -> ModuleListResponse:
    if member.role not in {"owner", "admin"}:
        raise ModuleError(403, "Modül tercihlerini yalnızca sahip veya yönetici değiştirebilir.")
    target = _target(member, keys)
    company = _lock_company(db, member)
    if company.setup_completed_at is None:
        raise ModuleError(409, "Önce çalışma alanı kurulumunu tamamlayın.")

    added, removed = _apply(db, member, target)
    if added or removed:
        parts = []
        if added:
            parts.append(f"Eklenen: {_join(MODULES[key].name for key in added)}.")
        if removed:
            kept = "Bu modülün verileri silinmedi." if len(removed) == 1 else "Bu modüllerin verileri silinmedi."
            parts.append(f"Kaldırılan: {_join(MODULES[key].name for key in removed)}. {kept}")
        notify(
            db,
            member,
            category="modules",
            title="Modül tercihleriniz güncellendi.",
            body=" ".join(parts),
            link="/panel/profil",
        )
        db.commit()
    return list_modules(db, member)


def _target(member: Member, keys: list[str]) -> set[str]:
    if member.role != "owner":
        raise ModuleError(403, "Modülleri yalnızca şirket sahibi değiştirebilir.")
    if any(key not in MODULES for key in keys):
        raise ModuleError(422, "Bilinmeyen bir modül seçildi.")
    if not keys:
        raise ModuleError(422, "En az bir modül seçin.")
    return with_requirements(set(keys))


def _apply(db: Session, member: Member, target: set[str]) -> tuple[list[str], list[str]]:
    rows = _rows(db, member)
    enabled = {key for key, row in rows.items() if _is_enabled(row)}
    order = [module.key for module in CATALOG]
    added = [key for key in order if key in target and key not in enabled]
    removed = [key for key in order if key in enabled and key not in target]
    now = datetime.now(UTC)

    for key in added:
        row = rows.get(key)
        if row is None:
            db.add(CompanyModule(company_id=member.company.id, module_key=key, status="enabled", enabled_at=now))
        else:
            row.status = "enabled"
            row.enabled_at = now
            row.disabled_at = None
            row.updated_at = now
        db.add(_audit(member, "module.enabled", key))

    for key in removed:
        row = rows[key]
        row.status = "disabled"
        row.disabled_at = now
        row.updated_at = now
        db.add(_audit(member, "module.disabled", key))

    return added, removed


def enabled_keys(db: Session, member: Member) -> set[str]:
    return {key for key, row in _rows(db, member).items() if _is_enabled(row)}


def _lock_company(db: Session, member: Member) -> Company:
    company = db.scalar(select(Company).where(Company.id == member.company.id).with_for_update().execution_options(populate_existing=True))
    if company is None:
        raise ModuleError(404, "Çalışma alanı bulunamadı.")
    return company


def _rows(db: Session, member: Member) -> dict[str, CompanyModule]:
    rows = db.scalars(select(CompanyModule).where(CompanyModule.company_id == member.company.id))
    return {row.module_key: row for row in rows}


def _is_enabled(row: CompanyModule | None) -> bool:
    return row is not None and row.status == "enabled"


def _item(module: ModuleDefinition, row: CompanyModule | None) -> ModuleItem:
    enabled = _is_enabled(row)
    return ModuleItem(
        key=module.key,
        name=module.name,
        summary=module.summary,
        requires=list(module.requires),
        enabled=enabled,
        enabled_at=row.enabled_at if enabled and row is not None else None,
    )


def _audit(member: Member, action: str, key: str) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="company_module",
        entity_id=key,
        summary={"module": key},
        source="api",
    )


def _join(names: Iterable[str]) -> str:
    return ", ".join(names)
