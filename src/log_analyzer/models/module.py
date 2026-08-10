"""Module lookup table — one row per distinct application component/module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from log_analyzer.models.base import Base

if TYPE_CHECKING:
    from log_analyzer.models.log_entry import LogEntry


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)

    log_entries: Mapped[list[LogEntry]] = relationship(back_populates="module")

    def __repr__(self) -> str:
        return f"Module(id={self.id}, name={self.name!r})"
