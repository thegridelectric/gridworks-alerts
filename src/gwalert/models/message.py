from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gwalert.models._base import Base


class MessageSql(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, primary_key=True, index=True
    )
    from_alias: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    persisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    message_type_name: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        Index("messages_timestamp_idx", timestamp.desc()),
        Index(
            "ix_from_type_message",
            "from_alias",
            "message_type_name",
            "persisted_at",
        ),
    )
