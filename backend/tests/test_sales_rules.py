from datetime import date, timedelta
from uuid import uuid4

from test_auth import csrf
from test_modules import sign_in_new_company
from test_sales import act, create, customer, product
from test_tasks import company_today


def workspace(client, modules: list[str]) -> None:
    sign_in_new_company(client, "Kural Atölyesi")
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": modules}).status_code == 200


def line(product_id: str | None = None, **extra) -> dict:
    return {"product_id": product_id, "description": "" if product_id else "Montaj hizmeti", "quantity": "1", "unit_price": "100", **extra}


def records(client, order_id: str) -> list[dict]:
    return client.get("/api/v1/finance/records", params={"order_id": order_id}).json()["items"]


def test_line_discount_totals_and_quote_lineage(client) -> None:
    workspace(client, ["customers", "sales", "inventory"])
    buyer = customer(client, "İskonto Mobilya")
    order = create(client, buyer, [line(quantity="2", unit_price="1000", discount_rate="10", vat_rate=20)]).json()
    assert (order["subtotal"], order["discount_total"], order["vat_total"], order["total"]) == ("1800.00", "200.00", "360.00", "2160.00")
    assert order["items"][0]["discount_rate"] == "10" and order["items"][0]["line_discount"] == "200.00"
    too_much = create(client, buyer, [line(discount_rate="120")])
    assert too_much.status_code == 422

    quote = client.post(
        "/api/v1/quotes",
        headers=csrf(client),
        json={"customer_id": buyer, "quote_date": "2026-10-23", "items": [line(quantity="3", unit_price="500", discount_rate="5")]},
    ).json()
    assert quote["discount_total"] == "75.00" and quote["total"] == "1710.00"
    for action in ("send", "accept", "convert"):
        assert client.post(f"/api/v1/quotes/{quote['id']}/{action}", headers=csrf(client)).status_code == 200
    converted = client.get(f"/api/v1/quotes/{quote['id']}").json()
    made = client.get(f"/api/v1/sales/orders/{converted['order_id']}").json()
    assert made["total"] == "1710.00" and made["items"][0]["discount_rate"] == "5"
    assert made["source_quote_id"] == quote["id"] and made["source_quote_code"] == quote["code"]


def test_reservations_show_available_stock_and_shortages(client) -> None:
    workspace(client, ["customers", "sales", "inventory"])
    buyer = customer(client, "Rezerv Yapı")
    shelf = product(client, stock="5", name="Raf")
    first = create(client, buyer, [line(shelf, quantity="3")]).json()
    assert first["stock_check"][0]["short"] == "0"
    assert act(client, first["id"], "confirm").status_code == 200
    item = client.get(f"/api/v1/inventory/products/{shelf}").json()
    assert (item["stock_quantity"], item["reserved"], item["available"]) == ("5", "3", "2")

    second = create(client, buyer, [line(shelf, quantity="4")]).json()
    check = second["stock_check"][0]
    assert (check["on_hand"], check["reserved_elsewhere"], check["available"], check["short"]) == ("5", "3", "2", "2")
    assert act(client, second["id"], "confirm").status_code == 200
    assert client.get(f"/api/v1/inventory/products/{shelf}").json()["available"] == "-2"

    assert act(client, first["id"], "fulfil").status_code == 200
    item = client.get(f"/api/v1/inventory/products/{shelf}").json()
    assert (item["stock_quantity"], item["reserved"], item["available"]) == ("2", "4", "-2")
    assert client.get(f"/api/v1/sales/orders/{first['id']}").json()["stock_check"] == []
    assert act(client, second["id"], "fulfil").status_code == 409


def test_company_rules_create_income_and_tasks_once(client, database: str) -> None:
    workspace(client, ["customers", "sales", "finance", "tasks"])
    buyer = customer(client, "Kural Müşterisi")
    template = client.post(
        "/api/v1/tasks/templates",
        headers=csrf(client),
        json={"name": "Sipariş hazırlığı", "items": [{"title": "Malzemeyi ayır", "offset_days": 0}, {"title": "Sevkiyatı planla", "offset_days": 1, "depends_on": [0]}]},
    ).json()
    assert client.get("/api/v1/sales/rules").json()["income_on"] == "off"
    bad = client.put("/api/v1/sales/rules", headers=csrf(client), json={"income_on": "confirmed", "confirm_template_id": str(uuid4())})
    assert bad.status_code == 422
    saved = client.put(
        "/api/v1/sales/rules", headers=csrf(client), json={"income_on": "confirmed", "income_due_days": 30, "confirm_template_id": template["id"]}
    ).json()
    assert saved["confirm_template_name"] == "Sipariş hazırlığı" and saved["finance_on"] and saved["tasks_on"]

    order = create(client, buyer, [line(unit_price="250", vat_rate=20)]).json()
    confirmed = act(client, order["id"], "confirm").json()
    assert len(confirmed["automation"]) == 2 and "Gelir kaydı" in confirmed["automation"][0]
    income = records(client, order["id"])
    assert len(income) == 1 and income[0]["amount"] == "300.00" and income[0]["status"] == "pending"
    assert income[0]["due_date"] == (company_today(database) + timedelta(days=30)).isoformat()
    tasks = client.get("/api/v1/tasks", params={"order": order["id"]}).json()["items"]
    assert sorted(task["title"] for task in tasks) == ["Malzemeyi ayır", "Sevkiyatı planla"]

    cancelled = act(client, order["id"], "cancel").json()
    assert any("iptal edildi" in note for note in cancelled["automation"])
    assert records(client, order["id"])[0]["status"] == "cancelled"
    assert len(client.get("/api/v1/tasks", params={"order": order["id"]}).json()["items"]) == 2

    client.put("/api/v1/sales/rules", headers=csrf(client), json={"income_on": "fulfilled"})
    later = create(client, buyer, [line()]).json()
    assert act(client, later["id"], "confirm").json()["automation"] == []
    assert records(client, later["id"]) == []
    fulfilled = act(client, later["id"], "fulfil").json()
    assert fulfilled["automation"] and len(records(client, later["id"])) == 1

    record = records(client, later["id"])[0]
    paid = {
        "kind": "income",
        "category": "Satış",
        "description": record["description"],
        "amount": record["amount"],
        "currency": "TRY",
        "record_date": record["record_date"],
        "status": "paid",
        "paid_on": date.today().isoformat(),
        "customer_id": buyer,
    }
    assert client.put(f"/api/v1/finance/records/{record['id']}", headers=csrf(client), json=paid).status_code == 200
    kept = act(client, later["id"], "cancel").json()
    assert any("Ödenmiş" in note for note in kept["automation"])
    assert records(client, later["id"])[0]["status"] == "paid"

    feed = client.get("/api/v1/activity", params={"module": "sales"}).json()["items"]
    assert any(item["action"] == "order.rules_applied" for item in feed)
