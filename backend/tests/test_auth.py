from uuid import uuid4

import psycopg


def csrf(client) -> dict[str, str]:
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    token = response.json()["token"]
    assert token
    return {"X-CSRF-Token": token}


def account_payload(email: str, company: str = "Örnek Atölye") -> dict[str, str]:
    return {
        "first_name": "Ömer",
        "last_name": "Yılmaz",
        "email": email,
        "password": "dogru-parola-1901",
        "company_name": company,
    }


def test_register_requires_csrf(client) -> None:
    response = client.post("/api/v1/auth/register", json=account_payload(f"{uuid4().hex[:8]}@example.com"))

    assert response.status_code == 403
    assert response.json()["detail"] == "İstek doğrulanamadı."


def test_short_password_is_not_echoed(client) -> None:
    payload = account_payload(f"{uuid4().hex[:8]}@example.com")
    payload["password"] = "kisa"
    response = client.post("/api/v1/auth/register", headers=csrf(client), json=payload)

    assert response.status_code == 422
    assert "kisa" not in response.text
    assert "password" not in response.text.lower() or "şifre" in response.text.lower()


def test_register_verify_login_and_logout(client, database: str) -> None:
    email = f"{uuid4().hex[:8]}@example.com"
    created = client.post("/api/v1/auth/register", headers=csrf(client), json=account_payload(email))

    assert created.status_code == 201
    body = created.json()
    assert body["email_sent"] is False
    assert body["verification_path"]
    assert "gönderilmedi" in body["message"]
    assert "dogru-parola-1901" not in created.text

    blocked = client.post(
        "/api/v1/auth/login",
        headers=csrf(client),
        json={"email": email, "password": "dogru-parola-1901"},
    )
    assert blocked.status_code == 403

    token = body["verification_path"].split("token=", 1)[1]
    verified = client.post("/api/v1/auth/verify-email", headers=csrf(client), json={"token": token})
    assert verified.status_code == 200
    again = client.post("/api/v1/auth/verify-email", headers=csrf(client), json={"token": token})
    assert again.status_code == 200

    signed_in = client.post(
        "/api/v1/auth/login",
        headers=csrf(client),
        json={"email": email, "password": "dogru-parola-1901"},
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["email"] == email
    assert signed_in.json()["company_name"] == "Örnek Atölye"
    assert "luminova_session" in signed_in.headers["set-cookie"]

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["first_name"] == "Ömer"

    logged_out = client.post("/api/v1/auth/logout", headers=csrf(client))
    assert logged_out.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401

    with psycopg.connect(database) as connection:
        audit = connection.execute(
            "SELECT summary::text FROM audit_logs WHERE action = 'account.registered' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        stored = connection.execute("SELECT password_hash, token_hash FROM users u JOIN email_verification_tokens t ON t.user_id = u.id WHERE u.email = %s", (email,)).fetchone()
    assert audit is not None
    assert "password" not in audit[0].lower()
    assert stored is not None
    assert stored[0] != "dogru-parola-1901"
    assert token not in stored[1]


def test_duplicate_email_and_wrong_password(client) -> None:
    email = f"{uuid4().hex[:8]}@example.com"
    payload = account_payload(email, company="Kuzey Atölye")
    assert client.post("/api/v1/auth/register", headers=csrf(client), json=payload).status_code == 201
    duplicate = client.post("/api/v1/auth/register", headers=csrf(client), json=payload)
    assert duplicate.status_code == 409

    token = client.post("/api/v1/auth/register", headers=csrf(client), json=account_payload(f"other-{email}", company="Kuzey Atölye")).json()[
        "verification_path"
    ].split("token=", 1)[1]
    # The second company name collides on slug; registration should still succeed with a suffixed slug.
    assert token

    wrong = client.post(
        "/api/v1/auth/login",
        headers=csrf(client),
        json={"email": email, "password": "yanlis-parola-1901"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "E-posta veya şifre hatalı."


def test_many_companies_can_share_a_name(client, database: str) -> None:
    name = f"Ortak Ad {uuid4().hex[:6]}"
    emails = [f"{uuid4().hex[:8]}@example.com" for _ in range(9)]
    for email in emails:
        response = client.post("/api/v1/auth/register", headers=csrf(client), json=account_payload(email, company=name))
        assert response.status_code == 201

    with psycopg.connect(database) as connection:
        slugs = connection.execute("SELECT slug FROM companies WHERE name = %s", (name,)).fetchall()
    assert len({slug for (slug,) in slugs}) == 9


def verified_account(client) -> str:
    email = f"{uuid4().hex[:8]}@example.com"
    created = client.post("/api/v1/auth/register", headers=csrf(client), json=account_payload(email))
    token = created.json()["verification_path"].split("token=", 1)[1]
    assert client.post("/api/v1/auth/verify-email", headers=csrf(client), json={"token": token}).status_code == 200
    return email


def test_remember_me_controls_cookie_lifetime(client) -> None:
    email = verified_account(client)

    browser = client.post("/api/v1/auth/login", headers=csrf(client), json={"email": email, "password": "dogru-parola-1901"})
    assert browser.status_code == 200
    browser_cookie = next(value for value in browser.headers.get_list("set-cookie") if value.startswith("luminova_session="))
    assert "max-age" not in browser_cookie.lower()
    assert browser.json()["setup_completed"] is False

    remembered = client.post(
        "/api/v1/auth/login",
        headers=csrf(client),
        json={"email": email, "password": "dogru-parola-1901", "remember": True},
    )
    remembered_cookie = next(value for value in remembered.headers.get_list("set-cookie") if value.startswith("luminova_session="))
    assert "max-age=2592000" in remembered_cookie.lower()


def test_password_reset_flow(client, database: str) -> None:
    email = verified_account(client)
    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": email, "password": "dogru-parola-1901"}).status_code == 200

    unknown = client.post("/api/v1/auth/forgot-password", headers=csrf(client), json={"email": f"yok-{email}"})
    assert unknown.status_code == 202
    assert unknown.json()["email_sent"] is False
    assert unknown.json()["reset_path"] is None

    requested = client.post("/api/v1/auth/forgot-password", headers=csrf(client), json={"email": email})
    assert requested.status_code == 202
    assert requested.json()["message"] == unknown.json()["message"]
    token = requested.json()["reset_path"].split("token=", 1)[1]

    short = client.post("/api/v1/auth/reset-password", headers=csrf(client), json={"token": token, "password": "kisa"})
    assert short.status_code == 422

    changed = client.post("/api/v1/auth/reset-password", headers=csrf(client), json={"token": token, "password": "yeni-parola-2026"})
    assert changed.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401

    reused = client.post("/api/v1/auth/reset-password", headers=csrf(client), json={"token": token, "password": "baska-parola-2026"})
    assert reused.status_code == 400

    old = client.post("/api/v1/auth/login", headers=csrf(client), json={"email": email, "password": "dogru-parola-1901"})
    assert old.status_code == 401
    new = client.post("/api/v1/auth/login", headers=csrf(client), json={"email": email, "password": "yeni-parola-2026"})
    assert new.status_code == 200

    with psycopg.connect(database) as connection:
        stored = connection.execute(
            "SELECT t.token_hash FROM password_reset_tokens t JOIN users u ON u.id = t.user_id WHERE u.email = %s",
            (email,),
        ).fetchone()
    assert stored is not None
    assert token not in stored[0]


def test_login_rate_limit(client) -> None:
    email = f"{uuid4().hex[:8]}@example.com"
    for _ in range(8):
        response = client.post(
            "/api/v1/auth/login",
            headers=csrf(client),
            json={"email": email, "password": "yanlis-parola-1901"},
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/v1/auth/login",
        headers=csrf(client),
        json={"email": email, "password": "yanlis-parola-1901"},
    )
    assert limited.status_code == 429


def test_sessions_are_isolated(client) -> None:
    first = f"{uuid4().hex[:8]}@example.com"
    second = f"{uuid4().hex[:8]}@example.com"
    for email, company in ((first, "Birinci"), (second, "İkinci Atölye")):
        created = client.post("/api/v1/auth/register", headers=csrf(client), json=account_payload(email, company))
        token = created.json()["verification_path"].split("token=", 1)[1]
        assert client.post("/api/v1/auth/verify-email", headers=csrf(client), json={"token": token}).status_code == 200
        assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": email, "password": "dogru-parola-1901"}).status_code == 200
        assert client.get("/api/v1/auth/me").json()["email"] == email
        assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    assert client.get("/api/v1/auth/me").status_code == 401
