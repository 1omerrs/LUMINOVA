from datetime import timedelta

import psycopg
from test_auth import csrf
from test_modules import PASSWORD, sign_in_new_company
from test_sales import customer, product
from test_tasks import company_today


def open_finance(client, company: str = "Finans Atölyesi", extra: list[str] | None = None) -> str:
    email = sign_in_new_company(client, company)
    modules = ["finance", *(extra or [])]
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": modules}).status_code == 200
    return email


def record(client, **fields):
    body = {"kind": "expense", "category": "Kira", "description": "Ekim kirası", "amount": "15000", "record_date": "2026-10-01", **fields}
    return client.post("/api/v1/finance/records", headers=csrf(client), json=body)


def test_finance_needs_the_module(client) -> None:
    assert client.get("/api/v1/finance/records").status_code == 401
    sign_in_new_company(client)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["tasks"]}).status_code == 200
    assert client.get("/api/v1/finance/summary").status_code == 403


def test_validation_and_categories(client) -> None:
    open_finance(client)
    categories = client.get("/api/v1/finance/categories").json()
    assert "Satış" in categories["income"] and "Kira" in categories["expense"]
    wrong = record(client, kind="income", category="Kira")
    assert wrong.status_code == 422
    assert wrong.json()["detail"][0]["msg"] == "Bu kayıt türü için geçerli bir kategori seçin."
    assert record(client, amount="0").status_code == 422
    assert record(client, amount="10.999").status_code == 422
    assert record(client, currency="GBP").status_code == 422
    assert record(client, description="x").status_code == 422


def test_status_changes_keep_a_revision_history(client, database: str) -> None:
    open_finance(client)
    today = company_today(database)
    created = record(client, description="  Ekim   kirası ", counterparty="Mülk sahibi", due_date=str(today - timedelta(days=3)))
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["description"] == "Ekim kirası"
    assert item["status"] == "pending" and item["overdue"] is True
    assert [rev["action"] for rev in item["revisions"]] == ["created"]

    body = {
        "kind": "expense",
        "category": "Kira",
        "description": "Ekim kirası",
        "counterparty": "Mülk sahibi",
        "amount": "15500.50",
        "record_date": "2026-10-01",
        "due_date": str(today - timedelta(days=3)),
        "status": "paid",
    }
    paid = client.put(f"/api/v1/finance/records/{item['id']}", headers=csrf(client), json=body).json()
    assert paid["status"] == "paid"
    assert paid["paid_on"] == str(today)
    assert paid["overdue"] is False
    assert paid["amount"] == "15500.50"
    update = paid["revisions"][-1]
    assert update["action"] == "updated"
    assert update["changes"]["amount"] == {"from": "15000.00", "to": "15500.50"}
    assert update["changes"]["status"] == {"from": "pending", "to": "paid"}
    assert client.put(f"/api/v1/finance/records/{item['id']}", headers=csrf(client), json=body).json()["revisions"] == paid["revisions"]

    assert client.post(f"/api/v1/finance/records/{item['id']}/cancel", headers=csrf(client), json={"reason": "x"}).status_code == 422
    cancelled = client.post(f"/api/v1/finance/records/{item['id']}/cancel", headers=csrf(client), json={"reason": "Yanlış girildi"}).json()
    assert cancelled["status"] == "cancelled" and cancelled["paid_on"] is None
    assert cancelled["cancel_reason"] == "Yanlış girildi"
    assert [rev["action"] for rev in cancelled["revisions"]] == ["created", "updated", "cancelled"]
    assert client.put(f"/api/v1/finance/records/{item['id']}", headers=csrf(client), json=body).status_code == 409
    assert client.post(f"/api/v1/finance/records/{item['id']}/cancel", headers=csrf(client), json={"reason": "Tekrar"}).status_code == 409

    with psycopg.connect(database) as connection:
        kept = connection.execute("SELECT count(*) FROM financial_records WHERE id = %s", (item["id"],)).fetchone()
    assert kept == (1,)


