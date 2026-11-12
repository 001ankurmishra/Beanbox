from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import Review
from app.repositories.interfaces import (
    CreateReviewInput,
    ReviewRepository,
    ReviewStats,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _compute_stats(reviews: list[Review]) -> ReviewStats:
    distribution: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    if not reviews:
        return ReviewStats(average=0.0, count=0, distribution=distribution)

    total_rating = 0
    for r in reviews:
        total_rating += r.rating
        distribution[r.rating] = distribution.get(r.rating, 0) + 1

    return ReviewStats(
        average=round(total_rating / len(reviews), 2),
        count=len(reviews),
        distribution=distribution,
    )


class InMemoryReviewRepository(ReviewRepository):
    def __init__(self, initial_reviews: Optional[list[Review]] = None) -> None:
        self._lock = RLock()
        self._reviews: list[Review] = [
            r.model_copy(deep=True) for r in (initial_reviews or [])
        ]

    def list_by_product_id(
        self, product_id: str, page: int, limit: int
    ) -> tuple[list[Review], int, ReviewStats]:
        with self._lock:
            product_reviews = [r for r in self._reviews if r.product_id == product_id]
            product_reviews.sort(key=lambda r: r.created_at, reverse=True)
            stats = _compute_stats(product_reviews)
            total = len(product_reviews)
            start = (page - 1) * limit
            items = [
                r.model_copy(deep=True) for r in product_reviews[start : start + limit]
            ]
            return items, total, stats

    def find_by_id(self, review_id: str) -> Optional[Review]:
        with self._lock:
            for r in self._reviews:
                if r.id == review_id:
                    return r.model_copy(deep=True)
            return None

    def find_by_id_for_user(
        self, review_id: str, user_id: str
    ) -> Optional[Review]:
        with self._lock:
            for r in self._reviews:
                if r.id == review_id and r.user_id == user_id:
                    return r.model_copy(deep=True)
            return None

    def find_by_user_and_product(
        self, user_id: str, product_id: str
    ) -> Optional[Review]:
        with self._lock:
            for r in self._reviews:
                if r.user_id == user_id and r.product_id == product_id:
                    return r.model_copy(deep=True)
            return None

    def create(self, data: CreateReviewInput) -> Review:
        now = _now_iso()
        review = Review(
            id=str(uuid4()),
            product_id=data.product_id,
            user_id=data.user_id,
            user_name=data.user_name,
            rating=data.rating,
            title=data.title,
            comment=data.comment,
            verified_purchase=data.verified_purchase,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._reviews.append(review.model_copy(deep=True))
        return review

    def delete(self, review_id: str) -> bool:
        with self._lock:
            before = len(self._reviews)
            self._reviews = [r for r in self._reviews if r.id != review_id]
            return len(self._reviews) < before

    def delete_for_user(self, review_id: str, user_id: str) -> bool:
        with self._lock:
            before = len(self._reviews)
            self._reviews = [
                r
                for r in self._reviews
                if not (r.id == review_id and r.user_id == user_id)
            ]
            return len(self._reviews) < before

    def get_stats_for_product(self, product_id: str) -> ReviewStats:
        with self._lock:
            product_reviews = [r for r in self._reviews if r.product_id == product_id]
            return _compute_stats(product_reviews)
