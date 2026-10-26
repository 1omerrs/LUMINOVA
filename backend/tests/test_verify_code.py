from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from test_auth import csrf
from test_join import login, owner_workspace, sign_up
from test_mail import TEST_DSN

from app.services import auth as auth_service


def verify(visitor, email: str, code: str):
    return visitor.post("/api/v1/auth/verify-code", headers=csrf(visitor), json={"email": email, "code": code})


def resend(visitor, email: str):
    return visitor.post("/api/v1/auth/verify-code/resend", headers=csrf(visitor), json={"email": email})


def age_codes(email: str, seconds: int) -> None:
    with psycopg.connect(TEST_DSN) as connection:
        connection.execute(
            "UPDATE email_verification_tokens SET created_at = created_at - make_interval(secs => %s) "
            "WHERE user_id = (SELECT id FROM users WHERE email = %s)",
            (seconds, email),
        )


def test_code_verifies_member_and_counts_wrong_tries(client, monkeypatch) -> None:
    code = owner_workspace(client, "Kodla Doğrulayan Atölye")
    monkeypatch.setattr(auth_service, "_new_code", lambda: "482913")
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        email = f"kod-{uuid4().hex[:8]}@example.com"
        assert sign_up(visitor, code, email).status_code == 201
        assert verify(visitor, email, "12345").status_code == 422
        wrong = verify(visitor, email, "000000")
        assert wrong.status_code == 400 and "4 deneme hakkınız kaldı" in wrong.json()["detail"]
        assert verify(visitor, "yok@example.com", "482913").status_code == 400

        assert verify(visitor, email.upper(), "482 913").status_code == 200
        assert verify(visitor, email, "482913").status_code == 200
        waiting = login(visitor, email)
        assert waiting.status_code == 403 and "onayını bekliyor" in waiting.json()["detail"]
        assert any(item["title"] == "Deniz Aday ekibe katılmak istiyor." for item in client.get("/api/v1/notifications").json()["items"])


def test_too_many_wrong_codes_need_a_new_code(client, monkeypatch) -> None:
    code = owner_workspace(client, "Kilitli Kod Atölyesi")
    codes = iter(["111111", "222222"])
    monkeypatch.setattr(auth_service, "_new_code", lambda: next(codes))
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        email = f"kilit-{uuid4().hex[:8]}@example.com"
        assert sign_up(visitor, code, email).status_code == 201
        statuses = [verify(visitor, email, "999999").status_code for _ in range(5)]
        assert statuses == [400, 400, 400, 400, 429]
        assert verify(visitor, email, "111111").status_code == 429

        resend(visitor, email)
        assert verify(visitor, email, "222222").status_code == 429, "a new code needs a minute between requests"
        age_codes(email, 61)
        assert resend(visitor, email).status_code == 202
        assert verify(visitor, email, "111111").status_code == 400
        assert verify(visitor, email, "222222").status_code == 200


def test_resend_is_silent_and_limited(client) -> None:
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        unknown = resend(visitor, "hic-yok@example.com")
        assert unknown.status_code == 202

    code = owner_workspace(client, "Sınırlı Kod Atölyesi")
    verified_owner = client.get("/api/v1/auth/me").json()["email"]
    with TestClient(create_app()) as visitor:
        assert resend(visitor, verified_owner).json() == unknown.json()
    with TestClient(create_app()) as visitor:
        email = f"sinir-{uuid4().hex[:8]}@example.com"
        assert sign_up(visitor, code, email).status_code == 201
        for _ in range(6):
            age_codes(email, 61)
            resend(visitor, email)
        with psycopg.connect(TEST_DSN) as connection:
            count = connection.execute(
                "SELECT count(*) FROM email_verification_tokens WHERE user_id = (SELECT id FROM users WHERE email = %s) AND created_at > %s",
                (email, datetime.now(UTC) - timedelta(hours=1)),
            ).fetchone()[0]
        assert count <= auth_service.VERIFY_RESEND_LIMIT
