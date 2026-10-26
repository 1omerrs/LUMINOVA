from uuid import uuid4

import psycopg
from test_auth import csrf
from test_modules import PASSWORD, sign_in_new_company
from test_sales import product, stock_of


def open_production(client, company: str = "Üretim Atölyesi") -> str:
    email = sign_in_new_company(client, company)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["production"]}).status_code == 200
    return email


def create(client, output: str, quantity: str, materials: list[tuple[str, str]], **extra):
    return client.post(
        "/api/v1/production/orders",
        headers=csrf(client),
        json={"product_id": output, "quantity": quantity, "materials": [{"product_id": pid, "quantity": qty} for pid, qty in materials], **extra},
    )


def act(client, order_id: str, action: str, body: dict | None = None):
    return client.post(f"/api/v1/production/orders/{order_id}/{action}", headers=csrf(client), json=body)


def test_production_needs_the_module(client) -> None:
    assert client.get("/api/v1/production/orders").status_code == 401
    sign_in_new_company(client)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["inventory"]}).status_code == 200
    assert client.get("/api/v1/production/orders").status_code == 403
    modules = client.put("/api/v1/modules", headers=csrf(client), json={"modules": ["production"]}).json()["modules"]
    assert {item["key"] for item in modules if item["enabled"]} == {"production", "inventory"}


def test_validation_rules(client) -> None:
    open_production(client)
    table = product(client, stock="0", name="Masa")
    wood = product(client, stock="10", name="Kereste", unit="m")
    screw = product(client, stock="100", name="Vida")

    assert create(client, table, "1", []).status_code == 422
    assert create(client, str(uuid4()), "1", [(wood, "1")]).json()["detail"] == "Üretilecek ürün bulunamadı."
    assert create(client, table, "1.5", [(wood, "1")]).json()["detail"] == "Üretim miktarı Adet biriminde tam sayı olmalı."
    assert create(client, table, "1", [(table, "1")]).json()["detail"] == "Üretilen ürün kendi malzemesi olamaz."
    assert create(client, table, "1", [(wood, "1"), (wood, "2")]).json()["detail"] == "Kereste iki kez eklendi; miktarları tek satırda birleştirin."
    assert create(client, table, "1", [(screw, "0.5")]).json()["detail"] == "1. malzeme: Adet biriminde miktar tam sayı olmalı."
    assert create(client, table, "1", [(str(uuid4()), "1")]).json()["detail"] == "1. malzeme bulunamadı."

    first = create(client, table, "2", [(wood, "3.5"), (screw, "16")], planned_date="2026-10-30", note="  Ofis masası  ")
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["code"] == "UE-0001"
    assert body["status"] == "planned"
    assert body["note"] == "Ofis masası"
    assert [(line["name"], line["quantity"], line["available"], line["short"]) for line in body["materials"]] == [
        ("Kereste", "3.5", "10", False),
        ("Vida", "16", "100", False),
    ]
    assert create(client, table, "1", [(wood, "1")]).json()["code"] == "UE-0002"

    edited = client.put(
        f"/api/v1/production/orders/{body['id']}",
        headers=csrf(client),
        json={"product_id": table, "quantity": "3", "materials": [{"product_id": wood, "quantity": "12"}]},
    )
    assert edited.status_code == 200
    assert edited.json()["material_count"] == 1
    assert edited.json()["shortage"] is True
    assert edited.json()["materials"][0]["short"] is True


