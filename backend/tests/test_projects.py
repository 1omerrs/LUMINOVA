from datetime import timedelta
from uuid import uuid4

import psycopg
from test_auth import csrf
from test_modules import PASSWORD, sign_in_new_company
from test_tasks import company_today


def open_projects(client, company: str = "Proje Atölyesi", extra: list[str] | None = None) -> str:
    email = sign_in_new_company(client, company)
    modules = ["projects", *(extra or [])]
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": modules}).status_code == 200
    return email


def create(client, name: str, **extra):
    return client.post("/api/v1/projects", headers=csrf(client), json={"name": name, **extra})


def task(client, title: str, **extra) -> dict:
    response = client.post("/api/v1/tasks", headers=csrf(client), json={"title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_projects_need_the_module(client) -> None:
    assert client.get("/api/v1/projects").status_code == 401
    sign_in_new_company(client)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["tasks"]}).status_code == 200
    assert client.get("/api/v1/projects").status_code == 403


def test_create_validate_and_link_a_customer(client) -> None:
    open_projects(client, extra=["customers"])
    assert create(client, "x").status_code == 422
    backwards = create(client, "Ters tarih", start_date="2026-11-10", due_date="2026-11-01")
    assert backwards.status_code == 422
    assert backwards.json()["detail"][0]["msg"] == "Teslim tarihi başlangıç tarihinden önce olamaz."
    assert create(client, "Yabancı müşteri", customer_id=str(uuid4())).json()["detail"] == "Seçilen müşteri bulunamadı."

    buyer = client.post("/api/v1/customers", headers=csrf(client), json={"name": "Deniz Yapı"}).json()["id"]
    project = create(client, "  Ofis   mobilyası ", customer_id=buyer, status="active", start_date="2026-10-20", due_date="2026-11-30")
    assert project.status_code == 201, project.text
    body = project.json()
    assert body["name"] == "Ofis mobilyası"
    assert body["customer_name"] == "Deniz Yapı"
    assert body["progress"] == 0 and body["task_total"] == 0

    done = client.put(f"/api/v1/projects/{body['id']}", headers=csrf(client), json={"name": "Ofis mobilyası", "status": "completed"})
    assert done.json()["completed_at"] is not None
    assert done.json()["customer_id"] is None
    reopened = client.put(f"/api/v1/projects/{body['id']}", headers=csrf(client), json={"name": "Ofis mobilyası", "status": "on_hold"})
    assert reopened.json()["completed_at"] is None


def test_progress_follows_linked_tasks(client, database: str) -> None:
    open_projects(client)
    today = company_today(database)
    project = create(client, "Showroom yenileme", status="active", due_date=str(today - timedelta(days=1))).json()
    assert project["overdue"] is True
    other = create(client, "Katalog çekimi").json()

    assert client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Yanlış proje", "project_id": str(uuid4())}).json()["detail"] == "Seçilen proje bulunamadı."
    first = task(client, "Zemin ölçüsü", project_id=project["id"], status="done")
    task(client, "Aydınlatma seçimi", project_id=project["id"], due_date=str(today - timedelta(days=2)))
    task(client, "Boya", project_id=project["id"])
    task(client, "Projesiz iş")
    task(client, "Fotoğrafçı ara", project_id=other["id"])

    detail = client.get(f"/api/v1/projects/{project['id']}").json()
    assert (detail["task_total"], detail["task_done"], detail["task_overdue"], detail["progress"]) == (3, 1, 1, 33)

    tasks = client.get("/api/v1/tasks", params={"project": project["id"]}).json()["items"]
    assert {item["title"] for item in tasks} == {"Zemin ölçüsü", "Aydınlatma seçimi", "Boya"}
    assert all(item["project_name"] == "Showroom yenileme" for item in tasks)
    assert [item["title"] for item in client.get("/api/v1/tasks", params={"project": "none"}).json()["items"]] == ["Projesiz iş"]

    kept = client.put(f"/api/v1/tasks/{first['id']}", headers=csrf(client), json={"title": "Zemin ölçüsü", "status": "done", "project_id": project["id"]})
    assert kept.json()["project_id"] == project["id"]

    listed = {item["name"]: item for item in client.get("/api/v1/projects").json()["items"]}
    assert listed["Katalog çekimi"]["task_total"] == 1
    assert listed["Showroom yenileme"]["progress"] == 33
    assert client.get("/api/v1/projects/summary").json() == {"planned": 1, "active": 1, "on_hold": 0, "completed": 0, "overdue": 1}
    assert [item["name"] for item in client.get("/api/v1/projects", params={"q": "SHOWROOM"}).json()["items"]] == ["Showroom yenileme"]
    assert [item["name"] for item in client.get("/api/v1/projects", params={"status": "planned"}).json()["items"]] == ["Katalog çekimi"]

    assert client.delete(f"/api/v1/projects/{project['id']}", headers=csrf(client)).status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    survivors = client.get("/api/v1/tasks", params={"project": "none"}).json()["items"]
    assert {item["title"] for item in survivors} == {"Zemin ölçüsü", "Aydınlatma seçimi", "Boya", "Projesiz iş"}
    assert task(client, "Işık kur", project_id=other["id"])["project_name"] == "Katalog çekimi"
    assert client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Silinmiş", "project_id": project["id"]}).status_code == 422

    with psycopg.connect(database) as connection:
        summary = connection.execute(
            "SELECT summary FROM audit_logs WHERE entity_id = %s AND action = 'project.deleted'", (project["id"],)
        ).fetchone()[0]
    assert summary["unlinked_tasks"] == 3


def test_projects_stay_in_their_company(client) -> None:
    first = open_projects(client, "Birinci Proje")
    owned = create(client, "Gizli proje").json()
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    open_projects(client, "İkinci Proje")
    assert client.get("/api/v1/projects").json()["total"] == 0
    assert client.get(f"/api/v1/projects/{owned['id']}").status_code == 404
    assert client.delete(f"/api/v1/projects/{owned['id']}", headers=csrf(client)).status_code == 404
    assert client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Sızma", "project_id": owned["id"]}).status_code == 422
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": first, "password": PASSWORD}).status_code == 200
    assert client.get(f"/api/v1/projects/{owned['id']}").json()["name"] == "Gizli proje"
