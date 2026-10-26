from test_auth import csrf
from test_modules import sign_in_new_company
from test_sales import act, create, customer, product


def workspace(client, modules: list[str]) -> None:
    sign_in_new_company(client, "Reçete Atölyesi")
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": modules}).status_code == 200


def recipe(client, product_id: str, items: list[tuple[str, str]]):
    return client.put(
        f"/api/v1/production/recipes/{product_id}", headers=csrf(client), json={"items": [{"product_id": pid, "quantity": qty} for pid, qty in items]}
    )


def item(client, product_id: str) -> dict:
    return client.get(f"/api/v1/inventory/products/{product_id}").json()


def test_recipes_fill_materials_and_reject_loops(client) -> None:
    workspace(client, ["inventory", "production"])
    table = product(client, stock="0", name="Masa")
    top = product(client, stock="10", name="Tabla")
    plywood = product(client, stock="10", name="Kontrplak")
    lacquer = product(client, stock="5", name="Lake", unit="lt")

    assert recipe(client, table, [(table, "1")]).status_code == 422
    assert recipe(client, table, [(plywood, "1"), (plywood, "2")]).status_code == 422
    saved = recipe(client, table, [(top, "1"), (plywood, "0.5"), (lacquer, "0.25")]).json()
    assert [line["name"] for line in saved["items"]] == ["Tabla", "Kontrplak", "Lake"]
    assert recipe(client, top, [(plywood, "2")]).status_code == 200
    loop = recipe(client, plywood, [(table, "1")])
    assert loop.status_code == 409 and "döngü" in loop.json()["detail"]
    assert {row["name"] for row in client.get("/api/v1/production/recipes").json()} == {"Masa", "Tabla"}

    missing = client.post("/api/v1/production/orders", headers=csrf(client), json={"product_id": plywood, "quantity": "2"})
    assert missing.status_code == 422 and "reçete" in missing.json()["detail"]
    made = client.post("/api/v1/production/orders", headers=csrf(client), json={"product_id": table, "quantity": "3"})
    assert made.status_code == 201, made.text
    materials = {line["name"]: line["quantity"] for line in made.json()["materials"]}
    assert materials == {"Tabla": "3", "Kontrplak": "2", "Lake": "0.75"}

    assert (item(client, plywood)["reserved"], item(client, plywood)["available"]) == ("2", "8")
    assert item(client, table)["incoming"] == "3"
    assert recipe(client, table, []).json()["items"] == []


def test_shortage_rule_opens_linked_production_once(client) -> None:
    workspace(client, ["customers", "sales", "inventory", "production"])
    buyer = customer(client, "Eksik Mobilya")
    table = product(client, stock="2", name="Meşe masa")
    chair = product(client, stock="0", name="Sandalye")
    wood = product(client, stock="50", name="Meşe kereste", unit="m")
    assert recipe(client, table, [(wood, "2.5")]).status_code == 200
    rules = client.put("/api/v1/sales/rules", headers=csrf(client), json={"production_on_shortage": True}).json()
    assert rules["production_on_shortage"] is True and rules["production_on"] is True

    order = create(
        client,
        buyer,
        [{"product_id": table, "quantity": "5", "unit_price": "1000"}, {"product_id": chair, "quantity": "4", "unit_price": "300"}],
    ).json()
    confirmed = act(client, order["id"], "confirm").json()
    notes = " ".join(confirmed["automation"])
    assert "üretim emri açıldı: 3 adet Meşe masa" in notes and "Sandalye için reçete yok" in notes
    check = {line["name"]: line for line in confirmed["stock_check"]}
    assert check["Meşe masa"]["short"] == "3" and check["Meşe masa"]["incoming"] == "3"

    jobs = client.get("/api/v1/production/orders").json()["items"]
    assert len(jobs) == 1 and jobs[0]["sales_order_id"] == order["id"] and jobs[0]["sales_order_code"] == order["code"]
    detail = client.get(f"/api/v1/production/orders/{jobs[0]['id']}").json()
    assert detail["materials"][0]["quantity"] == "7.5"
    assert item(client, wood)["reserved"] == "7.5"

    feed = client.get("/api/v1/activity", params={"module": "production"}).json()["items"]
    assert any(entry["action"] == "production.created" and entry["detail"] == "Satış kuralıyla otomatik açıldı" for entry in feed)


def test_reorder_suggestions_explain_why(client) -> None:
    workspace(client, ["inventory", "production"])
    screws = product(client, stock="4", name="Vida", unit="kutu", minimum="10")
    glue = product(client, stock="20", name="Tutkal", unit="kg")
    table = product(client, stock="0", name="Masa", minimum="2")
    calm = product(client, stock="50", name="Boya", unit="lt", minimum="5")
    assert recipe(client, table, [(glue, "0.5")]).status_code == 200
    used = client.post(f"/api/v1/inventory/products/{glue}/movements", headers=csrf(client), json={"kind": "out", "quantity": "18"})
    assert used.status_code in {200, 201}, used.text

    suggestions = {row["name"]: row for row in client.get("/api/v1/inventory/reorder").json()}
    assert calm not in {row["product_id"] for row in suggestions.values()}
    assert suggestions["Vida"]["suggested"] == "6" and suggestions["Vida"]["action"] == "purchase"
    assert suggestions["Masa"]["action"] == "produce" and suggestions["Masa"]["suggested"] == "2"
    assert suggestions["Tutkal"]["days_left"] == 3 and suggestions["Tutkal"]["suggested"] == "16"
    assert any("Son 30 günde 18" in reason for reason in suggestions["Tutkal"]["reasons"])
