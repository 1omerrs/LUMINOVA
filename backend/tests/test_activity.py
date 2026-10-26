from uuid import uuid4

from fastapi.testclient import TestClient
from test_auth import csrf
from test_modules import sign_in_new_company
from test_sales import create, customer, product
from test_team import accept, invite


def lines(client, **params) -> list[str]:
    body = client.get("/api/v1/activity", params=params).json()
    return [" ".join(part for part in (item["actor_name"], item["verb"], item["target"] or "", item["detail"] or "") if part).strip() for item in body["items"]]


def test_activity_feed_reads_audit_log(client) -> None:
    sign_in_new_company(client, "Etkinlik Atölyesi")
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["sales", "tasks"]}).status_code == 200
    me = client.get("/api/v1/tasks/assignees").json()[0]
    name = me["name"]

    buyer = customer(client, "Bora Ltd.")
    assert create(client, buyer, [{"description": "Montaj", "quantity": "1", "unit_price": "10"}]).status_code == 201
    item = product(client, stock="10", name="Seramik kupa", unit="kg")
    moved = client.post(f"/api/v1/inventory/products/{item}/movements", headers=csrf(client), json={"kind": "in", "quantity": "2.5"})
    assert moved.status_code == 201, moved.text
    task = client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Fuar standı"}).json()
    client.post(f"/api/v1/tasks/{task['id']}/status", headers=csrf(client), json={"status": "done"})
    client.delete(f"/api/v1/tasks/{task['id']}", headers=csrf(client))

    feed = lines(client)
    assert feed[:5] == [
        f"{name} görevi sildi Fuar standı",
        f"{name} görev durumunu değiştirdi Fuar standı Yapılacak → Tamamlandı",
        f"{name} görev ekledi Fuar standı",
        f"{name} stok hareketi kaydetti Seramik kupa Giriş 2,5 kg, kalan 12,5 kg",
        f"{name} ürün ekledi Seramik kupa",
    ]
    assert feed[5] == f"{name} sipariş oluşturdu SP-0001 1 kalem"
    assert f"{name} müşteri ekledi Bora Ltd." in feed
    assert f"{name} modül açtı Satış ve Siparişler" in feed

    deleted = client.get("/api/v1/activity").json()["items"][0]
    assert deleted["link"] is None and deleted["module"] == "tasks"
    assert all(line.split(" ", 2)[-1].startswith(("görev",)) for line in lines(client, module="tasks"))
    assert client.get("/api/v1/activity", params={"module": "payroll"}).status_code == 422

    first = client.get("/api/v1/activity", params={"limit": 3}).json()
    second = client.get("/api/v1/activity", params={"limit": 3, "cursor": first["next_cursor"]}).json()
    assert len(first["items"]) == 3 and first["next_cursor"]
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})
    assert [actor["name"] for actor in first["actors"]] == [name]
    assert client.get("/api/v1/activity", params={"cursor": "bozuk"}).status_code == 422

    client.put("/api/v1/modules", headers=csrf(client), json={"modules": ["customers", "inventory"]})
    assert lines(client, module="tasks") == []
    assert not any("görev" in line for line in lines(client, limit=50))


def test_members_see_team_joins_only_and_tenancy(client) -> None:
    sign_in_new_company(client, "Ekip Etkinliği")
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["tasks"]}).status_code == 200
    created = invite(client, f"ece-{uuid4().hex[:8]}@example.com").json()
    invite(client, f"iptal-{uuid4().hex[:8]}@example.com")

    from app.main import create_app

    with TestClient(create_app()) as other:
        assert accept(other, created["invite_path"]).status_code == 201
        member_view = lines(other, module="workspace")
        assert member_view[0] == "Ece Yıldız ekibe katıldı Rol: Üye"
        assert not any("davet" in line for line in member_view)
        owner_view = lines(client, module="workspace")
        assert sum("davet oluşturdu" in line for line in owner_view) == 2

        sign_in_new_company(other, "Başka Şirket")
        other.post("/api/v1/workspace/setup", headers=csrf(other), json={"modules": ["tasks"]})
        assert not any("Ece" in line or "davet" in line for line in lines(other, limit=50))
