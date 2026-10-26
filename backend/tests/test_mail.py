import hashlib
import hmac
import json
import time
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from test_auth import account_payload, csrf
from test_team import accept, invite, open_workspace

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.services.mail import deliver_mail

MAIL_URL = "https://n8n.example.test/webhook/luminova-mail"
SECRET = "test-mail-secret-0123456789abcdef0123"
TEST_DSN = "postgresql://luminova:luminova@127.0.0.1:5433/luminova_test"


@pytest.fixture
def mail_on(monkeypatch):
    monkeypatch.setenv("MAIL_WEBHOOK_URL", MAIL_URL)
    monkeypatch.setenv("MAIL_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.luminova.test/")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def sign(timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def run_worker(handler) -> list[dict]:
    seen: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Luminova-Event"] == "mail.send"
        assert request.headers["X-Luminova-Signature"] == sign(request.headers["X-Luminova-Timestamp"], request.content)
        payload = json.loads(request.content)
        assert request.headers["X-Luminova-Delivery"] == payload["id"]
        seen.append(payload)
        return handler(payload)

    with get_sessionmaker()() as db, httpx.Client(transport=httpx.MockTransport(record)) as client:
        deliver_mail(db, limit=500, client=client)
    return seen


def row(message_id: str) -> tuple:
    with psycopg.connect(TEST_DSN) as connection:
        return connection.execute(
            "SELECT status, attempts, body_text IS NULL, provider_message_id, last_error FROM email_messages WHERE id = %s", (message_id,)
        ).fetchone()


def smtp_ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, json={"accepted": [payload["to"]], "rejected": [], "messageId": f"<{payload['id']}@smtp.test>"})


def test_register_and_reset_mails_go_to_n8n_signed(client, mail_on) -> None:
    email = f"{uuid4().hex[:8]}@example.com"
    created = client.post("/api/v1/auth/register", headers=csrf(client), json=account_payload(email)).json()
    assert created["email_sent"] is False and created["email_queued"] is True
    assert "doğrulama kodu" in created["message"] and "sıraya alındı" in created["message"]

    seen = run_worker(smtp_ok)
    mine = [item for item in seen if item["to"] == email]
    assert len(mine) == 1 and mine[0]["kind"] == "verify_email"
    token = created["verification_path"].split("token=", 1)[1]
    assert f"https://app.luminova.test/dogrula?token={token}" in mine[0]["text"]
    code = mine[0]["subject"].rsplit(" ", 1)[1]
    assert len(code) == 6 and code.isdigit() and code in mine[0]["text"] and code in mine[0]["html"]
    assert "E-postamı doğrula" in mine[0]["html"]
    status, attempts, cleared, provider_id, _ = row(mine[0]["id"])
    assert (status, attempts, cleared) == ("sent", 1, True)
    assert provider_id == f"<{mine[0]['id']}@smtp.test>"

    client.post("/api/v1/auth/verify-email", headers=csrf(client), json={"token": token})
    reset = client.post("/api/v1/auth/forgot-password", headers=csrf(client), json={"email": email}).json()
    unknown = client.post("/api/v1/auth/forgot-password", headers=csrf(client), json={"email": f"yok-{email}"}).json()
    assert reset["message"] == unknown["message"] and reset["email_queued"] is unknown["email_queued"] is True
    seen = run_worker(smtp_ok)
    assert [item["kind"] for item in seen if item["to"] == email] == ["password_reset"]
    assert not [item for item in seen if item["to"] == f"yok-{email}"]


