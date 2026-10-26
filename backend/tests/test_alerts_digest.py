from datetime import datetime, timedelta
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_auth import csrf
from test_inventory import add_product, move
from test_mail import TEST_DSN, mail_on  # noqa: F401
from test_modules import sign_in_new_company
from test_team import accept, invite

from app.core.database import get_sessionmaker
from app.models.identity import Company, CompanyMembership, User
from app.services.digest import send_digests


def workspace(client, name: str, modules: list[str]) -> str:
    email = sign_in_new_company(client, name)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": modules}).status_code == 200
    return email


def inventory_titles(client) -> list[str]:
    return [item["title"] for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "inventory"]


def queued(to: str, kind: str) -> list[tuple]:
    with psycopg.connect(TEST_DSN) as connection:
        return connection.execute("SELECT subject, body_text FROM email_messages WHERE to_email = %s AND kind = %s ORDER BY created_at", (to, kind)).fetchall()


def test_stock_levels_alert_managers_and_queue_email(client, mail_on) -> None:  # noqa: F811
    owner = workspace(client, "Uyarı Atölyesi", ["inventory"])
    assert add_product(client, name="Hatalı", min_stock="5", initial_stock="10").get("critical_stock") is None
    bad = client.post(
        "/api/v1/inventory/products",
        headers=csrf(client),
        json={"sku": f"S-{uuid4().hex[:6]}", "name": "Ters Eşik", "unit": "adet", "min_stock": "5", "critical_stock": "8"},
    )
    assert bad.status_code == 422 and bad.json()["detail"] == "Kritik stok, minimum stoktan büyük olamaz."

    admin_email = f"yonetici-{uuid4().hex[:8]}@example.com"
    created = invite(client, admin_email, role="admin").json()
    from app.main import create_app

    with TestClient(create_app()) as admin:
        assert accept(admin, created["invite_path"]).status_code == 201

        plank = add_product(client, name="Kontrplak", min_stock="10", critical_stock="3", initial_stock="20")
        assert plank["critical_level"] == "3" and plank["critical"] is False
        low = move(client, plank["id"], "out", "12").json()["product"]
        assert low["low"] is True and low["critical"] is False
        assert inventory_titles(client) == ["Kontrplak minimum stok seviyesinin altına düştü."]
        assert inventory_titles(admin) == ["Kontrplak minimum stok seviyesinin altına düştü."]

        critical = move(client, plank["id"], "out", "6").json()["product"]
        assert critical["critical"] is True
        assert inventory_titles(admin)[0] == "Kontrplak kritik seviyeye indi."
        assert client.get("/api/v1/inventory/summary").json()["critical"] == 1

    assert [subject for subject, _ in queued(owner, "notification") if subject.startswith("Kontrplak")] == [
        "Kontrplak minimum stok seviyesinin altına düştü. · Uyarı Atölyesi",
        "Kontrplak kritik seviyeye indi. · Uyarı Atölyesi",
    ]
    assert len([subject for subject, _ in queued(admin_email, "notification") if subject.startswith("Kontrplak")]) == 2

    glue = add_product(client, name="Tutkal", min_stock="8", initial_stock="9")
    assert glue["critical_level"] == "4"
    move(client, glue["id"], "out", "6")
    assert inventory_titles(client)[0] == "Tutkal kritik seviyeye indi."


def members_of(db, name: str) -> tuple[Company, list[tuple[User, str]]]:
    company = db.scalar(select(Company).where(Company.name == name).order_by(Company.created_at.desc()))
    rows = db.execute(
        select(User, CompanyMembership.role).join(CompanyMembership, CompanyMembership.user_id == User.id).where(CompanyMembership.company_id == company.id)
    ).all()
    return company, [(user, role) for user, role in rows]


def test_weekly_digest_is_sent_once_on_monday_morning(client, mail_on) -> None:  # noqa: F811
    name = f"Özet Atölyesi {uuid4().hex[:6]}"
    owner = workspace(client, name, ["tasks", "inventory", "finance"])
    me = client.get("/api/v1/auth/me").json()["id"]
    now = datetime.now()
    monday = (now - timedelta(days=now.weekday())).replace(hour=9, minute=30, second=0, microsecond=0)
    late = (monday.date() - timedelta(days=2)).isoformat()
    client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Tedarikçiyi ara", "assignee_id": me, "due_date": late})
    add_product(client, name="Cila", unit="lt", min_stock="4", initial_stock="1")
    client.post(
        "/api/v1/finance/records",
        headers=csrf(client),
        json={"kind": "income", "category": "Satış", "description": "Eski fatura", "amount": "1500", "currency": "TRY", "record_date": late, "due_date": late, "status": "pending"},
    )

    with get_sessionmaker()() as db:
        company, members = members_of(db, name)
        assert send_digests(db, company, members, now=monday.replace(hour=8, minute=59)) == 0
        assert send_digests(db, company, members, now=monday + timedelta(days=1)) == 0
        assert send_digests(db, company, members, now=monday) == 1
        db.commit()
        assert send_digests(db, company, members, now=monday + timedelta(hours=3)) == 0

    [(subject, text)] = queued(owner, "digest")
    assert subject.startswith(f"Haftalık özet · {name} · ")
    assert "1 geciken görev: Tedarikçiyi ara" in text
    assert "GÖREVLERİNİZ" in text and "FİNANS" in text
    assert "Cila (1 lt, kritik 2)" in text
    assert "Vadesi geçen 1 alacak: ₺1.500,00." in text

    client.put("/api/v1/notifications/preferences", headers=csrf(client), json={"email": {"digest": False}})
    with get_sessionmaker()() as db:
        company, members = members_of(db, name)
        assert send_digests(db, company, members, now=monday + timedelta(days=7)) == 0
