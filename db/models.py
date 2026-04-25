from datetime import datetime, date, time
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Integer, Text,
    ForeignKey, UniqueConstraint, Index, text, Time
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    telegram_username: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Europe/Moscow")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    settings: Mapped[Optional["UserSettings"]] = relationship(back_populates="user", uselist=False)
    google_connection: Mapped[Optional["GoogleConnection"]] = relationship(back_populates="user", uselist=False)
    categories: Mapped[list["Category"]] = relationship(back_populates="user")
    activity_logs: Mapped[list["ActivityLog"]] = relationship(back_populates="user")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    reminder_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    evening_report_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    evening_report_time: Mapped[time] = mapped_column(Time, nullable=False, server_default="21:00")
    weekly_report_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    google_sheet_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    user: Mapped["User"] = relationship(back_populates="settings")


class GoogleConnection(Base):
    __tablename__ = "google_connections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    spreadsheet_id: Mapped[str] = mapped_column(Text, nullable=False)
    spreadsheet_url: Mapped[str] = mapped_column(Text, nullable=False)
    connection_status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    last_push_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_pull_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    user: Mapped["User"] = relationship(back_populates="google_connection")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_category"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    user: Mapped["User"] = relationship(back_populates="categories")
    activity_logs: Mapped[list["ActivityLog"]] = relationship(back_populates="category")


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("idx_activity_logs_user_date", "user_id", "date_local"),
        Index("idx_activity_logs_user_status", "user_id", "status"),
        Index("idx_activity_logs_open", "user_id", postgresql_where=text("status = 'open'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    date_local: Mapped[date] = mapped_column(Date, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("categories.id"), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="telegram")
    sync_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    user: Mapped["User"] = relationship(back_populates="activity_logs")
    category: Mapped[Optional["Category"]] = relationship(back_populates="activity_logs")


class SyncEvent(Base):
    __tablename__ = "sync_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sync_direction: Mapped[str] = mapped_column(Text, nullable=False)
    sync_status: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class DailyAggregate(Base):
    __tablename__ = "daily_aggregates"
    __table_args__ = (
        UniqueConstraint("user_id", "date_local", name="uq_daily_agg"),
        Index("idx_daily_agg_user_date", "user_id", "date_local"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    date_local: Mapped[date] = mapped_column(Date, nullable=False)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    study_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rest_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hobby_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transport_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    phone_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_blocks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class WeeklyAggregate(Base):
    __tablename__ = "weekly_aggregates"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start_date", name="uq_weekly_agg"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