def test_summary_by_period_and_currency(client, database: str) -> None:
    open_finance(client)
    today = company_today(database)
    first = today.replace(day=1)
    last_month = first - timedelta(days=1)
    record(client, kind="income", category="Satış", description="Masa satışı", amount="12000", record_date=str(first), status="paid")
    record(client, kind="income", category="Hizmet", description="Montaj", amount="3000", record_date=str(first), due_date=str(today - timedelta(days=1)))
    record(client, kind="expense", category="Malzeme", description="Kereste", amount="4500.25", record_date=str(today))
    record(client, kind="income", category="Satış", description="İhracat", amount="800", currency="EUR", record_date=str(first))
    record(client, kind="expense", category="Kira", description="Geçen ay kira", amount="9999", record_date=str(last_month), status="paid")
    voided = record(client, kind="income", category="Satış", description="İptal", amount="50000", record_date=str(first)).json()
    client.post(f"/api/v1/finance/records/{voided['id']}/cancel", headers=csrf(client), json={"reason": "Mükerrer"})

    summary = client.get("/api/v1/finance/summary").json()
    assert summary["period_from"] == str(first)
    assert summary["overdue_receivables"] == 1 and summary["overdue_payables"] == 0
    by_currency = {row["currency"]: row for row in summary["totals"]}
    assert list(by_currency) == ["TRY", "EUR"]
    assert by_currency["TRY"] == {"currency": "TRY", "income": "15000.00", "expense": "4500.25", "net": "10499.75", "receivable": "3000.00", "payable": "4500.25"}
    assert by_currency["EUR"]["income"] == "800.00" and by_currency["EUR"]["receivable"] == "800.00"

    previous = client.get("/api/v1/finance/summary", params={"from": str(last_month.replace(day=1)), "to": str(last_month)}).json()
    assert previous["totals"][0]["expense"] == "9999.00"
    assert client.get("/api/v1/finance/summary", params={"from": str(today), "to": str(first - timedelta(days=40))}).status_code == 422

    page = client.get("/api/v1/finance/records", params={"from": str(first), "to": str(today), "kind": "income"}).json()
    assert {item["description"] for item in page["items"]} == {"Masa satışı", "Montaj", "İhracat", "İptal"}
    assert [item["description"] for item in client.get("/api/v1/finance/records", params={"overdue": "true"}).json()["items"]] == ["Montaj"]
    assert [item["description"] for item in client.get("/api/v1/finance/records", params={"q": "KERESTE"}).json()["items"]] == ["Kereste"]


def test_an_order_links_to_one_income_record(client) -> None:
    open_finance(client, extra=["sales"])
    buyer = customer(client, "Deniz Yapı")
    table = product(client, stock="5")
    order = client.post(
        "/api/v1/sales/orders",
        headers=csrf(client),
        json={"customer_id": buyer, "order_date": "2026-10-23", "items": [{"product_id": table, "quantity": "2", "unit_price": "1000"}]},
    ).json()

    linked = {"kind": "income", "category": "Satış", "description": "SP-0001 siparişi", "amount": order["total"], "record_date": "2026-10-23", "customer_id": buyer, "order_id": order["id"]}
    early = client.post("/api/v1/finance/records", headers=csrf(client), json=linked)
    assert early.status_code == 409
    client.post(f"/api/v1/sales/orders/{order['id']}/confirm", headers=csrf(client))
    assert client.post("/api/v1/finance/records", headers=csrf(client), json={**linked, "kind": "expense", "category": "Malzeme"}).status_code == 422

    first = client.post("/api/v1/finance/records", headers=csrf(client), json=linked)
    assert first.status_code == 201, first.text
    assert first.json()["order_code"] == "SP-0001"
    assert first.json()["customer_name"] == "Deniz Yapı"
    second = client.post("/api/v1/finance/records", headers=csrf(client), json=linked)
    assert second.status_code == 409
    assert second.json()["detail"] == "Bu sipariş için zaten bir gelir kaydı var."
    assert [item["id"] for item in client.get("/api/v1/finance/records", params={"order_id": order["id"]}).json()["items"]] == [first.json()["id"]]

    client.post(f"/api/v1/finance/records/{first.json()['id']}/cancel", headers=csrf(client), json={"reason": "Tutar hatalı"})
    assert client.post("/api/v1/finance/records", headers=csrf(client), json=linked).status_code == 201


def test_records_stay_in_their_company(client) -> None:
    first = open_finance(client, "Birinci Finans")
    owned = record(client).json()
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    open_finance(client, "İkinci Finans")
    assert client.get("/api/v1/finance/records").json()["total"] == 0
    assert client.get(f"/api/v1/finance/records/{owned['id']}").status_code == 404
    assert client.post(f"/api/v1/finance/records/{owned['id']}/cancel", headers=csrf(client), json={"reason": "Sızma"}).status_code == 404
    assert client.get("/api/v1/finance/summary").json()["totals"][0]["expense"] == "0.00"
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": first, "password": PASSWORD}).status_code == 200
    assert client.get(f"/api/v1/finance/records/{owned['id']}").json()["status"] == "pending"
