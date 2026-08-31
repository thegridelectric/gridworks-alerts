from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gwalert.models._base import Base
from gwalert.models.reading_channel import ReadingChannelSql


class ReadingSql(Base):
    __tablename__ = "readings"
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reading_channels.id"),
        nullable=False,
    )
    channel: Mapped[ReadingChannelSql] = relationship()
    message_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        Index("readings_timestamp_idx", timestamp.desc()),
        UniqueConstraint(
            "channel_id", "timestamp", name="readings_channel_id_timestamp_key"
        ),
    )

    __mapper_args__ = {
        "primary_key": [channel_id, timestamp],
    }
