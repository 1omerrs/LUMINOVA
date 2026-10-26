from uuid import uuid4

import psycopg
from test_auth import csrf
from test_modules import PASSWORD, sign_in_new_company


def open_inventory(client, company: str = "Depo Atölyesi") -> str:
    email = sign_in_new_company(client, company)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["inventory"]}).status_code == 200
    return email


def add_product(client, **fields) -> dict:
    body = {"sku": f"SKU-{uuid4().hex[:6]}", "name": "Meşe Tabla", "unit": "adet", "min_stock": "0", **fields}
    response = client.post("/api/v1/inventory/products", headers=csrf(client), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def move(client, product_id: str, kind: str, quantity: str, **extra):
    return client.post(
        f"/api/v1/inventory/products/{product_id}/movements",
        headers=csrf(client),
        json={"kind": kind, "quantity": quantity, **extra},
    )


def test_inventory_needs_the_module(client) -> None:
    assert client.get("/api/v1/inventory/products").status_code == 401
    sign_in_new_company(client)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["customers"]}).status_code == 200
    assert client.get("/api/v1/inventory/products").status_code == 403
    assert client.get("/api/v1/inventory/summary").status_code == 403


def test_products_crud_and_validation(client, database: str) -> None:
    open_inventory(client)

    bad = client.post(
        "/api/v1/inventory/products",
        headers=csrf(client),
        json={"sku": "kod boşluk", "name": "X", "unit": "ton", "min_stock": "-1"},
    )
    assert bad.status_code == 422
    fields = {item["loc"][-1] for item in bad.json()["detail"]}
    assert {"sku", "name", "unit", "min_stock"} <= fields

    fraction = client.post(
        "/api/v1/inventory/products",
        headers=csrf(client),
        json={"sku": "ADET-1", "name": "Vida", "unit": "adet", "min_stock": "2.5"},
    )
    assert fraction.status_code == 422
    assert fraction.json()["detail"] == "Minimum stok Adet biriminde tam sayı olmalı."

    product = add_product(client, sku="MT-001", name="Meşe Tabla", min_stock="5", initial_stock="12", description="  80x120  ")
    assert product["stock_quantity"] == "12"
    assert product["min_stock"] == "5"
    assert product["description"] == "80x120"
    assert product["low"] is False

    duplicate = client.post("/api/v1/inventory/products", headers=csrf(client), json={"sku": "mt-001", "name": "Kopya", "unit": "adet", "min_stock": "0"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Bu stok koduyla kayıtlı bir ürün zaten var."

    weighed = add_product(client, sku="BOYA-1", name="Ceviz Boya", unit="lt", min_stock="1.5", initial_stock="2.25")
    assert weighed["stock_quantity"] == "2.25"
    to_whole = client.put(
        f"/api/v1/inventory/products/{weighed['id']}",
        headers=csrf(client),
        json={"sku": "BOYA-1", "name": "Ceviz Boya", "unit": "adet", "min_stock": "1"},
    )
    assert to_whole.status_code == 422

    renamed = client.put(
        f"/api/v1/inventory/products/{product['id']}",
        headers=csrf(client),
        json={"sku": "MT-001", "name": "Meşe Tabla 80x120", "unit": "adet", "min_stock": "5"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Meşe Tabla 80x120"
    assert renamed.json()["stock_quantity"] == "12"

    assert client.delete(f"/api/v1/inventory/products/{weighed['id']}", headers=csrf(client)).status_code == 204
    assert client.get(f"/api/v1/inventory/products/{weighed['id']}").status_code == 404
    again = add_product(client, sku="boya-1", name="Yeni Boya", unit="lt")
    assert again["sku"] == "boya-1"

    with psycopg.connect(database) as connection:
        opening = connection.execute(
            "SELECT kind, quantity::text, balance_after::text, note FROM stock_movements WHERE product_id = %s",
            (product["id"],),
        ).fetchall()
        kept = connection.execute("SELECT deleted_at IS NOT NULL FROM products WHERE id = %s", (weighed["id"],)).fetchone()
    assert opening == [("in", "12.0000", "12.0000", "Açılış stoku")]
    assert kept == (True,)


def test_movements_keep_balance_and_history(client, database: str) -> None:
    open_inventory(client)
    product = add_product(client, sku="KAL-01", name="Kalem", min_stock="10", initial_stock="20")

    received = move(client, product["id"], "in", "5", note="Tedarikçi teslimatı")
    assert received.status_code == 201
    assert received.json()["product"]["stock_quantity"] == "25"
    assert received.json()["movement"]["actor"] == "Ömer Yılmaz"

    too_much = move(client, product["id"], "out", "26")
    assert too_much.status_code == 409
    assert too_much.json()["detail"] == "Stokta yeterli miktar yok. Mevcut stok: 25 adet."

    assert move(client, product["id"], "out", "0").status_code == 422
    assert move(client, product["id"], "out", "1.5").status_code == 422
    assert move(client, product["id"], "adjustment", "25").json()["detail"] == "Sayılan miktar mevcut stokla aynı."

    shipped = move(client, product["id"], "out", "16")
    assert shipped.json()["product"]["stock_quantity"] == "9"
    assert shipped.json()["product"]["low"] is True

    counted = move(client, product["id"], "adjustment", "7", note="Ay sonu sayımı")
    assert counted.json()["movement"]["quantity"] == "-2"
    assert counted.json()["product"]["stock_quantity"] == "7"

    history = client.get(f"/api/v1/inventory/products/{product['id']}/movements").json()
    assert history["total"] == 4
    assert [item["kind"] for item in history["items"]] == ["adjustment", "out", "in", "in"]
    assert [item["balance_after"] for item in history["items"]] == ["7", "9", "25", "20"]

    feed = client.get("/api/v1/notifications").json()
    low = [item for item in feed["items"] if item["category"] == "inventory"]
    assert len(low) == 1
    assert low[0]["title"] == "Kalem minimum stok seviyesinin altına düştü."
    assert low[0]["body"] == "Mevcut stok 9 adet, minimum 10 adet."

    move(client, product["id"], "in", "10")
    move(client, product["id"], "out", "9")
    low_again = [item for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "inventory"]
    assert len(low_again) == 2

    summary = client.get("/api/v1/inventory/summary").json()
    assert summary == {"products": 1, "low": 1, "critical": 0}
    assert client.get("/api/v1/inventory/products", params={"low": "true"}).json()["total"] == 1

    with psycopg.connect(database) as connection:
        cached, summed = connection.execute(
            "SELECT p.stock_quantity, sum(m.quantity) FROM products p JOIN stock_movements m ON m.product_id = p.id WHERE p.id = %s GROUP BY p.stock_quantity",
            (product["id"],),
        ).fetchone()
    assert cached == summed


def test_idempotent_movements(client) -> None:
    open_inventory(client)
    first = add_product(client, sku="ID-1", initial_stock="3")
    second = add_product(client, sku="ID-2")
    key = f"move-{uuid4().hex}"

    one = move(client, first["id"], "in", "4", idempotency_key=key)
    two = move(client, first["id"], "in", "4", idempotency_key=key)
    assert one.status_code == two.status_code == 201
    assert one.json()["movement"]["id"] == two.json()["movement"]["id"]
    assert client.get(f"/api/v1/inventory/products/{first['id']}").json()["stock_quantity"] == "7"

    reused = move(client, second["id"], "in", "1", idempotency_key=key)
    assert reused.status_code == 409


def test_list_search_and_sort(client) -> None:
    open_inventory(client)
    add_product(client, sku="Z-9", name="Zımpara", min_stock="5", initial_stock="1")
    add_product(client, sku="C-1", name="Çivi", initial_stock="100")
    add_product(client, sku="I-2", name="Işık Bandı", unit="m", initial_stock="3.5")

    names = [item["name"] for item in client.get("/api/v1/inventory/products", params={"sort": "name"}).json()["items"]]
    assert names == ["Çivi", "Işık Bandı", "Zımpara"]
    by_stock = [item["name"] for item in client.get("/api/v1/inventory/products", params={"sort": "stock"}).json()["items"]]
    assert by_stock == ["Zımpara", "Işık Bandı", "Çivi"]
    assert [item["name"] for item in client.get("/api/v1/inventory/products", params={"q": "IŞIK"}).json()["items"]] == ["Işık Bandı"]
    assert [item["name"] for item in client.get("/api/v1/inventory/products", params={"q": "c-1"}).json()["items"]] == ["Çivi"]
    assert [item["name"] for item in client.get("/api/v1/inventory/products", params={"low": "true"}).json()["items"]] == ["Zımpara"]


def test_inventory_stays_in_its_company(client) -> None:
    first = open_inventory(client, "Birinci Depo")
    owned = add_product(client, sku="GIZLI-1", name="Gizli Ürün", initial_stock="5")
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    open_inventory(client, "İkinci Depo")
    assert client.get("/api/v1/inventory/products").json()["total"] == 0
    assert client.get(f"/api/v1/inventory/products/{owned['id']}").status_code == 404
    assert client.get(f"/api/v1/inventory/products/{owned['id']}/movements").status_code == 404
    assert move(client, owned["id"], "out", "5").status_code == 404
    assert client.delete(f"/api/v1/inventory/products/{owned['id']}", headers=csrf(client)).status_code == 404
    add_product(client, sku="GIZLI-1", name="Kendi Ürünüm")
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": first, "password": PASSWORD}).status_code == 200
    assert client.get(f"/api/v1/inventory/products/{owned['id']}").json()["stock_quantity"] == "5"
