"""Create an admin account. There is no public admin signup (decision D3).

Run: python -m app.scripts.create_admin --email admin@example.com --name "Skill Cortex Admin" --phone 9876543210
The password is read from ADMIN_PASSWORD, or prompted for interactively.
"""

import argparse
import getpass
import os
import sys

from pydantic import EmailStr, TypeAdapter
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.database import SessionLocal
from app.models import User, UserRole
from app.schemas.user import normalize_phone, validate_password_strength
from app.services.auth import get_user_by_email, normalize_email
from app.utils.security import hash_password


class AdminCreationError(Exception):
    pass


def create_admin(db: Session, *, name: str, email: str, phone: str, password: str) -> User:
    try:
        email = normalize_email(TypeAdapter(EmailStr).validate_python(email))
        phone = normalize_phone(phone)
        validate_password_strength(password)
    except ValueError as exc:
        raise AdminCreationError(str(exc)) from exc
    name = name.strip()
    if len(name) < 2:
        raise AdminCreationError("Name must be at least 2 characters.")
    if get_user_by_email(db, email) is not None:
        raise AdminCreationError("A user with this email already exists.")

    admin = User(name=name, email=email, phone=phone, password_hash=hash_password(password), role=UserRole.ADMIN)
    db.add(admin)
    db.flush()
    return admin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Skill Cortex admin account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--phone", required=True)
    args = parser.parse_args(argv)

    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")

    with SessionLocal() as db:
        try:
            admin = create_admin(db, name=args.name, email=args.email, phone=args.phone, password=password)
        except AdminCreationError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        db.commit()
        print(f"Admin created: {admin.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
