from datetime import timedelta
from uuid import uuid4

from test_auth import csrf
from test_modules import PASSWORD, sign_in_new_company
from test_sales import customer, product
from test_tasks import company_today


def setup(client, modules: list[str], company: str = "Teklif Atölyesi") -> str:
    email = sign_in_new_company(client, company)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": modules}).status_code == 200
    return email


def create(client, customer_id: str, items: list[dict], **extra):
    return client.post("/api/v1/quotes", headers=csrf(client), json={"customer_id": customer_id, "quote_date": "2026-10-23", "items": items, **extra})


def act(client, quote_id: str, action: str):
    return client.post(f"/api/v1/quotes/{quote_id}/{action}", headers=csrf(client))


def test_quote_flow_and_validation(client, database: str) -> None:
    assert client.get("/api/v1/quotes").status_code == 401
    setup(client, ["customers"])
    buyer = customer(client, "Deniz Yapı")

    assert create(client, buyer, []).status_code == 422
    assert create(client, str(uuid4()), [{"description": "Montaj", "quantity": "1", "unit_price": "10"}]).json()["detail"] == "Seçilen müşteri bulunamadı."
    backwards = create(client, buyer, [{"description": "Montaj", "quantity": "1", "unit_price": "10"}], valid_until="2026-10-01")
    assert backwards.json()["detail"][0]["msg"] == "Geçerlilik tarihi teklif tarihinden önce olamaz."

    today = company_today(database)
    created = create(
        client,
        buyer,
        [{"description": "Ofis tasarımı", "quantity": "2", "unit_price": "1500", "vat_rate": 20}, {"description": "Keşif", "quantity": "1", "unit_price": "250.50", "vat_rate": 0}],
        quote_date=str(today - timedelta(days=10)),
        valid_until=str(today - timedelta(days=1)),
        note="  İlk görüşme  ",
    )
    assert created.status_code == 201, created.text
    quote = created.json()
    assert quote["code"] == "TK-0001" and quote["status"] == "draft"
    assert (quote["subtotal"], quote["vat_total"], quote["total"]) == ("3250.50", "600.00", "3850.50")
    assert quote["note"] == "İlk görüşme" and quote["expired"] is False

    assert act(client, quote["id"], "accept").status_code == 409
    sent = act(client, quote["id"], "send").json()
    assert sent["status"] == "sent" and sent["sent_at"] is not None and sent["expired"] is True
    edit = client.put(f"/api/v1/quotes/{quote['id']}", headers=csrf(client), json={"customer_id": buyer, "quote_date": "2026-10-23", "items": [{"description": "X", "quantity": "1", "unit_price": "1"}]})
    assert edit.status_code == 409
    accepted = act(client, quote["id"], "accept").json()
    assert accepted["status"] == "accepted" and accepted["decided_at"] is not None

    blocked = act(client, quote["id"], "convert")
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Teklifi siparişe çevirmek için Satış ve Siparişler modülünü açın."

    second = create(client, buyer, [{"description": "Ek iş", "quantity": "1", "unit_price": "100"}]).json()
    act(client, second["id"], "send")
    assert act(client, second["id"], "reject").json()["status"] == "rejected"
    assert act(client, second["id"], "convert").status_code == 403

    summary = client.get("/api/v1/quotes/summary").json()
    assert summary == {"draft": 0, "sent": 0, "accepted": 1, "rejected": 1, "open_value": "0.00"}
    assert [item["code"] for item in client.get("/api/v1/quotes", params={"q": "tk-2"}).json()["items"]] == ["TK-0002"]
    assert [item["code"] for item in client.get("/api/v1/quotes", params={"status": "accepted"}).json()["items"]] == ["TK-0001"]


def test_accepted_quote_converts_once_to_an_order(client) -> None:
    setup(client, ["sales"])
    buyer = customer(client, "Bora Tekstil")
    table = product(client, stock="5", name="Masa")
    quote = create(client, buyer, [{"product_id": table, "quantity": "2", "unit_price": "1000"}, {"description": "Kurulum", "quantity": "1", "unit_price": "200", "vat_rate": 10}], note="Hızlı teslim").json()
    assert quote["items"][0]["description"] == "Masa"
    assert act(client, quote["id"], "convert").status_code == 409

    act(client, quote["id"], "send")
    act(client, quote["id"], "accept")
    converted = act(client, quote["id"], "convert")
    assert converted.status_code == 200, converted.text
    body = converted.json()
    assert body["order_code"] == "SP-0001"
    assert act(client, quote["id"], "convert").json()["detail"] == "Bu teklif zaten siparişe çevrildi."

    order = client.get(f"/api/v1/sales/orders/{body['order_id']}").json()
    assert order["status"] == "draft" and order["customer_name"] == "Bora Tekstil"
    assert order["total"] == quote["total"] == "2620.00"
    assert [(line["description"], line["product_id"]) for line in order["items"]] == [("Masa", table), ("Kurulum", None)]
    assert order["note"].startswith("TK-0001 teklifinden oluşturuldu.")
    assert client.get("/api/v1/inventory/products/" + table).json()["stock_quantity"] == "5"


def test_quotes_stay_in_their_company(client) -> None:
    first = setup(client, ["customers"], "Birinci Teklif")
    owned = create(client, customer(client), [{"description": "Gizli", "quantity": "1", "unit_price": "1"}]).json()
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    setup(client, ["customers"], "İkinci Teklif")
    assert client.get("/api/v1/quotes").json()["total"] == 0
    assert client.get(f"/api/v1/quotes/{owned['id']}").status_code == 404
    assert act(client, owned["id"], "send").status_code == 404
    assert create(client, customer(client), [{"description": "Benim", "quantity": "1", "unit_price": "1"}]).json()["code"] == "TK-0001"
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": first, "password": PASSWORD}).status_code == 200
    assert client.get(f"/api/v1/quotes/{owned['id']}").json()["status"] == "draft"
