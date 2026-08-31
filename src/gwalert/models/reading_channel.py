from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from gwalert.models._base import Base


class ReadingChannelSql(Base):
    __tablename__ = "reading_channels"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    terminal_asset_alias: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    unit_type: Mapped[str] = mapped_column(String, nullable=False)
    channel_type: Mapped[str] = mapped_column(String, nullable=False)
    deactivated_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("terminal_asset_alias", "name"),
        UniqueConstraint(
            "terminal_asset_alias",
            "name",
            "deactivated_date",
            name="unique_name_terminal_asset_deactivated_date",
            postgresql_nulls_not_distinct=True,
        ),
    )
