from uuid import uuid4

import psycopg
from test_auth import account_payload, csrf

PASSWORD = "dogru-parola-1901"


def sign_in_new_company(client, company: str = "Modül Atölyesi") -> str:
    email = f"{uuid4().hex[:8]}@example.com"
    created = client.post("/api/v1/auth/register", headers=csrf(client), json=account_payload(email, company))
    token = created.json()["verification_path"].split("token=", 1)[1]
    assert client.post("/api/v1/auth/verify-email", headers=csrf(client), json={"token": token}).status_code == 200
    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": email, "password": PASSWORD}).status_code == 200
    return email


def enabled_keys(response) -> set[str]:
    return {item["key"] for item in response.json()["modules"] if item["enabled"]}


def test_modules_require_a_session(client) -> None:
    assert client.get("/api/v1/modules").status_code == 401
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["tasks"]}).status_code == 401
    assert client.get("/api/v1/notifications").status_code == 401


def test_new_company_must_finish_setup(client) -> None:
    sign_in_new_company(client)
    me = client.get("/api/v1/auth/me").json()
    assert me["setup_completed"] is False
    assert me["role"] == "owner"

    modules = client.get("/api/v1/modules").json()["modules"]
    assert [item["key"] for item in modules] == [
        "sales",
        "inventory",
        "production",
        "customers",
        "finance",
        "tasks",
        "projects",
        "reporting",
        "automation",
    ]
    assert modules[0]["name"] == "Satış ve Siparişler"
    assert not any(item["enabled"] for item in modules)

    blocked = client.get("/api/v1/modules/tasks")
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Önce çalışma alanı kurulumunu tamamlayın."

    early_change = client.put("/api/v1/modules", headers=csrf(client), json={"modules": ["tasks"]})
    assert early_change.status_code == 409


def test_setup_needs_a_choice_and_adds_requirements(client, database: str) -> None:
    sign_in_new_company(client)

    assert client.post("/api/v1/workspace/setup", json={"modules": ["sales"]}).status_code == 403
    empty = client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": []})
    assert empty.status_code == 422
    assert empty.json()["detail"] == "En az bir modül seçin."
    unknown = client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["payroll"]})
    assert unknown.status_code == 422

    done = client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["sales", "reporting"]})
    assert done.status_code == 200
    assert enabled_keys(done) == {"sales", "customers", "inventory", "reporting"}
    assert client.get("/api/v1/auth/me").json()["setup_completed"] is True

    again = client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["tasks"]})
    assert again.status_code == 409

    assert client.get("/api/v1/modules/sales").status_code == 200
    closed = client.get("/api/v1/modules/finance")
    assert closed.status_code == 403
    assert closed.json()["detail"] == "Bu modül çalışma alanınızda açık değil."
    assert client.get("/api/v1/modules/payroll").status_code == 404

    notifications = client.get("/api/v1/notifications").json()
    assert notifications["unread"] == 1
    assert notifications["items"][0]["title"] == "Çalışma alanınız hazır."
    assert notifications["items"][0]["body"].startswith("4 modül açıldı.")

    company_id = client.get("/api/v1/auth/me").json()["company_id"]
    with psycopg.connect(database) as connection:
        stored = connection.execute(
            "SELECT module_key FROM company_modules WHERE company_id = %s AND status = 'enabled' ORDER BY module_key",
            (company_id,),
        ).fetchall()
    assert [key for (key,) in stored] == ["customers", "inventory", "reporting", "sales"]


def test_profile_changes_keep_rows_and_notify(client, database: str) -> None:
    sign_in_new_company(client)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["sales"]}).status_code == 200

    kept = client.put("/api/v1/modules", headers=csrf(client), json={"modules": ["sales", "inventory"]})
    assert enabled_keys(kept) == {"sales", "customers", "inventory"}
    assert client.get("/api/v1/notifications").json()["unread"] == 1

    changed = client.put("/api/v1/modules", headers=csrf(client), json={"modules": ["tasks"]})
    assert changed.status_code == 200
    assert enabled_keys(changed) == {"tasks"}
    assert client.get("/api/v1/modules/sales").status_code == 403

    feed = client.get("/api/v1/notifications").json()
    assert feed["unread"] == 2
    assert "Eklenen: Görev ve İş Yönetimi." in feed["items"][0]["body"]
    assert "Kaldırılan: Satış ve Siparişler, Stok ve Depo, Müşteri ve Teklifler." in feed["items"][0]["body"]
    assert "silinmedi" in feed["items"][0]["body"]

    first_id = feed["items"][0]["id"]
    after_one = client.post(f"/api/v1/notifications/{first_id}/read", headers=csrf(client)).json()
    assert after_one["unread"] == 1
    after_all = client.post("/api/v1/notifications/read-all", headers=csrf(client)).json()
    assert after_all["unread"] == 0
    assert client.post(f"/api/v1/notifications/{uuid4()}/read", headers=csrf(client)).status_code == 404

    company_id = client.get("/api/v1/auth/me").json()["company_id"]
    with psycopg.connect(database) as connection:
        rows = connection.execute(
            "SELECT module_key, status FROM company_modules WHERE company_id = %s ORDER BY module_key",
            (company_id,),
        ).fetchall()
    assert rows == [
        ("customers", "disabled"),
        ("inventory", "disabled"),
        ("sales", "disabled"),
        ("tasks", "enabled"),
    ]


def test_workspaces_stay_separate(client) -> None:
    first = sign_in_new_company(client, "Birinci Modül")
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["projects"]}).status_code == 200
    first_note = client.get("/api/v1/notifications").json()["items"][0]["id"]
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    sign_in_new_company(client, "İkinci Modül")
    assert enabled_keys(client.get("/api/v1/modules")) == set()
    assert client.get("/api/v1/notifications").json() == {"items": [], "unread": 0}
    assert client.post(f"/api/v1/notifications/{first_note}/read", headers=csrf(client)).status_code == 404
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["finance"]}).status_code == 200
    assert client.get("/api/v1/modules/projects").status_code == 403
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": first, "password": PASSWORD}).status_code == 200
    assert enabled_keys(client.get("/api/v1/modules")) == {"projects", "tasks"}
    assert client.get("/api/v1/notifications").json()["unread"] == 1
