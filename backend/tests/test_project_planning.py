from datetime import date, timedelta

from test_auth import csrf
from test_projects import open_projects
from test_sales import customer
from test_tasks import company_today

STEPS = [
    {"stage": "Keşif", "title": "Ölçü al", "duration_days": 2},
    {"stage": "Keşif", "title": "Teklif onayı", "duration_days": 1, "depends_on": [0]},
    {"stage": "Üretim", "title": "Kesim", "duration_days": 3, "depends_on": [1]},
    {"stage": "Üretim", "title": "Boya", "duration_days": 2, "depends_on": [2]},
    {"stage": "Teslim", "title": "Montaj", "duration_days": 1, "depends_on": [3]},
    {"stage": "Teslim", "title": "Fatura kes", "duration_days": 1, "depends_on": [3]},
]


def template(client) -> dict:
    response = client.post("/api/v1/projects/templates", headers=csrf(client), json={"name": "Mutfak projesi", "items": STEPS})
    assert response.status_code == 201, response.text
    return response.json()


def plan(client, project_id: str) -> dict:
    response = client.get(f"/api/v1/projects/{project_id}/plan")
    assert response.status_code == 200, response.text
    return response.json()


def by_title(data: dict) -> dict[str, dict]:
    return {task["title"]: task for task in data["tasks"]}


def day(value: date) -> str:
    return value.isoformat()


def move(client, task_id: str, status: str):
    return client.post(f"/api/v1/tasks/{task_id}/status", headers=csrf(client), json={"status": status})


def test_template_builds_scheduled_project_and_stages_close_themselves(client, database: str) -> None:
    open_projects(client, "Plan Atölyesi", ["tasks"])
    saved = template(client)
    assert saved["stages"] == ["Keşif", "Üretim", "Teslim"] and saved["total_days"] == 9
    forward = {"name": "Hatalı", "items": [{"stage": "A", "title": "İlk", "depends_on": [1]}, {"stage": "A", "title": "İkinci"}]}
    assert client.post("/api/v1/projects/templates", headers=csrf(client), json=forward).status_code == 422

    start = company_today(database) + timedelta(days=1)
    created = client.post("/api/v1/projects", headers=csrf(client), json={"name": "Kaya mutfağı", "start_date": day(start), "template_id": saved["id"]})
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["due_date"] == day(start + timedelta(days=8)) and project["task_total"] == 6 and project["milestone_total"] == 3

    data = plan(client, project["id"])
    tasks = by_title(data)
    assert (tasks["Ölçü al"]["start_date"], tasks["Ölçü al"]["due_date"]) == (day(start), day(start + timedelta(days=1)))
    assert (tasks["Kesim"]["start_date"], tasks["Kesim"]["due_date"]) == (day(start + timedelta(days=3)), day(start + timedelta(days=5)))
    assert tasks["Montaj"]["due_date"] == day(start + timedelta(days=8))
    assert tasks["Teklif onayı"]["blocked"] is True and tasks["Ölçü al"]["blocked"] is False
    assert all(task["critical"] for task in data["tasks"])
    assert [m["due_date"] for m in data["milestones"]] == [day(start + timedelta(days=2)), day(start + timedelta(days=7)), day(start + timedelta(days=8))]
    assert data["pending_changes"] == 0 and data["delay_days"] == 0 and data["actual_progress"] == 0
    assert any(risk["kind"] == "bottleneck" and "Boya" in risk["title"] for risk in data["risks"])

    assert move(client, tasks["Ölçü al"]["id"], "done").status_code == 200
    assert move(client, tasks["Teklif onayı"]["id"], "done").status_code == 200
    stages = client.get(f"/api/v1/projects/{project['id']}/milestones").json()
    assert [stage["done"] for stage in stages] == [True, False, False]
    assert move(client, tasks["Teklif onayı"]["id"], "todo").status_code == 200
    assert client.get(f"/api/v1/projects/{project['id']}/milestones").json()[0]["done"] is False

    activity = client.get("/api/v1/activity").json()["items"]
    assert any(item["action"] == "project.template_applied" and "6 görev" in (item["detail"] or "") for item in activity)
    assert any(item["action"] == "project.milestone_completed" and "otomatik" in (item["detail"] or "") for item in activity)