def test_completion_posts_stock_once_and_blocks_shortage(client, database: str) -> None:
    open_production(client)
    table = product(client, stock="1", name="Meşe Masa")
    wood = product(client, stock="5", name="Meşe Kereste", unit="m", minimum="3")
    screw = product(client, stock="10", name="Vida")
    order = create(client, table, "2", [(wood, "4"), (screw, "16")]).json()

    blocked = act(client, order["id"], "complete")
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "Malzeme yetersiz: Vida (mevcut 10, gereken 16 adet)."
    assert (stock_of(client, table), stock_of(client, wood), stock_of(client, screw)) == ("1", "5", "10")

    client.post(f"/api/v1/inventory/products/{screw}/movements", headers=csrf(client), json={"kind": "in", "quantity": "10"})
    started = act(client, order["id"], "start").json()
    assert started["status"] == "in_progress" and started["started_at"] is not None
    assert act(client, order["id"], "start").status_code == 409
    locked = client.put(f"/api/v1/production/orders/{order['id']}", headers=csrf(client), json={"product_id": table, "quantity": "1", "materials": [{"product_id": wood, "quantity": "1"}]})
    assert locked.status_code == 409

    done = act(client, order["id"], "complete")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed" and done.json()["stock_posted"] is True
    assert (stock_of(client, table), stock_of(client, wood), stock_of(client, screw)) == ("3", "1", "4")
    assert act(client, order["id"], "complete").status_code == 409
    assert act(client, order["id"], "cancel", {"reason": "Vazgeçtik"}).json()["detail"].startswith("Tamamlanan iş emri iptal edilemez.")

    low = [item for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "inventory"]
    assert len(low) == 1 and "Meşe Kereste" in low[0]["title"]

    with psycopg.connect(database) as connection:
        movements = connection.execute(
            "SELECT kind, quantity::text, note FROM stock_movements WHERE reference_type = 'production' AND reference_id = %s",
            (order["id"],),
        ).fetchall()
    assert sorted(movements) == sorted(
        [
            ("out", "-4.0000", "UE-0001 üretim tüketimi"),
            ("out", "-16.0000", "UE-0001 üretim tüketimi"),
            ("in", "2.0000", "UE-0001 üretim çıkışı"),
        ]
    )


def test_cancel_and_list(client) -> None:
    open_production(client)
    chair = product(client, stock="0", name="Sandalye")
    wood = product(client, stock="1", name="Kayın", unit="m")
    first = create(client, chair, "4", [(wood, "2")]).json()
    second = create(client, chair, "1", [(wood, "1")]).json()

    assert act(client, first["id"], "cancel", {"reason": "x"}).status_code == 422
    cancelled = act(client, first["id"], "cancel", {"reason": "Müşteri vazgeçti"}).json()
    assert cancelled["status"] == "cancelled" and cancelled["cancel_reason"] == "Müşteri vazgeçti"
    assert cancelled["shortage"] is False
    assert act(client, first["id"], "complete").status_code == 409
    assert stock_of(client, wood) == "1"

    assert client.get("/api/v1/production/summary").json() == {"planned": 1, "in_progress": 0, "completed": 0, "cancelled": 1}
    listed = client.get("/api/v1/production/orders").json()["items"]
    assert [item["code"] for item in listed] == ["UE-0002", "UE-0001"]
    assert listed[1]["shortage"] is False and listed[0]["shortage"] is False
    assert [item["code"] for item in client.get("/api/v1/production/orders", params={"q": "ue-2"}).json()["items"]] == ["UE-0002"]
    assert [item["code"] for item in client.get("/api/v1/production/orders", params={"q": "SANDALYE", "status": "planned"}).json()["items"]] == ["UE-0002"]
    assert second["shortage"] is False
    decimal = create(client, chair, "1", [(wood, "2.5")]).json()
    assert act(client, decimal["id"], "complete").json()["detail"] == "Malzeme yetersiz: Kayın (mevcut 1, gereken 2,5 m)."


def test_orders_stay_in_their_company(client) -> None:
    first = open_production(client, "Birinci Üretim")
    output = product(client, stock="0", name="Gizli")
    material = product(client, stock="5", name="Malzeme", unit="kg")
    owned = create(client, output, "1", [(material, "1")]).json()
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    open_production(client, "İkinci Üretim")
    assert client.get("/api/v1/production/orders").json()["total"] == 0
    assert client.get(f"/api/v1/production/orders/{owned['id']}").status_code == 404
    assert act(client, owned["id"], "complete").status_code == 404
    assert create(client, output, "1", [(material, "1")]).status_code == 422
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": first, "password": PASSWORD}).status_code == 200
    assert client.get(f"/api/v1/production/orders/{owned['id']}").json()["status"] == "planned"
