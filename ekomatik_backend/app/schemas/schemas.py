"""Pydantic request and response DTOs used by the REST API."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class VisionResponse(BaseModel):
    """Response returned by the mock vision inference endpoint."""

    status: str
    is_izmarit: bool
    confidence: float = Field(ge=0.0, le=1.0)


class AddTransactionRequest(BaseModel):
    """Payload received from an IoT EkoMatik device."""

    rfid_uid: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(gt=0, decimal_places=2)
    timestamp: int = Field(gt=0, description="Unix epoch timestamp in seconds")


class AddTransactionResponse(BaseModel):
    """Response returned after a successful EkoMatik earning transaction."""

    status: str
    transaction_id: uuid.UUID
    user_id: uuid.UUID
    new_balance: Decimal


class CardLinkRequest(BaseModel):
    """Payload used by the mobile app to attach an RFID card to the authenticated user."""

    rfid_uid: str = Field(min_length=1, max_length=64)


class CardLinkResponse(BaseModel):
    """Result of linking an RFID card."""

    status: str
    rfid_uid: str
    user_id: uuid.UUID


class SpendRequest(BaseModel):
    """Payload for donation or transfer spending operations."""

    type: str = Field(pattern="^(DONATE_STK|TRANSFER_TRANSIT)$")
    amount: Decimal = Field(gt=0, decimal_places=2)
    partner_id: str = Field(min_length=1, max_length=128)
    rfid_uid: str | None = Field(default=None, max_length=64)


class SpendResponse(BaseModel):
    """Result returned after an atomic balance deduction and ledger insert."""

    status: str
    transaction_id: uuid.UUID
    user_id: uuid.UUID
    new_balance: Decimal


class UserCreate(BaseModel):
    """Optional utility schema for creating a development/test user."""

    full_name: str
    email: EmailStr
    password_hash: str


class UserResponse(BaseModel):
    """Safe user representation that does not expose password hashes."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    full_name: str
    email: EmailStr
    total_balance: Decimal