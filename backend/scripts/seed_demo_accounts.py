from __future__ import annotations

from passlib.context import CryptContext

from app.db.session import SessionLocal
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_ACCOUNTS = [
    {
        "email": "cuong0505@gmail.com",
        "password": "cuong0505",
        "full_name": "Giáo viên Cường",
        "role": "teacher",
        "is_demo": True,
    },
    {
        "email": "cuong0505@gmail.com",
        "password": "cuong0505",
        "full_name": "Học viên Cường",
        "role": "student",
        "is_demo": True,
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        for acc in DEMO_ACCOUNTS:
            existing = (
                db.query(User)
                .filter(
                    User.email == acc["email"],
                    User.role == acc["role"],
                )
                .first()
            )
            if existing:
                print(f"⏩ Demo account already exists: {acc['email']} ({acc['role']})")
                continue

            user = User(
                email=acc["email"],
                password_hash=pwd_context.hash(acc["password"]),
                full_name=acc["full_name"],
                role=acc["role"],
                is_active=True,
                is_demo=bool(acc.get("is_demo", True)),
            )
            db.add(user)
            print(f"✅ Seeded demo account: {acc['email']} ({acc['role']})")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
