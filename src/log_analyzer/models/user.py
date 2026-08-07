"""User lookup table — one row per distinct username seen in the logs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from log_analyzer.models.base import Base

if TYPE_CHECKING:
    from log_analyzer.models.log_entry import LogEntry


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)

    log_entries: Mapped[list["LogEntry"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"User(id={self.id}, username={self.username!r})"
