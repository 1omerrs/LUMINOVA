from test_auth import csrf
from test_modules import sign_in_new_company
from test_sales import customer, product
from test_tasks import company_today


def setup(client, modules: list[str], company: str = "Rapor Atölyesi") -> None:
    sign_in_new_company(client, company)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": modules}).status_code == 200


def test_reports_need_the_module_and_follow_enabled_modules(client) -> None:
    assert client.get("/api/v1/reports/overview").status_code == 401
    setup(client, ["tasks"])
    assert client.get("/api/v1/reports/overview").status_code == 403

    client.put("/api/v1/modules", headers=csrf(client), json={"modules": ["tasks", "reporting"]})
    report = client.get("/api/v1/reports/overview", params={"months": 3}).json()
    assert len(report["months"]) == 3
    assert report["tasks"] is not None
    assert report["sales"] is None and report["finance"] is None and report["inventory"] is None
    assert [point["value"] for point in report["tasks"]["created"]] == ["0", "0", "0"]
    assert client.get("/api/v1/reports/overview", params={"months": 5}).status_code == 422


def test_overview_uses_real_records(client, database: str) -> None:
    setup(client, ["sales", "finance", "tasks", "projects", "production", "reporting"])
    today = company_today(database)
    this_month = today.strftime("%Y-%m")
    buyer = customer(client, "Deniz Yapı")
    other = customer(client, "Bora Tekstil")
    table = product(client, stock="10", name="Meşe Masa", minimum="9")

    def order(customer_id: str, price: str, currency: str = "TRY", confirm: bool = True) -> dict:
        created = client.post(
            "/api/v1/sales/orders",
            headers=csrf(client),
            json={"customer_id": customer_id, "currency": currency, "order_date": str(today), "items": [{"product_id": table, "quantity": "2", "unit_price": price, "vat_rate": 0}]},
        ).json()
        if confirm:
            client.post(f"/api/v1/sales/orders/{created['id']}/confirm", headers=csrf(client))
        return created

    order(buyer, "1000")
    order(other, "250")
    order(buyer, "400", currency="EUR")
    order(other, "99999", confirm=False)

    for body in (
        {"kind": "income", "category": "Satış", "description": "Tahsilat", "amount": "3000", "record_date": str(today), "status": "paid"},
        {"kind": "expense", "category": "Kira", "description": "Kira", "amount": "1200", "record_date": str(today)},
        {"kind": "expense", "category": "Malzeme", "description": "Kereste", "amount": "300.50", "record_date": str(today)},
    ):
        assert client.post("/api/v1/finance/records", headers=csrf(client), json=body).status_code == 201

    first = client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Bitti", "status": "done"}).json()
    client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Açık iş"})
    assert first["completed_at"] is not None

    report = client.get("/api/v1/reports/overview").json()
    assert report["months"][-1] == this_month and len(report["months"]) == 6

    sales = report["sales"]
    assert sales["revenue"][-1] == {"month": this_month, "value": "2500.00"}
    assert sales["orders"][-1]["value"] == "3"
    assert sales["total_revenue"] == "2500.00" and sales["average_order"] == "1250.00"
    assert sales["other_currency_orders"] == 1 and sales["open_orders"] == 4
    assert [row["label"] for row in sales["top_customers"]] == ["Deniz Yapı", "Bora Tekstil"]
    assert sales["top_products"] == [{"label": "Meşe Masa", "value": "6 adet", "detail": None}]

    finance = report["finance"]
    assert (finance["total_income"], finance["total_expense"], finance["net"]) == ("3000.00", "1500.50", "1499.50")
    assert finance["payable"] == "1500.50" and finance["receivable"] == "0.00"
    assert [row["label"] for row in finance["expense_categories"]] == ["Kira", "Malzeme"]

    assert report["inventory"]["products"] == 1 and report["inventory"]["low"] == 0
    assert report["inventory"]["movements_in"][-1]["value"] == "1"
    assert report["tasks"]["open"] == 1 and report["tasks"]["completion_rate"] == 50
    assert report["customers"]["total"] == 2 and report["customers"]["new"][-1]["value"] == "2"
    assert report["projects"]["active"] == 0 and report["production"]["open"] == 0


def test_reports_stay_in_their_company(client) -> None:
    setup(client, ["sales", "reporting"], "Birinci Rapor")
    buyer = customer(client)
    created = client.post(
        "/api/v1/sales/orders",
        headers=csrf(client),
        json={"customer_id": buyer, "order_date": "2026-10-23", "items": [{"description": "Hizmet", "quantity": "1", "unit_price": "500"}]},
    ).json()
    client.post(f"/api/v1/sales/orders/{created['id']}/confirm", headers=csrf(client))
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    setup(client, ["sales", "reporting"], "İkinci Rapor")
    report = client.get("/api/v1/reports/overview").json()
    assert report["sales"]["total_revenue"] == "0.00"
    assert report["customers"]["total"] == 0
