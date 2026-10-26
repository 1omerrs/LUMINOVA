import base64
import io
import zipfile

from test_auth import csrf
from test_modules import sign_in_new_company


def workspace(client, modules: list[str] | None = None) -> None:
    sign_in_new_company(client, "Müşteri Merkezi")
    chosen = modules or ["sales", "tasks", "projects", "finance"]
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": chosen}).status_code == 200


def add(client, **fields) -> dict:
    response = client.post("/api/v1/customers", headers=csrf(client), json=fields)
    assert response.status_code == 201, response.text
    return response.json()


def encoded(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode()


def test_matches_report_email_phone_and_name(client) -> None:
    workspace(client, ["customers"])
    bora = add(client, name="Bora Yapı Ltd. Şti.", email="info@bora.com", phone="+90 532 111 22 33")
    add(client, name="Deniz Mimarlık")

    def reasons(**params) -> list[tuple[str, str]]:
        return [(row["name"], row["reason"]) for row in client.get("/api/v1/customers/matches", params=params).json()]

    assert reasons(name="Başka Firma", email="INFO@bora.com") == [("Bora Yapı Ltd. Şti.", "aynı e-posta")]
    assert reasons(name="X Firma", phone="0532 111 2233") == [("Bora Yapı Ltd. Şti.", "aynı telefon")]
    assert reasons(name="BORA YAPI") == [("Bora Yapı Ltd. Şti.", "aynı ad")]
    assert reasons(name="Deniz Mimarlk") == [("Deniz Mimarlık", "benzer ad")]
    assert reasons(name="Tamamen Farklı") == []
    assert reasons(name="Bora Yapı", exclude=bora["id"]) == []


def test_overview_collects_orders_tasks_projects_and_receivables(client) -> None:
    workspace(client)
    buyer = add(client, name="Kaya İnşaat")
    other = add(client, name="Başka Müşteri")
    order = client.post(
        "/api/v1/sales/orders",
        headers=csrf(client),
        json={"customer_id": buyer["id"], "order_date": "2026-10-20", "items": [{"description": "Montaj", "quantity": "2", "unit_price": "500"}]},
    ).json()
    client.post(f"/api/v1/sales/orders/{order['id']}/confirm", headers=csrf(client), json={})
    client.post("/api/v1/sales/orders", headers=csrf(client), json={"customer_id": other["id"], "order_date": "2026-10-20", "items": [{"description": "X", "quantity": "1", "unit_price": "9"}]})
    client.post("/api/v1/projects", headers=csrf(client), json={"name": "Ofis tadilatı", "customer_id": buyer["id"]})
    client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Keşif randevusu", "customer_id": buyer["id"]})
    client.post(
        "/api/v1/finance/records",
        headers=csrf(client),
        json={"kind": "income", "category": "Satış", "description": "Montaj bedeli", "amount": "1200", "record_date": "2026-10-20", "due_date": "2026-10-01", "customer_id": buyer["id"]},
    )

    body = client.get(f"/api/v1/customers/{buyer['id']}/overview").json()
    overview = body["overview"]
    assert body["customer"]["name"] == "Kaya İnşaat"
    assert overview["order_count"] == 1 and overview["open_orders"] == 1
    assert overview["revenue"] == [{"currency": "TRY", "amount": "1200.00"}]
    assert [o["status_label"] for o in overview["orders"]] == ["Onaylandı"]
    assert [p["code"] for p in overview["projects"]] == ["Ofis tadilatı"]
    assert [t["title"] for t in overview["open_tasks"]] == ["Keşif randevusu"]
    assert overview["finance"]["receivable"] == [{"currency": "TRY", "amount": "1200.00"}] and overview["finance"]["overdue"] == 1
    assert overview["timeline"][-1]["label"] == "Müşteri kaydı açıldı"


def test_overview_hides_disabled_modules_and_other_companies(client) -> None:
    workspace(client, ["customers"])
    mine = add(client, name="Yalnız Müşteri")
    overview = client.get(f"/api/v1/customers/{mine['id']}/overview").json()["overview"]
    assert overview["orders"] == [] and overview["finance"] is None and "sales" not in overview["enabled"]
    client.post("/api/v1/auth/logout", headers=csrf(client))
    workspace(client, ["customers"])
    assert client.get(f"/api/v1/customers/{mine['id']}/overview").status_code == 404


def test_csv_import_maps_validates_and_skips_duplicates(client) -> None:
    workspace(client, ["customers"])
    add(client, name="Mevcut Firma", email="mevcut@firma.com")
    csv_text = "Firma Adı;E-posta;Telefon;Açıklama\n" "Yeni Firma;yeni@firma.com;0212 555 11 22;Fuar\n" "Mevcut Firma A.Ş.;;;\n" "Diğer;MEVCUT@firma.com;;\n" "Kopya;yeni@firma.com;;\n" "X;bozuk-eposta;;\n" ";;;\n" "Son Firma;son@firma.com;;\n"
    file = {"filename": "musteriler.csv", "content": encoded(csv_text)}

    preview = client.post("/api/v1/customers/import/preview", headers=csrf(client), json=file).json()
    assert preview["headers"] == ["Firma Adı", "E-posta", "Telefon", "Açıklama"]
    assert preview["mapping"] == {"name": 0, "email": 1, "phone": 2, "note": 3}
    assert preview["total_rows"] == 6

    checked = client.post("/api/v1/customers/import", headers=csrf(client), json={**file, "mapping": preview["mapping"], "dry_run": True}).json()
    assert checked["valid"] == 2 and checked["created"] == 0
    assert [(d["row"], d["reason"]) for d in checked["duplicates"]] == [(3, "aynı ad"), (4, "aynı e-posta"), (5, "dosyada 2. satırla aynı")]
    assert [e["row"] for e in checked["errors"]] == [6]
    assert client.get("/api/v1/customers").json()["total"] == 1

    done = client.post("/api/v1/customers/import", headers=csrf(client), json={**file, "mapping": preview["mapping"], "dry_run": False}).json()
    assert done["created"] == 2
    names = sorted(item["name"] for item in client.get("/api/v1/customers").json()["items"])
    assert names == ["Mevcut Firma", "Son Firma", "Yeni Firma"]
    again = client.post("/api/v1/customers/import", headers=csrf(client), json={**file, "mapping": preview["mapping"], "dry_run": False}).json()
    assert again["created"] == 0
    assert client.get("/api/v1/activity", params={"module": "customers"}).json()["items"][0]["verb"] == "müşteri listesi aktardı"
    assert client.post("/api/v1/customers/import", headers=csrf(client), json={**file, "mapping": {"email": 1}, "dry_run": True}).status_code == 422


def test_xlsx_import_reads_shared_strings(client) -> None:
    workspace(client, ["customers"])
    shared = '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Müşteri</t></si><si><t>Telefon</t></si><si><t>Excel Ltd</t></si></sst>'
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>5321112233</v></c></row>'
        "</sheetData></worksheet>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("xl/sharedStrings.xml", shared)
        book.writestr("xl/worksheets/sheet1.xml", sheet)
    file = {"filename": "liste.xlsx", "content": base64.b64encode(buffer.getvalue()).decode()}
    preview = client.post("/api/v1/customers/import/preview", headers=csrf(client), json=file).json()
    assert preview["headers"] == ["Müşteri", "Telefon"] and preview["sample"] == [["Excel Ltd", "5321112233"]]
    done = client.post("/api/v1/customers/import", headers=csrf(client), json={**file, "mapping": preview["mapping"], "dry_run": False}).json()
    assert done["created"] == 1
    assert client.post("/api/v1/customers/import/preview", headers=csrf(client), json={"filename": "x.csv", "content": encoded("Ad\n")}).status_code == 422
