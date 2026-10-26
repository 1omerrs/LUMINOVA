import hashlib
import hmac
import json
import time
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_auth import csrf
from test_modules import sign_in_new_company
from test_team import accept, invite

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.services.automation import deliver_due

HOOK_URL = "https://hooks.example.test/luminova"


def workspace(client, name: str, modules: list[str] | None = None) -> None:
    sign_in_new_company(client, name)
    chosen = modules or ["automation", "customers", "tasks"]
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": chosen}).status_code == 200


def outbound(client, events: list[str], url: str = HOOK_URL):
    return client.post("/api/v1/automation/endpoints", headers=csrf(client), json={"name": "n8n üretim", "url": url, "events": events})


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def run_worker(handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    with get_sessionmaker()() as db, httpx.Client(transport=httpx.MockTransport(record)) as client:
        deliver_due(db, limit=200, client=client)
    return seen


def deliveries(client) -> list[dict]:
    return client.get("/api/v1/automation/deliveries").json()


def test_outbound_events_are_signed_and_retried(client, database: str) -> None:
    workspace(client, "Webhook Atölyesi")
    assert outbound(client, ["customer.created"], url="ftp://example.test").status_code == 422
    assert outbound(client, []).status_code == 422
    assert outbound(client, ["payroll.paid"]).json()["detail"] == "Bilinmeyen olay türü: payroll.paid"

    created = outbound(client, ["task.completed", "customer.created"])
    assert created.status_code == 201, created.text
    secret = created.json()["secret"]
    endpoint = created.json()["endpoint"]
    assert secret.startswith("whsec_") and endpoint["secret_hint"] == secret[-4:]
    assert endpoint["events"] == ["customer.created", "task.completed"]
    assert "secret" not in client.get("/api/v1/automation/endpoints").json()[0]

    client.post("/api/v1/customers", headers=csrf(client), json={"name": "Bora Ltd."})
    task = client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Webhook görevi"}).json()
    client.post(f"/api/v1/tasks/{task['id']}/status", headers=csrf(client), json={"status": "in_progress"})
    client.post(f"/api/v1/tasks/{task['id']}/status", headers=csrf(client), json={"status": "done"})
    pending = deliveries(client)
    assert sorted(item["event_type"] for item in pending) == ["customer.created", "task.completed"]
    assert {item["status"] for item in pending} == {"pending"}

    seen = run_worker(lambda request: httpx.Response(204))
    ours = [request for request in seen if request.headers["X-Luminova-Delivery"] in {item["id"] for item in pending}]
    assert len(ours) == 2
    for request in ours:
        body = request.content
        assert request.headers["X-Luminova-Signature"] == sign(secret, request.headers["X-Luminova-Timestamp"], body)
        envelope = json.loads(body)
        assert envelope["type"] == request.headers["X-Luminova-Event"]
        if envelope["type"] == "customer.created":
            assert envelope["data"]["name"] == "Bora Ltd."
        else:
            assert envelope["data"]["title"] == "Webhook görevi"
    assert {item["status"] for item in deliveries(client)} == {"delivered"}

    rotated = client.post(f"/api/v1/automation/endpoints/{endpoint['id']}/rotate", headers=csrf(client)).json()
    assert rotated["secret"] != secret and rotated["endpoint"]["secret_hint"] == rotated["secret"][-4:]

    client.post("/api/v1/customers", headers=csrf(client), json={"name": "Deniz Yapı"})
    failing = next(item for item in deliveries(client) if item["status"] == "pending")
    run_worker(lambda request: httpx.Response(500))
    after = next(item for item in deliveries(client) if item["id"] == failing["id"])
    assert after["status"] == "pending" and after["attempts"] == 1 and after["last_status_code"] == 500
    assert after["last_error"] == "Alıcı 500 yanıtı verdi."
    for _ in range(5):
        with psycopg.connect(database) as connection:
            connection.execute("UPDATE webhook_deliveries SET next_attempt_at = now() WHERE id = %s", (failing["id"],))
        run_worker(lambda request: httpx.Response(500))
    final = next(item for item in deliveries(client) if item["id"] == failing["id"])
    assert final["status"] == "failed" and final["attempts"] == 6

    closed_port = {"name": "n8n üretim", "url": "http://127.0.0.1:9/hook", "events": ["customer.created"]}
    assert client.put(f"/api/v1/automation/endpoints/{endpoint['id']}", headers=csrf(client), json=closed_port).status_code == 200
    tested = client.post(f"/api/v1/automation/endpoints/{endpoint['id']}/test", headers=csrf(client)).json()
    assert tested["event_type"] == "ping" and tested["status"] == "failed" and tested["last_error"].startswith("Bağlantı kurulamadı")

    assert client.delete(f"/api/v1/automation/endpoints/{endpoint['id']}", headers=csrf(client)).status_code == 204
    assert client.get("/api/v1/automation/endpoints").json() == []
    verbs = [item["verb"] for item in client.get("/api/v1/activity", params={"module": "workspace"}).json()["items"][:4]]
    assert verbs == ["otomasyon bağlantısını sildi", "otomasyon bağlantısını güncelledi", "bağlantı anahtarını yeniledi", "otomasyon bağlantısı ekledi"]


def test_no_events_without_the_module(client) -> None:
    workspace(client, "Modülsüz Webhook", ["customers"])
    assert client.get("/api/v1/automation/endpoints").status_code == 403
    client.post("/api/v1/customers", headers=csrf(client), json={"name": "Sessiz Müşteri"})


def post_hook(client, endpoint_id: str, secret: str, payload: dict, *, delivery: str | None = None, timestamp: str | None = None, bad: bool = False):
    body = json.dumps(payload).encode()
    stamp = timestamp or str(int(time.time()))
    headers = {"Content-Type": "application/json", "X-Luminova-Timestamp": stamp, "X-Luminova-Signature": "sha256=00" if bad else sign(secret, stamp, body)}
    if delivery:
        headers["X-Luminova-Delivery"] = delivery
    return client.post(f"/api/v1/hooks/{endpoint_id}", content=body, headers=headers)


def test_inbound_webhooks_create_tasks_and_notifications(client) -> None:
    workspace(client, "Gelen Webhook")
    created = client.post("/api/v1/automation/endpoints", headers=csrf(client), json={"direction": "inbound", "name": "n8n'den gelen"}).json()
    endpoint, secret = created["endpoint"], created["secret"]
    assert endpoint["inbound_path"] == f"/api/v1/hooks/{endpoint['id']}" and endpoint["url"] is None

    task = {"action": "task.create", "data": {"title": "Yeni web siparişini kontrol et", "priority": "high"}}
    assert post_hook(client, endpoint["id"], secret, task, bad=True).status_code == 401
    assert post_hook(client, endpoint["id"], secret, task, timestamp=str(int(time.time()) - 900)).status_code == 401
    assert post_hook(client, str(uuid4()), secret, task).status_code == 404
    assert post_hook(client, endpoint["id"], secret, {"action": "task.create", "data": {"title": "x"}}).status_code == 422
    assert post_hook(client, endpoint["id"], secret, {"action": "order.delete", "data": {}}).status_code == 422

    delivery = f"n8n-{uuid4().hex}"
    first = post_hook(client, endpoint["id"], secret, task, delivery=delivery)
    assert first.status_code == 200, first.text
    assert first.json()["duplicate"] is False and first.json()["id"]
    assert post_hook(client, endpoint["id"], secret, task, delivery=delivery).json()["duplicate"] is True
    titles = [item["title"] for item in client.get("/api/v1/tasks").json()["items"]]
    assert titles.count("Yeni web siparişini kontrol et") == 1
    latest = client.get("/api/v1/activity", params={"module": "tasks"}).json()["items"][0]
    assert (latest["actor_name"], latest["verb"], latest["target"]) == ("Otomasyon", "görev ekledi", "Yeni web siparişini kontrol et")

    note = {"action": "notification.create", "data": {"title": "Ödeme alındı: SP-0042", "body": "iyzico bildirimi"}}
    assert post_hook(client, endpoint["id"], secret, note).status_code == 200
    automation = [item for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "automation"]
    assert automation[0]["title"] == "Ödeme alındı: SP-0042"
    assert client.get("/api/v1/automation/endpoints").json()[0]["last_used_at"] is not None


def test_members_cannot_manage_and_tenancy(client) -> None:
    workspace(client, "Yetki Webhook")
    endpoint = outbound(client, ["customer.created"]).json()["endpoint"]
    link = invite(client, f"uye-{uuid4().hex[:8]}@example.com").json()["invite_path"]

    from app.main import create_app

    with TestClient(create_app()) as other:
        assert accept(other, link).status_code == 201
        assert other.get("/api/v1/automation/endpoints").status_code == 403
        assert outbound(other, ["customer.created"]).status_code == 403

        sign_in_new_company(other, "Başka Webhook")
        other.post("/api/v1/workspace/setup", headers=csrf(other), json={"modules": ["automation"]})
        assert other.get("/api/v1/automation/endpoints").json() == []
        assert other.post(f"/api/v1/automation/endpoints/{endpoint['id']}/rotate", headers=csrf(other)).status_code == 404
        assert other.delete(f"/api/v1/automation/endpoints/{endpoint['id']}", headers=csrf(other)).status_code == 404


def test_production_requires_a_webhook_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://luminova:secret@db.internal:5432/luminova")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.luminova.example")
    monkeypatch.delenv("WEBHOOK_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()
    monkeypatch.setenv("WEBHOOK_SECRET_KEY", "x" * 40)
    get_settings.cache_clear()
    assert get_settings().webhook_secret_key == "x" * 40
    get_settings.cache_clear()
