from datetime import date, timedelta
from uuid import uuid4

import psycopg
from test_auth import csrf
from test_modules import PASSWORD, sign_in_new_company


def open_tasks(client, company: str = "Görev Atölyesi") -> str:
    email = sign_in_new_company(client, company)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["tasks"]}).status_code == 200
    return email


def company_today(database: str) -> date:
    with psycopg.connect(database) as connection:
        row = connection.execute("SELECT (now() AT TIME ZONE 'Europe/Istanbul')::date").fetchone()
    assert row is not None
    return row[0]


def create(client, title: str, **extra):
    return client.post("/api/v1/tasks", headers=csrf(client), json={"title": title, **extra})


def titles(client, **params) -> list[str]:
    response = client.get("/api/v1/tasks", params=params)
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


def test_tasks_need_the_module(client) -> None:
    assert client.get("/api/v1/tasks").status_code == 401
    sign_in_new_company(client)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["inventory"]}).status_code == 200
    assert client.get("/api/v1/tasks").status_code == 403
    assert create(client, "Kapalı modül").status_code == 403


def test_create_update_status_and_delete(client, database: str) -> None:
    open_tasks(client)
    me = client.get("/api/v1/tasks/assignees").json()
    assert len(me) == 1 and me[0]["me"] is True

    assert create(client, "x").status_code == 422
    assert create(client, "Geçerli", priority="critical").status_code == 422
    foreign = create(client, "Yabancı sorumlu", assignee_id=str(uuid4()))
    assert foreign.status_code == 422
    assert foreign.json()["detail"] == "Seçilen sorumlu bu çalışma alanında değil."

    created = create(client, "  Tedarikçiyi   ara ", description="  Fiyat teyidi  ", priority="high", assignee_id=me[0]["id"])
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["title"] == "Tedarikçiyi ara"
    assert task["description"] == "Fiyat teyidi"
    assert task["status"] == "todo"
    assert task["assignee_name"] == me[0]["name"]
    assert task["completed_at"] is None

    moved = client.post(f"/api/v1/tasks/{task['id']}/status", headers=csrf(client), json={"status": "done"})
    assert moved.json()["status"] == "done"
    assert moved.json()["completed_at"] is not None
    reopened = client.put(f"/api/v1/tasks/{task['id']}", headers=csrf(client), json={"title": "Tedarikçiyi ara", "status": "in_progress"})
    assert reopened.status_code == 200
    assert reopened.json()["completed_at"] is None
    assert reopened.json()["assignee_id"] is None
    assert reopened.json()["priority"] == "normal"

    assert client.delete(f"/api/v1/tasks/{task['id']}", headers=csrf(client)).status_code == 204
    assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404
    assert client.get("/api/v1/tasks").json()["total"] == 0

    with psycopg.connect(database) as connection:
        actions = [row[0] for row in connection.execute("SELECT action FROM audit_logs WHERE entity_id = %s ORDER BY created_at", (task["id"],))]
    assert actions == ["task.created", "task.status_changed", "task.updated", "task.deleted"]


def test_due_filters_use_the_company_date(client, database: str) -> None:
    open_tasks(client)
    today = company_today(database)
    create(client, "Dün bitmeliydi", due_date=str(today - timedelta(days=1)))
    create(client, "Bugün teslim", due_date=str(today), priority="urgent")
    create(client, "Haftaya kalan", due_date=str(today + timedelta(days=6)))
    create(client, "Gelecek ay", due_date=str(today + timedelta(days=30)))
    create(client, "Tarihsiz iş")
    finished = create(client, "Eski ama bitti", due_date=str(today - timedelta(days=3)), status="done").json()
    assert finished["completed_at"] is not None
    assert finished["overdue"] is False

    page = client.get("/api/v1/tasks").json()
    assert page["today"] == str(today)
    assert [item["title"] for item in page["items"]] == ["Eski ama bitti", "Dün bitmeliydi", "Bugün teslim", "Haftaya kalan", "Gelecek ay", "Tarihsiz iş"]
    assert [item["overdue"] for item in page["items"]][:2] == [False, True]
    assert titles(client, due="overdue") == ["Dün bitmeliydi"]
    assert titles(client, due="today") == ["Bugün teslim"]
    assert titles(client, due="week") == ["Bugün teslim", "Haftaya kalan"]
    assert titles(client, due="none") == ["Tarihsiz iş"]
    assert titles(client, sort="-priority")[0] == "Bugün teslim"

    summary = client.get("/api/v1/tasks/summary").json()
    assert summary == {"todo": 5, "in_progress": 0, "done": 1, "overdue": 1, "due_today": 1, "today": str(today)}


