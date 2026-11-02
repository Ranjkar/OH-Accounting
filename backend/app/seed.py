"""Seed a dev tenant + admin user. Run with: .venv/bin/python -m app.seed"""

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User

ADMIN_EMAIL = "admin@onholland.nl"
ADMIN_PASSWORD = "changeme123"


def seed() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == ADMIN_EMAIL).first():
            print("Seed data already present, skipping.")
            return
        tenant = Tenant(name="OnHolland Accounting")
        db.add(tenant)
        db.flush()
        admin = User(
            tenant_id=tenant.id,
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            full_name="OnHolland Admin",
            role=UserRole.admin,
        )
        db.add(admin)
        db.commit()
        print(f"Seeded tenant '{tenant.name}' and admin user '{ADMIN_EMAIL}'.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
