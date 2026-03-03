import sys, os
sys.path.insert(0, "/app")

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
            # Check by BOTH email AND role — same email is allowed with different roles
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
            # Commit individually so one failure does not roll back the rest
            try:
                db.commit()
                print(f"✅ Seeded demo account: {acc['email']} ({acc['role']})")
            except Exception as e:
                db.rollback()
                print(f"⚠️  Skipped {acc['email']} ({acc['role']}): {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()