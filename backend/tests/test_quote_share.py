from datetime import timedelta
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from test_auth import csrf
from test_mail import TEST_DSN, mail_on  # noqa: F401
from test_quotes import create, setup
from test_tasks import company_today


def buyer(client, email: str | None) -> str:
    body = {"name": "Kaya Ailesi", **({"email": email} if email else {})}
    response = client.post("/api/v1/customers", headers=csrf(client), json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def draft(client, customer_id: str, **extra) -> dict:
    today = company_today(TEST_DSN)
    items = [{"description": "Mutfak dolabı", "quantity": "2", "unit_price": "12500", "vat_rate": 20}]
    body = {"quote_date": today.isoformat(), "valid_until": (today + timedelta(days=14)).isoformat(), **extra}
    response = create(client, customer_id, items, **body)
    assert response.status_code == 201, response.text
    return response.json()


def send(client, quote_id: str, **body):
    return client.post(f"/api/v1/quotes/{quote_id}/send", headers=csrf(client), json=body or None)


def token(path: str) -> str:
    return path.rsplit("/", 1)[1]


def test_sent_quote_is_mailed_and_the_customer_decides(client, mail_on) -> None:  # noqa: F811
    owner = setup(client, ["customers", "sales"], "Teklif Postası")
    customer_email = f"kaya-{uuid4().hex[:6]}@example.com"
    quote = draft(client, buyer(client, customer_email), note="Montaj dahildir.")

    sent = send(client, quote["id"], message="Konuştuğumuz gibi ölçüye göre hazırladık.").json()
    assert sent["status"] == "sent" and sent["share_path"].startswith("/teklif/")
    assert sent["email_notice"] == f"Teklif e-postası {customer_email} adresine gönderim sırasına alındı."
    assert sent["email_status"] == "queued"
    with psycopg.connect(TEST_DSN) as connection:
        subject, reply_to, text = connection.execute(
            "SELECT subject, reply_to, body_text FROM email_messages WHERE kind = 'quote' AND to_email = %s", (customer_email,)
        ).fetchone()
    assert subject == "Teklif Postası teklifi · TK-0001" and reply_to == owner
    assert f"https://app.luminova.test{sent['share_path']}" in text
    assert "Konuştuğumuz gibi ölçüye göre hazırladık." in text and "₺30.000,00" in text

    secret = token(sent["share_path"])
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        assert visitor.get("/api/v1/public/quotes/" + "x" * 40).status_code == 404
        page = visitor.get(f"/api/v1/public/quotes/{secret}").json()
        assert page["company_name"] == "Teklif Postası" and page["code"] == "TK-0001" and page["can_decide"] is True
        assert page["total"] == "30000.00" and page["note"] == "Montaj dahildir." and page["items"][0]["description"] == "Mutfak dolabı"
        decided = visitor.post(f"/api/v1/public/quotes/{secret}/decision", headers=csrf(visitor), json={"decision": "accept", "note": "Cuma kurulum olsun."})
        assert decided.status_code == 200 and decided.json()["status"] == "accepted" and decided.json()["can_decide"] is False
        again = visitor.post(f"/api/v1/public/quotes/{secret}/decision", headers=csrf(visitor), json={"decision": "accept"})
        assert again.status_code == 200
        changed = visitor.post(f"/api/v1/public/quotes/{secret}/decision", headers=csrf(visitor), json={"decision": "reject"})
        assert changed.status_code == 409

    detail = client.get(f"/api/v1/quotes/{quote['id']}").json()
    assert detail["decided_by"] == "customer" and detail["customer_note"] == "Cuma kurulum olsun."
    notes = [item for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "quotes"]
    assert notes[0]["title"] == "Kaya Ailesi, TK-0001 teklifini kabul etti."
    assert "Cuma kurulum olsun." in notes[0]["body"] and notes[0]["link"].endswith(quote["id"])
    feed = client.get("/api/v1/activity").json()["items"]
    entry = next(item for item in feed if item["action"] == "quote.accepted_by_customer")
    assert entry["actor_name"] == "Kaya Ailesi" and entry["verb"] == "teklifi kabul etti"
    assert client.post(f"/api/v1/quotes/{quote['id']}/convert", headers=csrf(client)).status_code == 200


def test_resend_replaces_the_link_and_missing_email_is_reported(client, mail_on) -> None:  # noqa: F811
    setup(client, ["customers"], "Bağlantı Atölyesi")
    quiet = draft(client, buyer(client, None))
    sent = send(client, quiet["id"]).json()
    assert sent["email_notice"].startswith("Müşterinin e-posta adresi kayıtlı değil")
    assert sent["email_status"] is None

    renewed = client.post(f"/api/v1/quotes/{quiet['id']}/resend", headers=csrf(client), json={"email": False}).json()
    assert renewed["share_path"] != sent["share_path"] and renewed["email_notice"] is None
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        assert visitor.get(f"/api/v1/public/quotes/{token(sent['share_path'])}").status_code == 404
        rejected = visitor.post(f"/api/v1/public/quotes/{token(renewed['share_path'])}/decision", headers=csrf(visitor), json={"decision": "reject"})
        assert rejected.json()["status"] == "rejected"
    assert client.post(f"/api/v1/quotes/{quiet['id']}/resend", headers=csrf(client), json={}).status_code == 409


def test_expired_quote_cannot_be_decided(client) -> None:
    setup(client, ["customers"], "Süre Atölyesi")
    today = company_today(TEST_DSN)
    old = draft(client, buyer(client, None), quote_date=(today - timedelta(days=20)).isoformat(), valid_until=(today - timedelta(days=5)).isoformat())
    sent = send(client, old["id"]).json()
    assert sent["email_notice"].startswith("E-posta servisi yapılandırılmadığı için") or sent["email_notice"].startswith("Müşterinin e-posta adresi")
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        secret = token(sent["share_path"])
        page = visitor.get(f"/api/v1/public/quotes/{secret}").json()
        assert page["expired"] is True and page["can_decide"] is False
        late = visitor.post(f"/api/v1/public/quotes/{secret}/decision", headers=csrf(visitor), json={"decision": "accept"})
        assert late.status_code == 409 and "geçerlilik süresi dolmuş" in late.json()["detail"]
