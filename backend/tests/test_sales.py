from uuid import uuid4

import psycopg
from test_auth import csrf
from test_modules import PASSWORD, sign_in_new_company


def open_sales(client, company: str = "Satış Atölyesi") -> str:
    email = sign_in_new_company(client, company)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["sales"]}).status_code == 200
    return email


def customer(client, name: str = "Deniz Yapı") -> str:
    response = client.post("/api/v1/customers", headers=csrf(client), json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def product(client, *, stock: str, name: str = "Meşe Tabla", unit: str = "adet", minimum: str = "0") -> str:
    response = client.post(
        "/api/v1/inventory/products",
        headers=csrf(client),
        json={"sku": f"P-{uuid4().hex[:6]}", "name": name, "unit": unit, "min_stock": minimum, "initial_stock": stock},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def stock_of(client, product_id: str) -> str:
    return client.get(f"/api/v1/inventory/products/{product_id}").json()["stock_quantity"]


def create(client, customer_id: str, items: list[dict], **extra):
    return client.post(
        "/api/v1/sales/orders",
        headers=csrf(client),
        json={"customer_id": customer_id, "order_date": "2026-10-23", "items": items, **extra},
    )


def act(client, order_id: str, action: str, note: str | None = None):
    return client.post(f"/api/v1/sales/orders/{order_id}/{action}", headers=csrf(client), json={"note": note} if note else None)


def test_sales_needs_the_module(client) -> None:
    assert client.get("/api/v1/sales/orders").status_code == 401
    sign_in_new_company(client)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["inventory"]}).status_code == 200
    assert client.get("/api/v1/sales/orders").status_code == 403


def test_order_totals_numbers_and_validation(client, database: str) -> None:
    open_sales(client)
    buyer = customer(client)
    table = product(client, stock="10", name="Meşe Tabla")

    assert create(client, buyer, []).status_code == 422
    assert create(client, str(uuid4()), [{"description": "Hizmet", "quantity": "1", "unit_price": "100"}]).json()["detail"] == "Seçilen müşteri bulunamadı."
    assert create(client, buyer, [{"quantity": "1", "unit_price": "10"}]).json()["detail"] == "1. satır için ürün seçin veya açıklama yazın."
    fractional = create(client, buyer, [{"product_id": table, "quantity": "1.5", "unit_price": "10"}])
    assert fractional.status_code == 422
    assert fractional.json()["detail"] == "1. satır: Adet biriminde miktar tam sayı olmalı."
    assert create(client, buyer, [{"description": "X", "quantity": "1", "unit_price": "10", "vat_rate": 18}]).status_code == 422

    first = create(
        client,
        buyer,
        [
            {"product_id": table, "quantity": "3", "unit_price": "1250.50", "vat_rate": 20},
            {"description": "Montaj hizmeti", "quantity": "1", "unit_price": "333.33", "vat_rate": 10},
        ],
        note="  Hafta içi teslim  ",
    )
    assert first.status_code == 201, first.text
    order = first.json()
    assert order["code"] == "SP-0001"
    assert order["status"] == "draft"
    assert order["note"] == "Hafta içi teslim"
    assert order["items"][0]["description"] == "Meşe Tabla"
    assert order["items"][0]["line_subtotal"] == "3751.50"
    assert order["items"][0]["line_vat"] == "750.30"
    assert order["items"][1]["line_vat"] == "33.33"
    assert order["subtotal"] == "4084.83"
    assert order["vat_total"] == "783.63"
    assert order["total"] == "4868.46"
    assert [event["to_status"] for event in order["events"]] == ["draft"]

    second = create(client, buyer, [{"description": "Danışmanlık", "quantity": "2", "unit_price": "500", "vat_rate": 0}], currency="EUR")
    assert second.json()["code"] == "SP-0002"
    assert second.json()["total"] == "1000.00"

    edited = client.put(
        f"/api/v1/sales/orders/{order['id']}",
        headers=csrf(client),
        json={"customer_id": buyer, "order_date": "2026-10-24", "items": [{"product_id": table, "quantity": "2", "unit_price": "1000"}]},
    )
    assert edited.status_code == 200
    assert edited.json()["total"] == "2400.00"
    assert len(edited.json()["items"]) == 1
    assert stock_of(client, table) == "10"

    with psycopg.connect(database) as connection:
        stored = connection.execute("SELECT total::text FROM orders WHERE id = %s", (order["id"],)).fetchone()
    assert stored == ("2400.0000",)


