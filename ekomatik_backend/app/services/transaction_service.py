"""Business logic for earning, donating and transferring EkoMatik balance."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import RFIDCard, Transaction, TransactionType, User
from app.schemas.schemas import AddTransactionRequest, SpendRequest



def add_ekomatik_earning(db: Session, payload: AddTransactionRequest):
    """Atomically credit the RFID owner's balance and insert an earning ledger row.

    The RFID card is locked with SELECT ... FOR UPDATE, which prevents two concurrent
    IoT requests from racing while resolving or mutating the same account balance.
    """

    # Lock the card row first so its ownership and active status remain stable during
    # this operation. PostgreSQL applies the lock inside the current DB transaction.
    card = db.execute(
        select(RFIDCard).where(RFIDCard.rfid_uid == payload.rfid_uid).with_for_update()
    ).scalar_one_or_none()

    if card is None or not card.is_active:
        raise HTTPException(status_code=404, detail="RFID card not found or inactive")

    # Lock the user row before changing the balance to serialize concurrent updates.
    user = db.execute(select(User).where(User.user_id == card.user_id).with_for_update()).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # The IoT message timestamp is the event timestamp supplied by the device; it has
    # already passed replay protection in middleware, so we keep it in the audit trail.
    transaction = Transaction(
        transaction_id=uuid.uuid4(),
        user_id=user.user_id,
        rfid_uid=card.rfid_uid,
        type=TransactionType.EARN_EKOMATIK,
        amount=payload.amount,
        timestamp=datetime.fromtimestamp(payload.timestamp, tz=timezone.utc),
    )

    try:
        user.total_balance = user.total_balance + payload.amount
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        db.refresh(user)
    except SQLAlchemyError as exc:
        # Explicit rollback ensures the balance change and ledger insert are atomic.
        db.rollback()
        raise HTTPException(status_code=500, detail="Database transaction failed") from exc

    return AddTransactionResponseData(
        transaction_id=transaction.transaction_id,
        user_id=user.user_id,
        new_balance=user.total_balance,
    )


class AddTransactionResponseData:
    """Small internal DTO returned by the earning service."""

    def __init__(self, transaction_id: uuid.UUID, user_id: uuid.UUID, new_balance: Decimal):
        self.transaction_id = transaction_id
        self.user_id = user_id
        self.new_balance = new_balance


def spend_balance(db: Session, user_id: uuid.UUID, payload: SpendRequest):
    """Perform a donation/transfer inside one explicit ACID database transaction.

    The user row is locked with SELECT ... FOR UPDATE before checking the balance.
    Therefore concurrent spend requests cannot both observe the same old balance and
    overspend the account. Any failure rolls the whole operation back.
    """

    try:
        # BEGIN: SQLAlchemy opens a transaction automatically for the first DB command.
        user = db.execute(select(User).where(User.user_id == user_id).with_for_update()).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        if user.total_balance < payload.amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")

        rfid_uid = payload.rfid_uid
        if rfid_uid is not None:
            card = db.execute(select(RFIDCard).where(RFIDCard.rfid_uid == rfid_uid)).scalar_one_or_none()
            if card is None or card.user_id != user_id:
                raise HTTPException(status_code=400, detail="RFID card does not belong to user")

        transaction_type = (
            TransactionType.DONATE_STK
            if payload.type == "DONATE_STK"
            else TransactionType.TRANSFER_TRANSIT
        )

        transaction = Transaction(
            transaction_id=uuid.uuid4(),
            user_id=user_id,
            rfid_uid=rfid_uid,
            type=transaction_type,
            amount=payload.amount,
            partner_id=payload.partner_id,
            timestamp=datetime.now(timezone.utc),
        )

        user.total_balance = user.total_balance - payload.amount
        db.add(transaction)

        # COMMIT: balance deduction and immutable ledger record are committed together.
        db.commit()
        db.refresh(transaction)
        db.refresh(user)

        return transaction, user.total_balance

    except HTTPException:
        # ROLLBACK: business-rule failures must leave no partial database state.
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        # ROLLBACK: infrastructure/database failures also revert all statements.
        db.rollback()
        raise HTTPException(status_code=500, detail="Database transaction failed") from exc