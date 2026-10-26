from datetime import timedelta

from test_auth import csrf
from test_modules import sign_in_new_company
from test_sales import act, create, customer, product
from test_tasks import company_today


def workspace(client) -> None:
    sign_in_new_company(client, "Sinyal Atölyesi")
    modules = ["customers", "sales", "inventory", "finance", "tasks"]
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": modules}).status_code == 200


def income(client, buyer: str, due) -> dict:
    body = {"kind": "income", "category": "Satış", "description": "Dolap", "amount": "900", "record_date": (due - timedelta(days=10)).isoformat(), "due_date": due.isoformat(), "customer_id": buyer}
    response = client.post("/api/v1/finance/records", headers=csrf(client), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def auto_tasks(client) -> list[dict]:
    return [task for task in client.get("/api/v1/tasks", params={"page_size": 100}).json()["items"] if task["automatic"]]


def test_signals_create_tasks_once_and_close_them_when_resolved(client, database: str) -> None:
    workspace(client)
    today = company_today(database)
    buyer = customer(client, "Geciken Mobilya")
    record = income(client, buyer, today - timedelta(days=9))
    product(client, stock="1", name="Vida", minimum="10")

    insights = client.get("/api/v1/insights").json()
    kinds = {item["kind"] for item in insights["items"]}
    assert {"receivable_overdue", "restock"} <= kinds
    late = next(item for item in insights["items"] if item["kind"] == "receivable_overdue")
    assert late["severity"] == "high" and "9 gün" in late["title"] and late["task_id"]

    tasks = auto_tasks(client)
    titles = sorted(task["title"] for task in tasks)
    assert any(title.startswith("Tahsilatı takip et: Geciken Mobilya") for title in titles)
    assert any(title.startswith("Satın alma yap: Vida") for title in titles)
    follow = next(task for task in tasks if task["title"].startswith("Tahsilatı"))
    assert follow["customer_id"] == buyer and follow["priority"] == "high" and follow["assignee_id"]

    assert client.post("/api/v1/autopilot/run", headers=csrf(client)).json() == {"created": 0, "resolved": 0}
    assert len(auto_tasks(client)) == len(tasks)

    paid = client.post(f"/api/v1/finance/records/{record['id']}/payments", headers=csrf(client), json={"amount": "900", "paid_on": today.isoformat()})
    assert paid.status_code == 201
    result = client.post("/api/v1/autopilot/run", headers=csrf(client)).json()
    assert result["resolved"] == 1
    closed = client.get(f"/api/v1/tasks/{follow['id']}").json()
    assert closed["status"] == "done"

    feed = client.get("/api/v1/activity", params={"module": "tasks"}).json()["items"]
    assert any(item["action"] == "task.auto_resolved" and item["actor_name"] == "LUMINOVA" for item in feed)


def test_scheduled_pass_works_without_a_signed_in_user(client, database: str) -> None:
    from uuid import UUID

    from app.core.database import get_sessionmaker
    from app.services.scheduler import run_scheduled

    workspace(client)
    today = company_today(database)
    buyer = customer(client, "Sessiz Mobilya")
    income(client, buyer, today - timedelta(days=4))
    company = UUID(client.get("/api/v1/auth/me").json()["company_id"])
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    with get_sessionmaker()() as db:
        totals = run_scheduled(db, {company})
    assert totals["companies"] == 1 and totals["created"] >= 1

    with get_sessionmaker()() as db:
        from sqlalchemy import select

        from app.modules.tasks.models import Task

        titles = list(db.scalars(select(Task.title).where(Task.company_id == company, Task.source_key.is_not(None))))
    assert any(title.startswith("Tahsilatı takip et: Sessiz Mobilya") for title in titles)


def test_manual_completion_snoozes_and_settings_filter_kinds(client, database: str) -> None:
    workspace(client)
    today = company_today(database)
    buyer = customer(client, "Takip Yapı")
    income(client, buyer, today - timedelta(days=2))
    client.get("/api/v1/insights")
    task = next(task for task in auto_tasks(client) if task["title"].startswith("Tahsilatı"))
    assert client.post(f"/api/v1/tasks/{task['id']}/status", headers=csrf(client), json={"status": "done"}).status_code == 200
    client.post("/api/v1/autopilot/run", headers=csrf(client))
    assert not [item for item in auto_tasks(client) if item["status"] != "done" and item["title"].startswith("Tahsilatı")]

    settings = client.get("/api/v1/autopilot").json()
    assert settings["enabled"] is True and all(kind["on"] for kind in settings["kinds"] if kind["key"] != "auto_assign")
    assert next(kind for kind in settings["kinds"] if kind["key"] == "auto_assign")["on"] is False
    bad = client.put("/api/v1/autopilot", headers=csrf(client), json={"enabled": True, "kinds": ["bilinmeyen"]})
    assert bad.status_code == 422

    order = create(client, buyer, [{"description": "Montaj", "quantity": "1", "unit_price": "100"}]).json()
    assert act(client, order["id"], "confirm").status_code == 200
    saved = client.put("/api/v1/autopilot", headers=csrf(client), json={"enabled": True, "kinds": ["restock"]}).json()
    assert [kind["key"] for kind in saved["kinds"] if kind["on"]] == ["restock"]
    product(client, stock="0", name="Menteşe", minimum="5")
    client.post("/api/v1/autopilot/run", headers=csrf(client))
    open_titles = [item["title"] for item in auto_tasks(client) if item["status"] != "done"]
    assert open_titles and all(title.startswith("Satın alma yap") for title in open_titles)

    loose = client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Sahipsiz iş"}).json()
    assert loose["assignee_id"] is None
    client.put("/api/v1/autopilot", headers=csrf(client), json={"enabled": True, "kinds": ["restock", "auto_assign"]})
    me = next(person for person in client.get("/api/v1/tasks/assignees").json() if person["me"])
    assert client.get(f"/api/v1/tasks/{loose['id']}").json()["assignee_id"] == me["id"]

    off = client.put("/api/v1/autopilot", headers=csrf(client), json={"enabled": False, "kinds": []}).json()
    assert off["enabled"] is False
    assert not [item for item in auto_tasks(client) if item["status"] != "done"]