def test_fulfilment_posts_stock_once_and_cancel_returns_it(client, database: str) -> None:
    open_sales(client)
    buyer = customer(client)
    table = product(client, stock="10", name="Meşe Tabla", minimum="5")
    paint = product(client, stock="4.5", name="Ceviz Boya", unit="lt")
    order = create(
        client,
        buyer,
        [
            {"product_id": table, "quantity": "4", "unit_price": "100"},
            {"product_id": paint, "quantity": "1.25", "unit_price": "80"},
            {"product_id": table, "quantity": "2", "unit_price": "100"},
            {"description": "Nakliye", "quantity": "1", "unit_price": "50"},
        ],
    ).json()

    early = act(client, order["id"], "fulfil")
    assert early.status_code == 409
    assert early.json()["detail"] == "Bu sipariş taslak durumunda; bu işlem yapılamaz."

    assert act(client, order["id"], "confirm").json()["status"] == "confirmed"
    locked = client.put(
        f"/api/v1/sales/orders/{order['id']}",
        headers=csrf(client),
        json={"customer_id": buyer, "order_date": "2026-10-23", "items": [{"description": "X", "quantity": "1", "unit_price": "1"}]},
    )
    assert locked.status_code == 409

    fulfilled = act(client, order["id"], "fulfil", note="Kargo ile gönderildi")
    assert fulfilled.status_code == 200, fulfilled.text
    assert fulfilled.json()["status"] == "fulfilled"
    assert fulfilled.json()["stock_posted"] is True
    assert stock_of(client, table) == "4"
    assert stock_of(client, paint) == "3.25"
    assert act(client, order["id"], "fulfil").status_code == 409

    low = [item for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "inventory"]
    assert len(low) == 1

    cancelled = act(client, order["id"], "cancel", note="Müşteri iade etti")
    assert cancelled.json()["status"] == "cancelled"
    assert stock_of(client, table) == "10"
    assert stock_of(client, paint) == "4.5"
    assert [event["to_status"] for event in cancelled.json()["events"]] == ["draft", "confirmed", "fulfilled", "cancelled"]
    assert cancelled.json()["events"][2]["note"] == "Kargo ile gönderildi"
    assert act(client, order["id"], "cancel").status_code == 409

    with psycopg.connect(database) as connection:
        movements = connection.execute(
            "SELECT kind, quantity::text, reference_type FROM stock_movements WHERE reference_id = %s ORDER BY created_at, kind",
            (order["id"],),
        ).fetchall()
    assert sorted(movements) == sorted(
        [
            ("out", "-6.0000", "order"),
            ("out", "-1.2500", "order"),
            ("in", "6.0000", "order_cancel"),
            ("in", "1.2500", "order_cancel"),
        ]
    )


def test_shortage_blocks_fulfilment_without_partial_posting(client) -> None:
    open_sales(client)
    buyer = customer(client)
    enough = product(client, stock="10", name="Yeterli Ürün")
    scarce = product(client, stock="1", name="Az Ürün")
    order = create(
        client,
        buyer,
        [{"product_id": enough, "quantity": "5", "unit_price": "10"}, {"product_id": scarce, "quantity": "3", "unit_price": "10"}],
    ).json()
    act(client, order["id"], "confirm")

    blocked = act(client, order["id"], "fulfil")
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "Stok yetersiz: Az Ürün (mevcut 1, gereken 3 adet)."
    assert stock_of(client, enough) == "10"
    assert client.get(f"/api/v1/sales/orders/{order['id']}").json()["status"] == "confirmed"

    client.post(f"/api/v1/inventory/products/{scarce}/movements", headers=csrf(client), json={"kind": "in", "quantity": "2"})
    assert act(client, order["id"], "fulfil").status_code == 200
    assert stock_of(client, enough) == "5"
    assert stock_of(client, scarce) == "0"


def test_list_filters_search_and_summary(client) -> None:
    open_sales(client)
    deniz = customer(client, "Deniz Yapı")
    ilgaz = customer(client, "Ilgaz Mobilya")
    one = create(client, deniz, [{"description": "A", "quantity": "1", "unit_price": "10"}]).json()
    create(client, ilgaz, [{"description": "B", "quantity": "1", "unit_price": "99"}])
    three = create(client, ilgaz, [{"description": "C", "quantity": "1", "unit_price": "5"}]).json()
    act(client, one["id"], "confirm")
    act(client, three["id"], "cancel")

    assert client.get("/api/v1/sales/summary").json() == {"draft": 1, "confirmed": 1, "fulfilled": 0, "cancelled": 1}
    assert [item["code"] for item in client.get("/api/v1/sales/orders", params={"status": "draft"}).json()["items"]] == ["SP-0002"]
    assert [item["code"] for item in client.get("/api/v1/sales/orders", params={"q": "ILGAZ"}).json()["items"]] == ["SP-0003", "SP-0002"]
    assert [item["code"] for item in client.get("/api/v1/sales/orders", params={"q": "sp-1"}).json()["items"]] == ["SP-0001"]
    assert [item["code"] for item in client.get("/api/v1/sales/orders", params={"sort": "-total"}).json()["items"]][0] == "SP-0002"
    listed = client.get("/api/v1/sales/orders").json()["items"][0]
    assert listed["customer_name"] == "Ilgaz Mobilya"
    assert listed["item_count"] == 1


def test_orders_stay_in_their_company(client) -> None:
    first = open_sales(client, "Birinci Satış")
    buyer = customer(client)
    owned = create(client, buyer, [{"description": "Gizli", "quantity": "1", "unit_price": "1"}]).json()
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    open_sales(client, "İkinci Satış")
    assert client.get("/api/v1/sales/orders").json()["total"] == 0
    assert client.get(f"/api/v1/sales/orders/{owned['id']}").status_code == 404
    assert act(client, owned["id"], "cancel").status_code == 404
    foreign_customer = create(client, buyer, [{"description": "X", "quantity": "1", "unit_price": "1"}])
    assert foreign_customer.status_code == 422
    mine = create(client, customer(client), [{"description": "Benim", "quantity": "1", "unit_price": "1"}]).json()
    assert mine["code"] == "SP-0001"
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": first, "password": PASSWORD}).status_code == 200
    assert client.get(f"/api/v1/sales/orders/{owned['id']}").json()["status"] == "draft"
