from datetime import timedelta

from test_auth import csrf
from test_modules import sign_in_new_company
from test_sales import product
from test_tasks import company_today


def setup(client, modules: list[str]) -> str:
    sign_in_new_company(client, "Hatırlatma Atölyesi")
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": modules}).status_code == 200
    return client.get("/api/v1/tasks/assignees").json()[0]["id"] if "tasks" in modules else ""


def titles(client, category: str) -> list[str]:
    return sorted(item["title"] for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == category)


def test_due_reminders_are_written_once(client, database: str) -> None:
    me = setup(client, ["tasks", "finance"])
    today = company_today(database)
    for title, offset in (("Dün", -1), ("Bugün", 0), ("Yarın", 1), ("Gelecek hafta", 7)):
        client.post("/api/v1/tasks", headers=csrf(client), json={"title": f"{title} işi", "due_date": str(today + timedelta(days=offset)), "assignee_id": me})
    client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Başkasının işi", "due_date": str(today)})
    client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Biten iş", "due_date": str(today), "assignee_id": me, "status": "done"})
    client.post(
        "/api/v1/finance/records",
        headers=csrf(client),
        json={"kind": "income", "category": "Satış", "description": "Bora tahsilatı", "amount": "500", "record_date": str(today), "due_date": str(today + timedelta(days=2))},
    )
    client.post(
        "/api/v1/finance/records",
        headers=csrf(client),
        json={"kind": "expense", "category": "Kira", "description": "Kira", "amount": "900", "record_date": str(today), "due_date": str(today - timedelta(days=4))},
    )

    expected_tasks = ["Görev bugün teslim: Bugün işi", "Görev gecikti: Dün işi", "Görev yarın teslim: Yarın işi"]
    assert titles(client, "tasks") == expected_tasks
    assert titles(client, "finance") == ["Tahsilat vadesi yaklaşıyor: Bora tahsilatı", "Ödeme vadesi geçti: Kira"]
    assert titles(client, "tasks") == expected_tasks


def test_preferences_mute_a_category(client) -> None:
    setup(client, ["inventory"])
    prefs = client.get("/api/v1/notifications/preferences").json()
    assert [item["category"] for item in prefs] == ["tasks", "finance", "quotes", "inventory", "team", "support", "automation", "workspace", "digest"]
    assert all(item["in_app"] for item in prefs if item["in_app_available"])
    digest = next(item for item in prefs if item["category"] == "digest")
    assert digest["in_app_available"] is False and digest["email"] is True
    assert client.put("/api/v1/notifications/preferences", headers=csrf(client), json={"in_app": {"payroll": False}}).status_code == 422

    muted = client.put("/api/v1/notifications/preferences", headers=csrf(client), json={"in_app": {"inventory": False}}).json()
    assert next(item for item in muted if item["category"] == "inventory")["in_app"] is False
    quiet = product(client, stock="10", name="Sessiz Ürün", minimum="5")
    client.post(f"/api/v1/inventory/products/{quiet}/movements", headers=csrf(client), json={"kind": "out", "quantity": "8"})
    assert titles(client, "inventory") == []

    client.put("/api/v1/notifications/preferences", headers=csrf(client), json={"in_app": {"inventory": True}})
    loud = product(client, stock="10", name="Sesli Ürün", minimum="5")
    client.post(f"/api/v1/inventory/products/{loud}/movements", headers=csrf(client), json={"kind": "out", "quantity": "8"})
    assert titles(client, "inventory") == ["Sesli Ürün kritik seviyeye indi."]
