"""Database ORM models for users, RFID cards and transactions."""

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TransactionType(str, enum.Enum):
    """Allowed business transaction categories recorded by EkoMatik."""

    EARN_EKOMATIK = "EARN_EKOMATIK"
    DONATE_STK = "DONATE_STK"
    TRANSFER_TRANSIT = "TRANSFER_TRANSIT"


class User(Base):
    """Represents a mobile application user and their current point balance."""

    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    total_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    cards: Mapped[list["RFIDCard"]] = relationship(back_populates="user")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")


class RFIDCard(Base):
    """Maps a physical RFID UID to a user account."""

    __tablename__ = "rfid_cards"

    rfid_uid: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped[User] = relationship(back_populates="cards")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="rfid_card")


class Transaction(Base):
    """Immutable financial/event ledger row for balance-affecting operations."""

    __tablename__ = "transactions"

    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rfid_uid: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("rfid_cards.rfid_uid", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    partner_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    user: Mapped[User] = relationship(back_populates="transactions")
    rfid_card: Mapped[RFIDCard | None] = relationship(back_populates="transactions")