def test_search_filters_and_sorting(client) -> None:
    open_tasks(client)
    me = client.get("/api/v1/tasks/assignees").json()[0]["id"]
    create(client, "Çınar masası ölçüsü", assignee_id=me, priority="low")
    create(client, "Irmak için teklif", description="İndirimli fiyat")
    create(client, "Ambalaj siparişi", status="in_progress")

    assert titles(client, q="ÇINAR") == ["Çınar masası ölçüsü"]
    assert titles(client, q="indirimli") == ["Irmak için teklif"]
    assert titles(client, q="100%") == []
    assert titles(client, assignee="me") == ["Çınar masası ölçüsü"]
    assert set(titles(client, assignee="none")) == {"Irmak için teklif", "Ambalaj siparişi"}
    assert titles(client, status="in_progress") == ["Ambalaj siparişi"]
    assert titles(client, priority="low") == ["Çınar masası ölçüsü"]
    assert titles(client, sort="title") == ["Ambalaj siparişi", "Çınar masası ölçüsü", "Irmak için teklif"]
    assert client.get("/api/v1/tasks", params={"assignee": "kimse"}).status_code == 422


def test_assigning_a_teammate_notifies_them(client, database: str) -> None:
    teammate_email = sign_in_new_company(client, "Ekip Arkadaşı")
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204
    owner_email = open_tasks(client, "Ana Atölye")
    with psycopg.connect(database) as connection:
        teammate = connection.execute("SELECT id FROM users WHERE email = %s", (teammate_email,)).fetchone()[0]
        company = connection.execute(
            "SELECT company_id FROM company_memberships JOIN users ON users.id = user_id WHERE email = %s", (owner_email,)
        ).fetchone()[0]
        connection.execute("INSERT INTO company_memberships (id, company_id, user_id) VALUES (%s, %s, %s)", (uuid4(), company, teammate))

    assert len(client.get("/api/v1/tasks/assignees").json()) == 2
    task = create(client, "Numune gönder", assignee_id=str(teammate)).json()
    client.put(f"/api/v1/tasks/{task['id']}", headers=csrf(client), json={"title": "Numune gönder", "assignee_id": str(teammate), "priority": "high"})
    self_assigned = client.get("/api/v1/tasks/assignees").json()
    mine = next(item["id"] for item in self_assigned if item["me"])
    create(client, "Kendime not", assignee_id=mine)

    with psycopg.connect(database) as connection:
        rows = connection.execute(
            "SELECT user_id, company_id, category, body FROM notifications WHERE category = 'tasks' AND company_id = %s", (company,)
        ).fetchall()
    assert [(row[0], row[1], row[2]) for row in rows] == [(teammate, company, "tasks")]
    assert rows[0][3].endswith(": Numune gönder")
    assert [item for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "tasks"] == []


def test_tasks_stay_in_their_company(client) -> None:
    first = open_tasks(client, "Birinci Görev")
    owned = create(client, "Gizli görev").json()
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    open_tasks(client, "İkinci Görev")
    assert client.get("/api/v1/tasks").json()["total"] == 0
    assert client.get(f"/api/v1/tasks/{owned['id']}").status_code == 404
    assert client.post(f"/api/v1/tasks/{owned['id']}/status", headers=csrf(client), json={"status": "done"}).status_code == 404
    assert client.delete(f"/api/v1/tasks/{owned['id']}", headers=csrf(client)).status_code == 404
    assert client.get("/api/v1/tasks/summary").json()["todo"] == 0
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": first, "password": PASSWORD}).status_code == 200
    assert client.get(f"/api/v1/tasks/{owned['id']}").json()["status"] == "todo"
