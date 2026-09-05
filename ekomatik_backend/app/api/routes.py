"""FastAPI route definitions for the EkoMatik backend."""

import json
import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import RFIDCard, User
from app.schemas.schemas import (
    AddTransactionRequest,
    AddTransactionResponse,
    CardLinkRequest,
    CardLinkResponse,
    SpendRequest,
    SpendResponse,
    UserResponse,
    VisionResponse,
)
from app.services.transaction_service import add_ekomatik_earning, spend_balance
from app.utils.security import get_mock_user_id

router = APIRouter(prefix="/api/v1")


async def mock_ml_inference(image_bytes: bytes) -> dict:
    """Run a deliberately lightweight mock model for the prototype.

    The function accepts the compressed image bytes so its interface matches a real
    inference pipeline. It returns immediately with the requested fixed demo result.
    Replace this function with a real model invocation later.
    """

    # Reading the input length proves the upload was actually received while avoiding
    # expensive processing in the mock implementation.
    _ = len(image_bytes)
    return {"status": "success", "is_izmarit": True, "confidence": 0.96}


def _authenticated_user_id(authorization: str | None) -> uuid.UUID:
    """Return the authenticated user UUID using the development JWT verifier."""

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    return get_mock_user_id(authorization)


@router.post("/vision/analyze", response_model=VisionResponse)
async def analyze_vision(file: UploadFile = File(...)):
    """Accept a compressed Raspberry Pi image and return mock cigarette-butt detection."""

    image_bytes = await file.read()
    # Keep upload validation here as a simple defensive size cap for the prototype.
    # A production implementation should also validate MIME type and image dimensions.
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty image file")

    result = await mock_ml_inference(image_bytes)
    return VisionResponse(**result)


@router.post("/transactions/add", response_model=AddTransactionResponse)
def add_transaction(payload: AddTransactionRequest, db: Session = Depends(get_db)):
    """Credit the RFID card owner's balance after IoT HMAC validation middleware succeeds."""

    result = add_ekomatik_earning(db, payload)
    return AddTransactionResponse(
        status="success",
        transaction_id=result.transaction_id,
        user_id=result.user_id,
        new_balance=result.new_balance,
    )


@router.post("/cards/link", response_model=CardLinkResponse)
def link_card(
    payload: CardLinkRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    """Link an RFID UID to the user represented by a mock JWT Bearer token."""

    user_id = _authenticated_user_id(authorization)
    user = db.execute(select(User).where(User.user_id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    card = db.execute(select(RFIDCard).where(RFIDCard.rfid_uid == payload.rfid_uid)).scalar_one_or_none()
    if card is None:
        card = RFIDCard(rfid_uid=payload.rfid_uid, user_id=user_id, is_active=True)
        db.add(card)
    else:
        if card.user_id != user_id and card.is_active:
            raise HTTPException(status_code=409, detail="RFID card is already linked to another user")
        card.user_id = user_id
        card.is_active = True

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to link RFID card") from exc

    return CardLinkResponse(status="success", rfid_uid=card.rfid_uid, user_id=card.user_id)


@router.post("/transactions/spend", response_model=SpendResponse)
def spend_transaction(
    payload: SpendRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    """Atomically deduct user balance and log a donation or transfer transaction."""

    user_id = _authenticated_user_id(authorization)
    transaction, new_balance = spend_balance(db, user_id, payload)
    return SpendResponse(
        status="success",
        transaction_id=transaction.transaction_id,
        user_id=user_id,
        new_balance=new_balance,
    )


@router.get("/users/me", response_model=UserResponse)
def get_current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    """Return the authenticated user's profile and current balance.

    Required by the Flutter mobile client (HomeView) to display and refresh
    the user's balance on load and after donations.
    """

    user_id = _authenticated_user_id(authorization)
    user = db.execute(select(User).where(User.user_id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return user