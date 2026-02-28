from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base_class import Base


class RetentionSchedule(Base):
    """A scheduled retention check (spaced repetition / delayed evaluation).

    This table supports delayed-reward learning:
      - We can attach a future retention outcome to an earlier policy decision (state/action),
        enabling credit assignment beyond immediate quiz scores.

    Notes:
      - No background execution is assumed. 'due' checks are surfaced via API and can be
        triggered by the client when convenient.
    """

    __tablename__ = "retention_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("document_topics.id"), index=True, nullable=False)

    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )

    baseline_score_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    # Provenance: the attempt/quiz that triggered this schedule (e.g., mastery attempt).
    source_attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id"), nullable=True)
    source_quiz_set_id: Mapped[int | None] = mapped_column(ForeignKey("quiz_sets.id"), nullable=True)

    # Delayed credit assignment to a prior policy decision (best-effort).
    origin_policy_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    origin_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    origin_state_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Retention quiz/attempt created when the schedule is executed.
    retention_quiz_set_id: Mapped[int | None] = mapped_column(ForeignKey("quiz_sets.id"), nullable=True)
    retention_attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
