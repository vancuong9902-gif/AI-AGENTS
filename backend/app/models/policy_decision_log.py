from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base_class import Base


class PolicyDecisionLog(Base):
    __tablename__ = "policy_decision_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)

    policy_type: Mapped[str] = mapped_column(String(50), nullable=False, default="contextual_bandit")
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    recommended_difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)

    state_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    meta_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
