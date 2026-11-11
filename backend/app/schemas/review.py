from pydantic import Field

from app.models.domain import CamelModel


class CreateReviewRequest(CamelModel):
    rating: int = Field(ge=1, le=5)
    title: str = Field(min_length=3, max_length=100)
    comment: str = Field(min_length=5, max_length=1000)
