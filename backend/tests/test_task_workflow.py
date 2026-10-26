from datetime import timedelta

from test_auth import csrf
from test_modules import sign_in_new_company
from test_tasks import company_today


def workspace(client, modules: list[str] | None = None) -> str:
    sign_in_new_company(client, "Akış Atölyesi")
    chosen = modules or ["tasks", "customers"]
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": chosen}).status_code == 200
    return client.get("/api/v1/tasks/assignees").json()[0]["id"]


def task(client, title: str, **extra) -> dict:
    response = client.post("/api/v1/tasks", headers=csrf(client), json={"title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def depend(client, task_id: str, *parents: str):
    return client.put(f"/api/v1/tasks/{task_id}/dependencies", headers=csrf(client), json={"depends_on": list(parents)})


def move(client, task_id: str, status: str):
    return client.post(f"/api/v1/tasks/{task_id}/status", headers=csrf(client), json={"status": status})


def test_dependencies_block_progress_and_release_on_completion(client) -> None:
    workspace(client)
    measure = task(client, "Ölçü al")
    design = task(client, "Tasarımı çiz")
    install = task(client, "Montaj")

    linked = depend(client, install["id"], measure["id"], design["id"]).json()
    assert linked["blocked"] is True and sorted(d["title"] for d in linked["depends_on"]) == ["Tasarımı çiz", "Ölçü al"]
    assert depend(client, install["id"], install["id"]).status_code == 422
    assert depend(client, measure["id"], install["id"]).status_code == 409

    refused = move(client, install["id"], "in_progress")
    assert refused.status_code == 409 and "Ölçü al" in refused.json()["detail"]
    edit = {"title": "Montaj", "status": "done"}
    assert client.put(f"/api/v1/tasks/{install['id']}", headers=csrf(client), json=edit).status_code == 409

    assert move(client, measure["id"], "done").status_code == 200
    assert client.get(f"/api/v1/tasks/{install['id']}").json()["blocked"] is True
    assert move(client, design["id"], "done").status_code == 200
    freed = client.get(f"/api/v1/tasks/{install['id']}").json()
    assert freed["blocked"] is False
    assert move(client, install["id"], "in_progress").status_code == 200

    feed = client.get("/api/v1/activity", params={"module": "tasks"}).json()["items"]
    unblocked = [item for item in feed if item["verb"] == "sırası gelen görevi açtı"]
    assert len(unblocked) == 1 and unblocked[0]["target"] == "Montaj" and unblocked[0]["detail"] == "“Tasarımı çiz” tamamlandı"

    assert depend(client, install["id"]).json()["depends_on"] == []


def test_templates_create_linked_tasks_once_per_record(client, database: str) -> None:
    me = workspace(client)
    today = company_today(database)
    customer = client.post("/api/v1/customers", headers=csrf(client), json={"name": "Şablon Müşterisi"}).json()
    assert client.post("/api/v1/tasks/templates", headers=csrf(client), json={"name": "x", "items": []}).status_code == 422
    bad = {"name": "Ters", "items": [{"title": "Bir", "depends_on": [1]}, {"title": "İki"}]}
    assert client.post("/api/v1/tasks/templates", headers=csrf(client), json=bad).status_code == 422

    template = client.post(
        "/api/v1/tasks/templates",
        headers=csrf(client),
        json={
            "name": "Yeni müşteri açılışı",
            "items": [
                {"title": "Karşılama araması", "priority": "high", "offset_days": 0},
                {"title": "Fiyat listesi gönder", "offset_days": 2, "depends_on": [0]},
                {"title": "İlk siparişi takip et", "offset_days": 7, "depends_on": [1]},
            ],
        },
    ).json()
    assert [item["name"] for item in client.get("/api/v1/tasks/templates").json()] == ["Yeni müşteri açılışı"]

    apply = {"customer_id": customer["id"], "assignee_id": me, "start_date": str(today)}
    created = client.post(f"/api/v1/tasks/templates/{template['id']}/apply", headers=csrf(client), json=apply)
    assert created.status_code == 201, created.text
    tasks = created.json()["created"]
    assert [t["title"] for t in tasks] == ["Karşılama araması", "Fiyat listesi gönder", "İlk siparişi takip et"]
    assert [t["due_date"] for t in tasks] == [str(today), str(today + timedelta(days=2)), str(today + timedelta(days=7))]
    assert {t["customer_name"] for t in tasks} == {"Şablon Müşterisi"} and {t["assignee_id"] for t in tasks} == {me}
    assert [t["blocked"] for t in tasks] == [False, True, True]
    assert tasks[2]["depends_on"][0]["title"] == "Fiyat listesi gönder"

    again = client.post(f"/api/v1/tasks/templates/{template['id']}/apply", headers=csrf(client), json=apply)
    assert again.status_code == 409 and "zaten uygulandı" in again.json()["detail"]
    linked = client.get("/api/v1/tasks", params={"customer": customer["id"]}).json()
    assert linked["total"] == 3
    loose = client.post(f"/api/v1/tasks/templates/{template['id']}/apply", headers=csrf(client), json={"once_per_record": False})
    assert loose.status_code == 201

    verbs = [item["verb"] for item in client.get("/api/v1/activity", params={"module": "tasks"}).json()["items"][:2]]
    assert verbs == ["görev şablonunu uyguladı", "görev şablonunu uyguladı"]
    assert client.delete(f"/api/v1/tasks/templates/{template['id']}", headers=csrf(client)).status_code == 204
    assert client.post(f"/api/v1/tasks/templates/{template['id']}/apply", headers=csrf(client), json={}).status_code == 404


def test_today_view_groups_my_work(client, database: str) -> None:
    me = workspace(client)
    today = company_today(database)
    task(client, "Dünden kalan", assignee_id=me, due_date=str(today - timedelta(days=1)))
    task(client, "Bugünkü iş", assignee_id=me, due_date=str(today))
    task(client, "Süren iş", assignee_id=me, status="in_progress")
    first = task(client, "Hafta içi", assignee_id=me, due_date=str(today + timedelta(days=3)))
    waiting = task(client, "Sırada bekleyen", assignee_id=me)
    depend(client, waiting["id"], first["id"])
    task(client, "Başkasının işi", due_date=str(today))
    later = task(client, "Bekleyen ve haftaya düşen", assignee_id=me, due_date=str(today + timedelta(days=4)))
    depend(client, later["id"], first["id"])

    view = client.get("/api/v1/tasks/today").json()
    titles = {key: [item["title"] for item in view[key]] for key in ("overdue", "due_today", "in_progress", "upcoming", "waiting", "unblocked")}
    assert titles["overdue"] == ["Dünden kalan"]
    assert titles["due_today"] == ["Bugünkü iş"]
    assert titles["in_progress"] == ["Süren iş"]
    assert titles["upcoming"] == ["Hafta içi"]
    assert sorted(titles["waiting"]) == ["Bekleyen ve haftaya düşen", "Sırada bekleyen"]
    assert titles["unblocked"] == []
    mine = next(row for row in view["load"] if row["assignee_id"] == me)
    assert (mine["open"], mine["overdue"]) == (6, 1)
    assert any(row["assignee_id"] is None and row["open"] == 1 for row in view["load"])

    move(client, first["id"], "done")
    after = client.get("/api/v1/tasks/today").json()
    assert sorted(item["title"] for item in after["unblocked"]) == ["Bekleyen ve haftaya düşen", "Sırada bekleyen"]
    assert [item["title"] for item in after["upcoming"]] == []


def test_workflow_stays_in_its_company(client) -> None:
    workspace(client)
    secret = task(client, "Gizli görev")
    template = client.post("/api/v1/tasks/templates", headers=csrf(client), json={"name": "Gizli şablon", "items": [{"title": "Adım"}]}).json()
    client.post("/api/v1/auth/logout", headers=csrf(client))

    workspace(client)
    own = task(client, "Kendi görevim")
    assert depend(client, own["id"], secret["id"]).status_code == 422
    assert depend(client, secret["id"]).status_code == 404
    assert client.get("/api/v1/tasks/templates").json() == []
    assert client.post(f"/api/v1/tasks/templates/{template['id']}/apply", headers=csrf(client), json={}).status_code == 404
