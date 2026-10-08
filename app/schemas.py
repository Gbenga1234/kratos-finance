import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TransferCreate(BaseModel):
    source_account_id: str = Field(min_length=1, max_length=100)
    destination_account_id: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("Currency must be a three-letter code")
        return normalized

    @model_validator(mode="after")
    def validate_accounts(self) -> "TransferCreate":
        if self.source_account_id == self.destination_account_id:
            raise ValueError("Source and destination accounts must be different")
        return self


class TransferRead(BaseModel):
    id: str
    source_account_id: str
    destination_account_id: str
    amount: Decimal
    currency: str
    status: Literal["pending", "processing", "completed", "failed"]
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
