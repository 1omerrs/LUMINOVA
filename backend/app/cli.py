"""Operator commands.

python -m app.cli create-admin <login>       # staff-only account for /yonetim; asks for the password
python -m app.cli grant-admin user@example.com
python -m app.cli revoke-admin user@example.com
python -m app.cli deliver-webhooks          # one pass over due webhook deliveries and queued e-mails
python -m app.cli webhook-worker            # keep delivering webhooks and e-mails; every 5 minutes also runs scheduled work
python -m app.cli run-scheduled             # one pass of automatic tasks and reminders for every company
"""

import argparse
import getpass
import sys
import time
from datetime import UTC, datetime

from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.identity import Session as AuthSession
from app.models.identity import User
from app.services.automation import deliver_due
from app.services.mail import deliver_mail
from app.services.scheduler import run_scheduled


def set_admin(email: str, value: bool) -> int:
    with get_sessionmaker()() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
        if user is None:
            print(f"Kullanıcı bulunamadı: {email}", file=sys.stderr)
            return 1
        user.is_platform_admin = value
        db.commit()
        print(f"{user.email}: platform yöneticisi {'yapıldı' if value else 'yetkisi kaldırıldı'}.")
        return 0


WEAK_PASSWORDS = {"admin", "admin123", "admin 123", "password", "parola", "123456", "12345678", "123456789", "qwerty", "luminova"}


def create_admin(login: str, password: str) -> int:
    """Creates or updates the staff-only account that opens the platform panel (/yonetim)."""
    login = login.strip().lower()
    if len(login) < 3:
        print("Giriş adı en az 3 karakter olmalı.", file=sys.stderr)
        return 1
    if get_settings().app_env == "production" and (len(password) < 12 or password.strip().lower() in WEAK_PASSWORDS or login in password.lower()):
        print("Canlı ortamda yönetici şifresi en az 12 karakter olmalı ve tahmin edilebilir olmamalı.", file=sys.stderr)
        return 1
    now = datetime.now(UTC)
    with get_sessionmaker()() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == login))
        if user is None:
            user = User(email=login, first_name="LUMINOVA", last_name="Yönetim", status="active", email_verified_at=now, password_hash=hash_password(password))
            db.add(user)
            action = "oluşturuldu"
        else:
            user.password_hash = hash_password(password)
            user.status = "active"
            user.email_verified_at = user.email_verified_at or now
            user.updated_at = now
            db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).values(revoked_at=now))
            action = "güncellendi; açık oturumları kapatıldı"
        user.is_platform_admin = True
        db.commit()
    print(f"Platform yönetim hesabı {action}: {login}")
    return 0


SCHEDULE_EVERY = 300.0


def scheduled_pass() -> None:
    with get_sessionmaker()() as db:
        totals = run_scheduled(db)
    print(
        f"Zamanlanmış kontrol: {totals['companies']} şirket, {totals['created']} görev açıldı, {totals['resolved']} görev kapandı, "
        f"{totals['digests']} haftalık özet sıraya alındı.",
        flush=True,
    )


def deliver(loop: bool, interval: float) -> int:
    last_schedule = 0.0
    while True:
        with get_sessionmaker()() as db:
            sent = deliver_due(db)
        with get_sessionmaker()() as db:
            mailed = deliver_mail(db)
        if sent:
            print(f"{sent} webhook gönderimi denendi.", flush=True)
        if mailed:
            print(f"{mailed} e-posta n8n'e iletilmeye çalışıldı.", flush=True)
        sent += mailed
        if not loop:
            return 0
        if time.monotonic() - last_schedule >= SCHEDULE_EVERY:
            scheduled_pass()
            last_schedule = time.monotonic()
        if not sent:
            time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("grant-admin", "revoke-admin"):
        commands.add_parser(name).add_argument("email")
    staff = commands.add_parser("create-admin")
    staff.add_argument("login")
    staff.add_argument("--password", help="Verilmezse güvenli biçimde sorulur; komut geçmişinde kalmaması için sormasını tercih edin.")
    commands.add_parser("deliver-webhooks")
    commands.add_parser("run-scheduled")
    worker = commands.add_parser("webhook-worker")
    worker.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args(argv)
    if args.command in {"grant-admin", "revoke-admin"}:
        return set_admin(args.email, args.command == "grant-admin")
    if args.command == "create-admin":
        return create_admin(args.login, args.password or getpass.getpass("Şifre: "))
    if args.command == "deliver-webhooks":
        return deliver(loop=False, interval=0)
    if args.command == "run-scheduled":
        scheduled_pass()
        return 0
    try:
        return deliver(loop=True, interval=args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
