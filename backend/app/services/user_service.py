from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User


def ensure_user_exists(db: Session, user_id: int, *, role: str = "student") -> User:
    """Ensure a user row exists for a given numeric ID.

    Why: The demo frontend lets you type any ID (1, 2, 3...). But the database
    enforces foreign keys to the `users` table. If a user id doesn't exist,
    inserts into `quiz_sets`, `attempts`, `learner_profiles`, ... will fail.

    This helper auto-creates a minimal user record when missing.
    """

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user:
        # Keep role consistent in demo mode (helps teacher/student routing)
        try:
            if role and hasattr(user, "role") and (user.role or "") != role:
                user.role = role
                db.commit()
        except Exception:
            pass
        return user

    uid = int(user_id)
    email = f"{role}{uid}@demo.local"

    # If email happens to exist already, keep it unique.
    if db.query(User).filter(User.email == email).first():
        email = f"{role}{uid}-{uid}@demo.local"

    user = User(id=uid, email=email, full_name=f"{role.title()} {uid}", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
