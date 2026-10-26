from datetime import timedelta

from test_auth import csrf
from test_projects import create, open_projects
from test_tasks import company_today


def add(client, project: str, title: str, **extra):
    return client.post(f"/api/v1/projects/{project}/milestones", headers=csrf(client), json={"title": title, **extra})


def titles(rows: list[dict]) -> list[str]:
    return [row["title"] for row in rows]


def test_milestones_order_complete_and_summarise(client, database: str) -> None:
    open_projects(client, "Aşama Atölyesi")
    today = company_today(database)
    project = create(client, "Mağaza açılışı", status="active").json()
    pid = project["id"]
    assert project["milestone_total"] == 0 and project["next_milestone"] is None
    assert add(client, pid, "x").status_code == 422

    add(client, pid, "Keşif ve ölçü", due_date=str(today - timedelta(days=2)))
    add(client, pid, "Tasarım onayı", due_date=str(today + timedelta(days=5)))
    rows = add(client, pid, "  Montaj   ve teslim ").json()
    assert titles(rows) == ["Keşif ve ölçü", "Tasarım onayı", "Montaj ve teslim"]
    assert [row["overdue"] for row in rows] == [True, False, False]

    first = rows[0]
    rows = client.put(f"/api/v1/projects/{pid}/milestones/{first['id']}", headers=csrf(client), json={"title": first["title"], "due_date": first["due_date"], "done": True}).json()
    assert rows[0]["done"] is True and rows[0]["overdue"] is False and rows[0]["completed_at"]

    rows = client.post(f"/api/v1/projects/{pid}/milestones/{rows[2]['id']}/move", headers=csrf(client), json={"direction": "up"}).json()
    assert titles(rows) == ["Keşif ve ölçü", "Montaj ve teslim", "Tasarım onayı"]
    rows = client.post(f"/api/v1/projects/{pid}/milestones/{rows[0]['id']}/move", headers=csrf(client), json={"direction": "up"}).json()
    assert titles(rows)[0] == "Keşif ve ölçü"

    summary = client.get(f"/api/v1/projects/{pid}").json()
    assert (summary["milestone_total"], summary["milestone_done"], summary["next_milestone"]) == (3, 1, "Montaj ve teslim")
    listed = next(item for item in client.get("/api/v1/projects").json()["items"] if item["id"] == pid)
    assert listed["milestone_done"] == 1

    rows = client.delete(f"/api/v1/projects/{pid}/milestones/{rows[1]['id']}", headers=csrf(client)).json()
    assert titles(rows) == ["Keşif ve ölçü", "Tasarım onayı"]
    assert client.delete(f"/api/v1/projects/{pid}/milestones/{rows[1]['id']}", headers=csrf(client)).status_code == 200
    assert client.delete(f"/api/v1/projects/{pid}/milestones/{rows[1]['id']}", headers=csrf(client)).status_code == 404

    verbs = [(item["verb"], item["detail"]) for item in client.get("/api/v1/activity", params={"module": "projects"}).json()["items"][:3]]
    assert verbs[0] == ("proje aşamasını kaldırdı", "Aşama: Tasarım onayı")
    assert ("proje aşamasını tamamladı", "Aşama: Keşif ve ölçü") in [
        (item["verb"], item["detail"]) for item in client.get("/api/v1/activity", params={"module": "projects"}).json()["items"]
    ]


def test_milestones_stay_in_their_company(client) -> None:
    open_projects(client, "Birinci Aşama")
    pid = create(client, "Gizli proje").json()["id"]
    milestone = add(client, pid, "Gizli aşama").json()[0]
    client.post("/api/v1/auth/logout", headers=csrf(client))

    open_projects(client, "İkinci Aşama")
    assert client.get(f"/api/v1/projects/{pid}/milestones").status_code == 404
    assert add(client, pid, "Sızma denemesi").status_code == 404
    own = create(client, "Kendi projem").json()["id"]
    assert client.delete(f"/api/v1/projects/{own}/milestones/{milestone['id']}", headers=csrf(client)).status_code == 404
