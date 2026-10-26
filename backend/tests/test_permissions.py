from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from test_auth import csrf
from test_insights import auto_tasks, income, workspace
from test_sales import customer
from test_tasks import company_today
from test_team import accept, invite


def joined(client, permissions: dict[str, str]) -> tuple[TestClient, str]:
    from app.main import create_app

    created = invite(client, f"uye-{uuid4().hex[:8]}@example.com", permissions=permissions)
    assert created.status_code == 201, created.text
    assert created.json()["invitation"]["permissions"] == permissions
    other = TestClient(create_app())
    other.__enter__()
    assert accept(other, created.json()["invite_path"]).status_code == 201
    member_id = other.get("/api/v1/auth/me").json()["id"]
    return other, member_id


def visible(client) -> dict[str, str | None]:
    return {item["key"]: item["access"] for item in client.get("/api/v1/modules").json()["modules"] if item["enabled"]}


def test_member_sees_only_granted_modules(client, database: str) -> None:
    workspace(client)
    today = company_today(database)
    buyer = customer(client, "Gizli Müşteri")
    income(client, buyer, today - timedelta(days=5))
    assert client.post("/api/v1/autopilot/run", headers=csrf(client)).json()["created"] >= 1

    member, member_id = joined(client, {"tasks": "edit", "inventory": "view"})
    try:
        assert visible(member) == {"tasks": "edit", "inventory": "view"}
        blocked = member.get("/api/v1/customers")
        assert blocked.status_code == 403 and "erişim yetkiniz yok" in blocked.json()["detail"]
        assert member.get("/api/v1/finance/records").status_code == 403
        assert member.get("/api/v1/quotes").status_code == 403
        assert member.get("/api/v1/inventory/products").status_code == 200
        readonly = member.post("/api/v1/inventory/products", headers=csrf(member), json={"sku": "GZ-1", "name": "Gizli", "unit": "adet", "min_stock": "0"})
        assert readonly.status_code == 403 and "yalnızca görüntüleme" in readonly.json()["detail"]
        assert member.post("/api/v1/tasks", headers=csrf(member), json={"title": "Benim işim"}).status_code == 201

        assert all(item["module"] in {"tasks", "inventory"} for item in member.get("/api/v1/insights").json()["items"])
        assert not [task for task in auto_tasks(member) if task["title"].startswith("Tahsilatı")]
        assert [task for task in auto_tasks(client) if task["title"].startswith("Tahsilatı")]
        actions = {item["action"].split(".")[0] for item in member.get("/api/v1/activity").json()["items"]}
        assert not actions & {"finance", "customer"}
        # Opening the notification list as a member must not close tasks the member cannot see.
        member.get("/api/v1/notifications")
        assert [task for task in auto_tasks(client) if task["title"].startswith("Tahsilatı") and task["status"] != "done"]

        team = client.put(f"/api/v1/team/members/{member_id}/permissions", headers=csrf(client), json={"permissions": {"sales": "edit"}}).json()
        granted = next(person for person in team["members"] if person["user_id"] == member_id)["permissions"]
        assert granted == {"sales": "edit", "customers": "view", "inventory": "view"}
        assert member.get("/api/v1/tasks").status_code == 403
        assert member.get("/api/v1/customers").status_code == 200
        assert member.post("/api/v1/customers", headers=csrf(member), json={"name": "Yeni"}).status_code == 403
        notes = [item["title"] for item in member.get("/api/v1/notifications").json()["items"] if item["category"] == "team"]
        assert "Modül yetkileriniz güncellendi." in notes
        assert member.put(f"/api/v1/team/members/{member_id}/permissions", headers=csrf(member), json={"permissions": {"tasks": "edit"}}).status_code == 403
    finally:
        member.__exit__(None, None, None)

    owner_id = client.get("/api/v1/auth/me").json()["id"]
    assert client.put(f"/api/v1/team/members/{owner_id}/permissions", headers=csrf(client), json={"permissions": {}}).status_code == 409
    assert client.put(f"/api/v1/team/members/{member_id}/permissions", headers=csrf(client), json={"permissions": {"projects": "edit"}}).status_code == 422
    assert client.put(f"/api/v1/team/members/{member_id}/permissions", headers=csrf(client), json={"permissions": {"automation": "view"}}).status_code == 422
    assert client.put(f"/api/v1/team/members/{member_id}/permissions", headers=csrf(client), json={"permissions": {"tasks": "owner"}}).status_code == 422


def test_member_without_grants_sees_nothing(client, database: str) -> None:
    workspace(client)
    member, _ = joined(client, {})
    try:
        assert visible(member) == {}
        assert member.get("/api/v1/tasks").status_code == 403
        assert member.get("/api/v1/insights").json()["items"] == []
    finally:
        member.__exit__(None, None, None)
