"""Declarative base shared by every ORM model in the package."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All models inherit from this so Base.metadata knows the full schema."""
