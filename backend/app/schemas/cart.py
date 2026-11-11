from pydantic import Field

from app.models.domain import CamelModel


class AddToCartRequest(CamelModel):
    product_id: str = Field(min_length=1, max_length=120)
    variant_id: str = Field(min_length=1, max_length=120)
    quantity: int = Field(default=1, ge=1, le=20)


class UpdateCartItemRequest(CamelModel):
    quantity: int = Field(ge=0, le=20)
