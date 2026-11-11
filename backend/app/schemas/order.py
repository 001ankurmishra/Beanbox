from typing import Literal, Optional

from pydantic import Field

from app.models.domain import CamelModel


class CheckoutPreviewRequest(CamelModel):
    address_id: Optional[str] = Field(default=None, min_length=1, max_length=120)
    coupon_code: Optional[str] = Field(default=None, max_length=40)


class CreateOrderRequest(CamelModel):
    address_id: str = Field(min_length=1, max_length=120)
    coupon_code: Optional[str] = Field(default=None, max_length=40)


class CancelOrderRequest(CamelModel):
    reason: Optional[str] = Field(default=None, max_length=250)


class CreatePaymentSessionRequest(CamelModel):
    order_id: str = Field(min_length=1, max_length=120)


class TriggerMockPaymentRequest(CamelModel):
    order_id: str = Field(min_length=1, max_length=120)
    outcome: Literal["success", "failed", "expired"]