def test_reschedule_previews_then_applies_and_flags_late_finish(client, database: str) -> None:
    open_projects(client, "Takvim Atölyesi", ["tasks"])
    saved = template(client)
    today = company_today(database)
    body = {"name": "Gecikmeli iş", "start_date": day(today - timedelta(days=5)), "due_date": day(today + timedelta(days=5)), "template_id": saved["id"]}
    project = client.post("/api/v1/projects", headers=csrf(client), json=body).json()

    data = plan(client, project["id"])
    tasks = by_title(data)
    assert tasks["Ölçü al"]["start_date"] == day(today) and tasks["Montaj"]["due_date"] == day(today + timedelta(days=8))
    assert data["delay_days"] == 3 and data["risks"][0]["kind"] == "late_finish"
    assert data["expected_progress"] is not None

    cut = tasks["Kesim"]
    longer = {"title": "Kesim", "status": "todo", "priority": "normal", "due_date": day(date.fromisoformat(cut["due_date"]) + timedelta(days=2)), "project_id": project["id"]}
    assert client.put(f"/api/v1/tasks/{cut['id']}", headers=csrf(client), json=longer).status_code == 200
    data = plan(client, project["id"])
    assert by_title(data)["Kesim"]["duration_days"] == 5 and data["pending_changes"] == 3

    preview = client.post(f"/api/v1/projects/{project['id']}/reschedule", headers=csrf(client), json={"apply": False}).json()
    assert preview["applied"] is False and sorted(change["title"] for change in preview["changes"]) == ["Boya", "Fatura kes", "Montaj"]
    assert plan(client, project["id"])["pending_changes"] == 3

    applied = client.post(f"/api/v1/projects/{project['id']}/reschedule", headers=csrf(client), json={"apply": True}).json()
    assert applied["applied"] is True and applied["delay_days"] == 5 and applied["projected_finish"] == day(today + timedelta(days=10))
    data = plan(client, project["id"])
    assert data["pending_changes"] == 0 and by_title(data)["Montaj"]["due_date"] == day(today + timedelta(days=10))
    assert data["milestones"][2]["due_date"] == day(today + timedelta(days=10))


def test_working_days_skip_weekends_and_fixed_holidays(client) -> None:
    from app.modules.projects.planning import add_working_days

    open_projects(client, "İş Günü Atölyesi", ["tasks"])
    saved = template(client)
    friday = date(2031, 2, 7)
    assert friday.weekday() == 4
    body = {"name": "Hafta sonu yok", "start_date": day(friday), "template_id": saved["id"], "working_days_only": True}
    project = client.post("/api/v1/projects", headers=csrf(client), json=body).json()
    assert project["working_days_only"] is True
    tasks = by_title(plan(client, project["id"]))
    assert tasks["Ölçü al"]["due_date"] == day(friday + timedelta(days=3))
    assert tasks["Teklif onayı"]["start_date"] == day(friday + timedelta(days=4))
    assert tasks["Boya"]["start_date"] == day(friday + timedelta(days=10))
    assert tasks["Montaj"]["due_date"] == day(friday + timedelta(days=12))
    assert client.get(f"/api/v1/projects/{project['id']}").json()["due_date"] == day(friday + timedelta(days=12))

    renamed = client.put(f"/api/v1/projects/{project['id']}", headers=csrf(client), json={"name": "Hafta sonu yok 2", "start_date": day(friday)}).json()
    assert renamed["working_days_only"] is True
    assert add_working_days(date(2031, 10, 28), 2) == date(2031, 10, 30)


def test_project_links_inherit_customer_and_reject_mismatch(client) -> None:
    open_projects(client, "Bağlantı Atölyesi", ["customers", "sales"])
    buyer, other = customer(client, "Ece Mimarlık"), customer(client, "Başka Firma")
    order = client.post(
        "/api/v1/sales/orders",
        headers=csrf(client),
        json={"customer_id": buyer, "order_date": "2026-10-23", "items": [{"description": "Montaj hizmeti", "quantity": "1", "unit_price": "100"}]},
    )
    assert order.status_code == 201, order.text
    linked = client.post("/api/v1/projects", headers=csrf(client), json={"name": "Sipariş projesi", "order_id": order.json()["id"]})
    assert linked.status_code == 201, linked.text
    assert linked.json()["customer_id"] == buyer and linked.json()["order_code"].startswith("SP-")
    clash = client.post("/api/v1/projects", headers=csrf(client), json={"name": "Yanlış", "order_id": order.json()["id"], "customer_id": other})
    assert clash.status_code == 422 and "başka bir müşteriye" in clash.json()["detail"]

    renamed = client.put(f"/api/v1/projects/{linked.json()['id']}", headers=csrf(client), json={"name": "Sipariş projesi 2", "customer_id": buyer})
    assert renamed.status_code == 200 and renamed.json()["order_id"] == order.json()["id"]
    cleared = client.put(f"/api/v1/projects/{linked.json()['id']}", headers=csrf(client), json={"name": "Sipariş projesi 2", "customer_id": buyer, "order_id": None})
    assert cleared.json()["order_id"] is None
