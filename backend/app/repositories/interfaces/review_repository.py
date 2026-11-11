from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.models.domain import CamelModel, Review


@dataclass
class CreateReviewInput:
    product_id: str
    user_id: str
    user_name: str
    rating: int
    title: str
    comment: str
    verified_purchase: bool


class ReviewStats(CamelModel):
    average: float
    count: int
    distribution: dict[int, int]


class ReviewRepository(ABC):
    @abstractmethod
    def list_by_product_id(
        self, product_id: str, page: int, limit: int
    ) -> tuple[list[Review], int, ReviewStats]: ...

    @abstractmethod
    def find_by_id(self, review_id: str) -> Optional[Review]: ...

    @abstractmethod
    def find_by_user_and_product(
        self, user_id: str, product_id: str
    ) -> Optional[Review]: ...

    @abstractmethod
    def create(self, data: CreateReviewInput) -> Review: ...

    @abstractmethod
    def delete(self, review_id: str) -> bool: ...

    @abstractmethod
    def get_stats_for_product(self, product_id: str) -> ReviewStats: ...
