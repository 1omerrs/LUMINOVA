"""Readable company activity built from audit_logs."""

import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.identity import AuditLog, User
from app.models.team import CompanyInvitation
from app.modules.catalog import MODULES
from app.modules.customers.models import Customer
from app.modules.finance.models import FinancialRecord
from app.modules.inventory.models import Product
from app.modules.inventory.service import quantity_label
from app.modules.production.service import production_code
from app.modules.projects.models import Project
from app.modules.quotes.service import quote_code
from app.modules.sales.service import STATUS_LABELS as ORDER_STATUS
from app.modules.sales.service import order_code
from app.modules.tasks.models import Task
from app.services.auth import Member
from app.services.modules import visible_keys
from app.services.permissions import describe as describe_levels
from app.services.support import ticket_code
from app.services.team import ROLE_LABELS


class ActivityError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


PAGE_SIZE = 30
PREFIXES: dict[str, str] = {
    "customer": "customers",
    "quote": "customers",
    "product": "inventory",
    "stock": "inventory",
    "order": "sales",
    "sales": "sales",
    "production": "production",
    "task": "tasks",
    "project": "projects",
    "finance": "finance",
    "account": "workspace",
    "workspace": "workspace",
    "module": "workspace",
    "team": "workspace",
    "support": "workspace",
    "automation": "workspace",
}
MANAGER_PREFIXES = {"team", "support", "automation"}
LINKS: dict[str, str] = {
    "customer": "/panel/musteriler",
    "quote": "/panel/musteriler?bolum=teklifler",
    "product": "/panel/stok",
    "stock": "/panel/stok",
    "order": "/panel/satis",
    "production": "/panel/uretim",
    "task": "/panel/gorevler",
    "project": "/panel/projeler",
    "finance": "/panel/finans",
    "team": "/panel/profil#ekip",
    "module": "/panel/profil#moduller",
    "support": "/panel/destek",
    "automation": "/panel/otomasyon",
}
VERBS: dict[str, str] = {
    "account.registered": "çalışma alanını oluşturdu",
    "workspace.exported": "çalışma alanı verilerini indirdi",
    "workspace.closure_requested": "çalışma alanı için kapatma talebi açtı",
    "workspace.closure_cancelled": "kapatma talebini iptal etti",
    "account.closed": "hesabını kapattı",
    "account.data_exported": "kişisel verilerini indirdi",
    "module.enabled": "modül açtı",
    "module.disabled": "modül kapattı",
    "team.invited": "davet oluşturdu",
    "team.invitation_revoked": "daveti iptal etti",
    "team.invitation_accepted": "ekibe katıldı",
    "team.role_changed": "rol değiştirdi",
    "team.permissions_changed": "modül yetkilerini güncelledi",
    "team.join_requested": "katılım kodu ile ekibe katılmak istedi",
    "team.join_approved": "katılım isteğini onayladı",
    "team.join_rejected": "katılım isteğini reddetti",
    "team.join_code_renewed": "katılım kodunu yeniledi",
    "team.member_removed": "ekipten çıkardı",
    "customer.created": "müşteri ekledi",
    "customer.updated": "müşteriyi güncelledi",
    "customer.deleted": "müşteriyi sildi",
    "customer.imported": "müşteri listesi aktardı",
    "quote.created": "teklif hazırladı",
    "quote.updated": "teklifi güncelledi",
    "quote.sent": "teklifi gönderdi",
    "quote.resent": "teklif bağlantısını yeniledi",
    "quote.accepted": "teklifi kabul edildi olarak işaretledi",
    "quote.rejected": "teklifi reddedildi olarak işaretledi",
    "quote.accepted_by_customer": "teklifi kabul etti",
    "quote.rejected_by_customer": "teklifi reddetti",
    "quote.converted": "teklifi siparişe dönüştürdü",
    "product.created": "ürün ekledi",
    "product.updated": "ürünü güncelledi",
    "product.deleted": "ürünü sildi",
    "stock.movement_recorded": "stok hareketi kaydetti",
    "order.created": "sipariş oluşturdu",
    "order.updated": "siparişi güncelledi",
    "order.status_changed": "sipariş durumunu değiştirdi",
    "order.rules_applied": "satış kuralını uyguladı",
    "sales.rules_updated": "satış kurallarını güncelledi",
    "production.created": "iş emri oluşturdu",
    "production.updated": "iş emrini güncelledi",
    "production.started": "üretimi başlattı",
    "production.completed": "üretimi tamamladı",
    "production.cancelled": "iş emrini iptal etti",
    "production.recipe_saved": "ürün reçetesini kaydetti",
    "production.recipe_removed": "ürün reçetesini kaldırdı",
    "task.created": "görev ekledi",
    "task.updated": "görevi güncelledi",
    "task.status_changed": "görev durumunu değiştirdi",
    "task.deleted": "görevi sildi",
    "task.unblocked": "sırası gelen görevi açtı",
    "task.auto_created": "otomatik görev açtı",
    "task.auto_resolved": "görevi kendiliğinden kapattı",
    "task.auto_assigned": "görevi otomatik atadı",
    "task.dependencies_changed": "görev bağımlılıklarını güncelledi",
    "task.template_created": "görev şablonu oluşturdu",
    "task.template_updated": "görev şablonunu güncelledi",
    "task.template_deleted": "görev şablonunu sildi",
    "task.template_applied": "görev şablonunu uyguladı",
    "project.created": "proje oluşturdu",
    "project.updated": "projeyi güncelledi",
    "project.deleted": "projeyi sildi",
    "project.milestone_added": "projeye aşama ekledi",
    "project.milestone_updated": "proje aşamasını güncelledi",
    "project.milestone_completed": "proje aşamasını tamamladı",
    "project.milestone_reopened": "proje aşamasını yeniden açtı",
    "project.milestone_removed": "proje aşamasını kaldırdı",
    "project.template_created": "proje şablonu oluşturdu",
    "project.template_updated": "proje şablonunu güncelledi",
    "project.template_deleted": "proje şablonunu sildi",
    "project.template_applied": "projeyi şablondan kurdu",
    "project.rescheduled": "proje takvimini yeniden hesapladı",
    "finance.record_updated": "finans kaydını güncelledi",
    "finance.record_cancelled": "finans kaydını iptal etti",
    "finance.payment_added": "ödeme kaydetti",
    "finance.payment_removed": "ödemeyi geri aldı",
    "finance.opening_balance_set": "kasa açılış bakiyesini girdi",
    "support.ticket_created": "destek talebi açtı",
    "support.message_added": "destek talebine yazdı",
    "support.ticket_closed": "destek talebini kapattı",
    "automation.endpoint_created": "otomasyon bağlantısı ekledi",
    "automation.endpoint_updated": "otomasyon bağlantısını güncelledi",
    "automation.endpoint_deleted": "otomasyon bağlantısını sildi",
    "automation.secret_rotated": "bağlantı anahtarını yeniledi",
}
CODES = {"order": order_code, "quote": quote_code, "production": production_code, "support": ticket_code}
TASK_STATUS = {"todo": "yapılacak", "in_progress": "sürüyor", "done": "tamamlandı"}
MOVEMENT_LABELS = {"in": "Giriş", "out": "Çıkış", "adjustment": "Sayım düzeltmesi"}
MEMBER_TEAM_ACTIONS = ("team.invitation_accepted",)
DELETING = (".deleted",)