def test_failures_retry_and_callback_reports_result(client, mail_on) -> None:
    email = f"{uuid4().hex[:8]}@example.com"
    client.post("/api/v1/auth/register", headers=csrf(client), json=account_payload(email))

    seen = run_worker(lambda payload: httpx.Response(502))
    message_id = next(item["id"] for item in seen if item["to"] == email)
    status, attempts, cleared, _, error = row(message_id)
    assert (status, attempts, cleared) == ("queued", 1, False) and "502" in error
    assert not [item for item in run_worker(smtp_ok) if item["id"] == message_id]

    with psycopg.connect(TEST_DSN) as connection:
        connection.execute("UPDATE email_messages SET next_attempt_at = now() WHERE id = %s", (message_id,))
    run_worker(lambda payload: httpx.Response(200, json={}))
    assert row(message_id)[0] == "handed_off"

    body = json.dumps({"id": message_id, "status": "failed", "error": "550 mailbox unavailable"}).encode()
    stamp = str(int(time.time()))
    forged = client.post("/api/v1/mail/callback", content=body, headers={"X-Luminova-Timestamp": stamp, "X-Luminova-Signature": "sha256=00"})
    assert forged.status_code == 401
    stale = str(int(time.time()) - 900)
    assert client.post("/api/v1/mail/callback", content=body, headers={"X-Luminova-Timestamp": stale, "X-Luminova-Signature": sign(stale, body)}).status_code == 401
    reported = client.post("/api/v1/mail/callback", content=body, headers={"X-Luminova-Timestamp": stamp, "X-Luminova-Signature": sign(stamp, body)})
    assert reported.status_code == 200 and reported.json()["status"] == "failed"
    status, _, cleared, _, error = row(message_id)
    assert status == "failed" and error == "550 mailbox unavailable" and cleared is False

    late = json.dumps({"id": message_id, "status": "sent"}).encode()
    assert client.post("/api/v1/mail/callback", content=late, headers={"X-Luminova-Timestamp": stamp, "X-Luminova-Signature": sign(stamp, late)}).json()["status"] == "failed"


def test_invitation_mail_status_and_notification_emails(client, mail_on) -> None:
    open_workspace(client, "Posta Atölyesi")
    prefs = client.get("/api/v1/notifications/preferences").json()
    assert all(item["email_available"] for item in prefs)
    assert {item["category"] for item in prefs if item["email"]} == {"inventory", "quotes", "team", "digest"}
    changed = client.put("/api/v1/notifications/preferences", headers=csrf(client), json={"email": {"team": True}}).json()
    team_pref = next(item for item in changed if item["category"] == "team")
    assert team_pref["email"] is True and team_pref["in_app"] is True

    guest = f"ece-{uuid4().hex[:8]}@example.com"
    created = invite(client, guest).json()
    assert created["email_queued"] is True
    assert client.get("/api/v1/team").json()["invitations"][0]["email_status"] == "queued"
    seen = run_worker(smtp_ok)
    letter = next(item for item in seen if item["to"] == guest)
    assert letter["kind"] == "invitation" and "Posta Atölyesi" in letter["subject"]
    assert client.get("/api/v1/team").json()["invitations"][0]["email_status"] == "sent"

    from app.main import create_app

    with TestClient(create_app()) as other:
        assert accept(other, created["invite_path"]).status_code == 201
    owner = client.get("/api/v1/auth/me").json()["email"]
    seen = run_worker(smtp_ok)
    notes = [item for item in seen if item["to"] == owner]
    assert len(notes) == 1 and notes[0]["kind"] == "notification"
    assert "Posta Atölyesi" in notes[0]["subject"]


def test_without_mail_channel_nothing_is_queued(client, monkeypatch) -> None:
    monkeypatch.setenv("MAIL_WEBHOOK_URL", "")
    get_settings.cache_clear()
    open_workspace(client, "Postasız Atölye")
    blocked = client.put("/api/v1/notifications/preferences", headers=csrf(client), json={"email": {"tasks": True}})
    assert blocked.status_code == 409
    guest = f"ece-{uuid4().hex[:8]}@example.com"
    created = invite(client, guest).json()
    assert created["email_queued"] is False and "gönderilmedi" in created["message"]
    with psycopg.connect(TEST_DSN) as connection:
        assert connection.execute("SELECT count(*) FROM email_messages WHERE to_email = %s", (guest,)).fetchone()[0] == 0


def test_production_mail_settings_are_checked(monkeypatch) -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    base = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://u:p@db:5432/luminova",
        "cors_origins": "https://app.example.com",
        "webhook_secret_key": "x" * 40,
        "public_app_url": "https://app.example.com",
    }
    with pytest.raises(ValidationError):
        Settings(**base, mail_webhook_url="http://n8n.internal/webhook/mail", mail_webhook_secret="y" * 40)
    with pytest.raises(ValidationError):
        Settings(**base, mail_webhook_url="https://n8n.example.com/webhook/mail", mail_webhook_secret="short")
    assert Settings(**base, mail_webhook_url="https://n8n.example.com/webhook/mail", mail_webhook_secret="y" * 40).mail_webhook_url
