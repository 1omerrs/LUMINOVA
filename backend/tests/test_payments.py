from datetime import timedelta

from test_auth import csrf
from test_modules import sign_in_new_company
from test_sales import customer
from test_tasks import company_today


def workspace(client) -> None:
    sign_in_new_company(client, "Tahsilat Atölyesi")
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["finance", "customers"]}).status_code == 200


def record(client, **extra) -> dict:
    body = {"kind": "income", "category": "Satış", "description": "Mutfak dolabı", "amount": "1000", "record_date": extra.pop("record_date"), **extra}
    response = client.post("/api/v1/finance/records", headers=csrf(client), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def pay(client, record_id: str, amount: str, day, method: str = "transfer"):
    return client.post(f"/api/v1/finance/records/{record_id}/payments", headers=csrf(client), json={"amount": amount, "paid_on": day.isoformat(), "method": method})


def test_partial_payments_drive_status_and_remaining(client, database: str) -> None:
    workspace(client)
    today = company_today(database)
    item = record(client, record_date=(today - timedelta(days=10)).isoformat(), due_date=(today - timedelta(days=1)).isoformat())
    assert (item["status"], item["remaining"], item["overdue"]) == ("pending", "1000.00", True)

    first = pay(client, item["id"], "400", today, "cash").json()
    assert (first["status"], first["paid_amount"], first["remaining"], first["overdue"]) == ("partial", "400.00", "600.00", True)
    assert first["payments"][0]["method"] == "cash" and first["paid_on"] is None
    too_much = pay(client, item["id"], "700", today)
    assert too_much.status_code == 422 and "600.00" in too_much.json()["detail"]
    assert pay(client, item["id"], "10", today + timedelta(days=1)).status_code == 422

    done = pay(client, item["id"], "600", today).json()
    assert (done["status"], done["remaining"], done["paid_on"]) == ("paid", "0.00", today.isoformat())
    assert pay(client, item["id"], "1", today).status_code == 409
    assert [revision["action"] for revision in done["revisions"]] == ["created", "payment_added", "payment_added"]

    reopened = client.delete(f"/api/v1/finance/records/{item['id']}/payments/{done['payments'][1]['id']}", headers=csrf(client)).json()
    assert (reopened["status"], reopened["remaining"]) == ("partial", "600.00")

    edit = {
        "kind": "income",
        "category": "Satış",
        "description": "Mutfak dolabı",
        "amount": "300",
        "record_date": item["record_date"],
        "status": "pending",
    }
    lower = client.put(f"/api/v1/finance/records/{item['id']}", headers=csrf(client), json=edit)
    assert lower.status_code == 422 and "400.00" in lower.json()["detail"]
    settled = client.put(f"/api/v1/finance/records/{item['id']}", headers=csrf(client), json={**edit, "amount": "1000", "status": "paid", "paid_on": today.isoformat()}).json()
    assert settled["status"] == "paid" and [payment["amount"] for payment in settled["payments"]] == ["400.00", "600.00"]
    cleared = client.put(f"/api/v1/finance/records/{item['id']}", headers=csrf(client), json={**edit, "amount": "1000"}).json()
    assert cleared["status"] == "pending" and cleared["payments"] == []

    paid_at_once = record(client, record_date=today.isoformat(), status="paid", paid_on=today.isoformat())
    assert paid_at_once["status"] == "paid" and len(paid_at_once["payments"]) == 1


def test_balances_due_lists_and_cashflow(client, database: str) -> None:
    workspace(client)
    today = company_today(database)
    buyer = customer(client, "Bakiye Mobilya")
    late = record(client, record_date=(today - timedelta(days=20)).isoformat(), due_date=(today - timedelta(days=5)).isoformat(), customer_id=buyer)
    record(client, record_date=today.isoformat(), due_date=(today + timedelta(days=9)).isoformat(), customer_id=buyer, amount="250")
    record(client, record_date=today.isoformat(), counterparty="Kapıdan müşteri", amount="80")
    client.post(
        "/api/v1/finance/records",
        headers=csrf(client),
        json={"kind": "expense", "category": "Kira", "description": "Kira", "amount": "500", "record_date": today.isoformat(), "due_date": (today + timedelta(days=2)).isoformat()},
    )
    assert pay(client, late["id"], "300", today).status_code == 201

    rows = {row["name"]: row for row in client.get("/api/v1/finance/balances").json()}
    assert rows["Bakiye Mobilya"]["open_amount"] == "950.00" and rows["Bakiye Mobilya"]["overdue_amount"] == "700.00"
    assert rows["Bakiye Mobilya"]["records"] == 2 and rows["Bakiye Mobilya"]["last_payment"] == today.isoformat()
    assert rows["Kapıdan müşteri"]["customer_id"] is None
    assert client.get("/api/v1/finance/balances").json()[0]["name"] == "Bakiye Mobilya"

    summary = client.get("/api/v1/finance/summary").json()["totals"][0]
    assert summary["receivable"] == "1030.00" and summary["payable"] == "500.00"

    due = client.get("/api/v1/finance/records", params={"kind": "income", "open": "true", "due_to": (today + timedelta(days=7)).isoformat(), "sort": "due_date"}).json()
    assert [item["remaining"] for item in due["items"]] == ["700.00"]
    mine = client.get("/api/v1/finance/records", params={"customer_id": buyer, "open": "true"}).json()
    assert mine["total"] == 2

    flow = client.get("/api/v1/finance/cashflow", params={"weeks": 4, "past": 1}).json()
    assert flow["overdue_in"] == "700.00" and flow["undated_in"] == "80.00"
    weeks = flow["weeks"]
    assert len(weeks) == 5
    this_week = next(week for week in weeks if week["week_start"] <= today.isoformat() <= week["week_end"])
    assert this_week["actual_in"] == "300.00"
    expected_in = sum(float(week["expected_in"]) for week in weeks)
    expected_out = sum(float(week["expected_out"]) for week in weeks)
    assert expected_in == 250 and expected_out == 500
    assert flow["cash_now"] is None

    future = client.put("/api/v1/finance/opening-balance", headers=csrf(client), json={"amount": "1000", "as_of": (today + timedelta(days=1)).isoformat()})
    assert future.status_code == 422
    opened = client.put("/api/v1/finance/opening-balance", headers=csrf(client), json={"amount": "1000", "as_of": (today - timedelta(days=1)).isoformat()}).json()
    assert opened["opening_amount"] == "1000.00" and opened["cash_now"] == "1300.00"