def _cursor(entry: AuditLog) -> str:
    return f"{entry.created_at.isoformat()}_{entry.id}"


def _parse_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        moment, _, identifier = value.rpartition("_")
        return datetime.fromisoformat(moment), uuid.UUID(identifier)
    except ValueError:
        raise ActivityError(422, "Sayfa bilgisi okunamadı.") from None


def _name(user: User | None) -> str:
    return f"{user.first_name} {user.last_name}".strip() if user else "Sistem"


def visible_prefixes(db: Session, member: Member) -> list[str]:
    enabled = visible_keys(db, member) | {"workspace"}
    return [prefix for prefix, module in PREFIXES.items() if module in enabled]


def list_activity(
    db: Session,
    member: Member,
    *,
    module: str | None = None,
    actor: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = PAGE_SIZE,
) -> tuple[list[dict[str, object]], str | None, list[dict[str, object]]]:
    prefixes = visible_prefixes(db, member)
    if module is not None:
        if module not in set(PREFIXES.values()):
            raise ActivityError(422, "Bilinmeyen modül filtresi.")
        prefixes = [prefix for prefix in prefixes if PREFIXES[prefix] == module]
    scope = [AuditLog.company_id == member.company.id]
    manager = member.role in {"owner", "admin"}
    conditions = [AuditLog.action.like(f"{prefix}.%") for prefix in prefixes if prefix not in MANAGER_PREFIXES or (manager and prefix != "team")]
    if "team" in prefixes:
        conditions.append(AuditLog.action.like("team.%") if manager else AuditLog.action.in_(MEMBER_TEAM_ACTIONS))
    if not conditions:
        return [], None, []
    scope.append(or_(*conditions))
    actors = [
        {"id": user.id, "name": _name(user)}
        for user in db.scalars(
            select(User).where(User.id.in_(select(AuditLog.actor_user_id).where(*scope).distinct())).order_by(User.first_name, User.last_name)
        )
    ]
    query = select(AuditLog).where(*scope)
    if actor is not None:
        query = query.where(AuditLog.actor_user_id == actor)
    if cursor:
        moment, identifier = _parse_cursor(cursor)
        query = query.where(or_(AuditLog.created_at < moment, and_(AuditLog.created_at == moment, AuditLog.id < identifier)))
    rows = db.scalars(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return [_describe(entry, labels) for entry, labels in _with_labels(db, member, rows)], (_cursor(rows[-1]) if more else None), actors


def _ids(rows: list[AuditLog], *prefixes: str) -> list[uuid.UUID]:
    found = []
    for entry in rows:
        if entry.action.split(".")[0] in prefixes and entry.entity_id:
            try:
                found.append(uuid.UUID(entry.entity_id))
            except ValueError:
                continue
    return found


def _with_labels(db: Session, member: Member, rows: list[AuditLog]) -> list[tuple[AuditLog, dict[str, object]]]:
    company = member.company.id
    lookups: dict[str, dict[str, object]] = defaultdict(dict)
    sources = (
        ("customer", Customer, Customer.name),
        ("task", Task, Task.title),
        ("project", Project, Project.name),
    )
    for prefix, model, column in sources:
        ids = _ids(rows, prefix)
        if ids:
            for identifier, label in db.execute(select(model.id, column).where(model.company_id == company, model.id.in_(ids))):
                lookups[prefix][str(identifier)] = label
    finance_ids = _ids(rows, "finance")
    if finance_ids:
        for record in db.scalars(select(FinancialRecord).where(FinancialRecord.company_id == company, FinancialRecord.id.in_(finance_ids))):
            lookups["finance"][str(record.id)] = record
    product_ids = _ids(rows, "product", "stock")
    if product_ids:
        for product in db.scalars(select(Product).where(Product.company_id == company, Product.id.in_(product_ids))):
            lookups["product"][str(product.id)] = product
    team_ids = _ids(rows, "team")
    if team_ids:
        for invitation in db.scalars(select(CompanyInvitation).where(CompanyInvitation.company_id == company, CompanyInvitation.id.in_(team_ids))):
            lookups["invitation"][str(invitation.id)] = invitation.email
    user_ids = {entry.actor_user_id for entry in rows if entry.actor_user_id} | set(team_ids)
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    lookups["user"] = {str(identifier): user for identifier, user in users.items()}
    return [(entry, lookups) for entry in rows]


def _title(label: str) -> str:
    head = {"i": "İ", "ı": "I"}.get(label[:1], label[:1].upper())
    return head + label[1:]


def _quantity(value: object) -> str | None:
    try:
        return quantity_label(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _describe(entry: AuditLog, lookups: dict[str, dict[str, object]]) -> dict[str, object]:
    prefix = entry.action.split(".")[0]
    summary = entry.summary or {}
    key = entry.entity_id or ""
    users = lookups["user"]
    actor = users.get(str(entry.actor_user_id)) if entry.actor_user_id else None
    if entry.source == "customer":
        actor_name = str(summary.get("customer") or "Müşteri")
    else:
        actor_name = "Otomasyon" if entry.source == "webhook" else "LUMINOVA" if entry.source == "automation" else _name(actor)  # type: ignore[arg-type]
    verb = VERBS.get(entry.action, "bir işlem yaptı")
    target: str | None = None
    detail: str | None = None

    if entry.action.startswith("production.recipe_"):
        target = str(summary.get("name") or "") or None
        if entry.action == "production.recipe_saved":
            detail = f"{summary.get('materials', 0)} malzeme"
    elif prefix in {"order", "quote", "production", "support"}:
        number = summary.get("number")
        target = CODES[prefix](number) if isinstance(number, int) else None
        if entry.action == "production.created" and summary.get("auto"):
            detail = "Satış kuralıyla otomatik açıldı"
    elif entry.action.startswith("task.template_") or (entry.action.startswith("project.template_") and entry.action != "project.template_applied"):
        target = str(summary.get("name") or "") or None
        if entry.action == "task.template_applied":
            detail = f"{summary.get('tasks', 0)} görev oluşturuldu"
    elif prefix in {"customer", "task", "project"}:
        target = lookups[prefix].get(key)  # type: ignore[assignment]
        if entry.action in {"task.auto_created", "task.auto_resolved", "task.auto_assigned"} and summary.get("reason"):
            detail = str(summary["reason"])[:240]
        if entry.action == "task.unblocked" and summary.get("after"):
            detail = f"“{summary['after']}” tamamlandı"
    elif prefix == "finance":
        record = lookups["finance"].get(key)
        target = record.description if isinstance(record, FinancialRecord) else None
        if entry.action == "finance.opening_balance_set" and summary.get("amount"):
            amount = str(summary["amount"]).replace(".", ",")
            detail = f"{amount} {summary.get('currency', '')} · {summary.get('as_of', '')} itibarıyla"
        elif entry.action == "finance.record_created":
            kind = summary.get("kind") or (record.kind if isinstance(record, FinancialRecord) else None)
            verb = "gelir kaydı ekledi" if kind == "income" else "gider kaydı ekledi"
        elif entry.action in {"finance.payment_added", "finance.payment_removed"} and summary.get("amount"):
            income = isinstance(record, FinancialRecord) and record.kind == "income"
            if entry.action == "finance.payment_added":
                verb = "tahsilat kaydetti" if income else "ödeme kaydetti"
            amount = str(summary["amount"]).replace(".", ",")
            detail = f"{amount} {summary.get('currency', '')}" + (" · kayıt tamamen kapandı" if summary.get("status") == "paid" else "")
    elif prefix in {"product", "stock"}:
        product = lookups["product"].get(key)
        target = product.name if isinstance(product, Product) else None
        if entry.action == "stock.movement_recorded":
            unit = product.unit if isinstance(product, Product) else ""
            amount = _quantity(str(summary.get("quantity", "")).lstrip("-"))
            balance = _quantity(summary.get("balance_after"))
            kind = MOVEMENT_LABELS.get(str(summary.get("kind")), "Hareket")
            if amount and balance:
                detail = f"{kind} {amount} {unit}, kalan {balance} {unit}".replace("  ", " ").strip()
    elif prefix == "automation":
        target = str(summary.get("name") or "") or None
    elif prefix == "module":
        module = MODULES.get(key)
        target = module.name if module else key
    elif prefix == "team":
        if entry.action in {"team.invited", "team.invitation_revoked"}:
            target = lookups["invitation"].get(key)  # type: ignore[assignment]
        elif entry.action != "team.invitation_accepted":
            target = _name(users.get(key)) if users.get(key) else None  # type: ignore[arg-type]
        if entry.action in {"team.join_requested", "team.join_code_renewed"}:
            target = None
        if entry.action in {"team.permissions_changed", "team.join_approved"} and isinstance(summary.get("permissions"), dict):
            detail = describe_levels(summary["permissions"])[:240]  # type: ignore[arg-type]
        elif entry.action == "team.role_changed":
            detail = f"{ROLE_LABELS.get(str(summary.get('from')), '')} → {ROLE_LABELS.get(str(summary.get('to')), '')}"
        elif entry.action in {"team.invited", "team.invitation_accepted"} and summary.get("role"):
            detail = f"Rol: {ROLE_LABELS.get(str(summary['role']), '')}"

    if entry.action in {"order.status_changed", "task.status_changed"}:
        labels = ORDER_STATUS if prefix == "order" else TASK_STATUS
        start, end = labels.get(str(summary.get("from")), ""), labels.get(str(summary.get("to")), "")
        if start and end:
            detail = f"{_title(start)} → {_title(end)}"
    elif entry.action == "quote.converted" and isinstance(summary.get("order"), int):
        detail = f"Sipariş {order_code(summary['order'])}"  # type: ignore[arg-type]
    elif entry.action.startswith("project.milestone_") and summary.get("milestone"):
        detail = f"Aşama: {summary['milestone']}" + (" · görevlerine göre otomatik" if summary.get("auto") else "")
    elif entry.action == "project.template_applied":
        detail = f"“{summary.get('name', '')}” şablonundan {summary.get('tasks', 0)} görev oluşturuldu"
    elif entry.action == "project.rescheduled":
        detail = f"{summary.get('count', 0)} görevin tarihi bağımlılıklara göre güncellendi"
    elif entry.action == "customer.imported":
        detail = f"{summary.get('created', 0)} müşteri eklendi, {summary.get('duplicates', 0)} mükerrer atlandı"
    elif entry.action == "order.rules_applied" and isinstance(summary.get("notes"), list):
        detail = " ".join(str(note) for note in summary["notes"])[:240]
    elif entry.action in {"quote.created", "order.created"} and summary.get("lines"):
        detail = f"{summary['lines']} kalem"
    elif entry.action in {"quote.sent", "quote.resent"} and summary.get("emailed"):
        detail = "Müşteriye e-postayla gönderildi"
    elif entry.action.endswith("_by_customer") and summary.get("note"):
        detail = f"“{str(summary['note'])[:200]}”"

    link = None if entry.action.endswith(DELETING) else LINKS.get(prefix)
    return {
        "id": entry.id,
        "module": PREFIXES.get(prefix, "workspace"),
        "action": entry.action,
        "actor_id": entry.actor_user_id,
        "actor_name": actor_name,
        "verb": verb,
        "target": target,
        "detail": detail,
        "link": link,
        "created_at": entry.created_at,
    }
