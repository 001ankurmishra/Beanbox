import math

from app.models.domain import Review
from app.repositories.interfaces import (
    CreateReviewInput,
    OrderRepository,
    ProductRepository,
    ReviewRepository,
    UserRepository,
)
from app.schemas.common import PaginationMeta
from app.utils.errors import ConflictError, ForbiddenError, NotFoundError


class ReviewService:
    def __init__(
        self,
        review_repo: ReviewRepository,
        product_repo: ProductRepository,
        order_repo: OrderRepository,
        user_repo: UserRepository,
    ) -> None:
        self._review_repo = review_repo
        self._product_repo = product_repo
        self._order_repo = order_repo
        self._user_repo = user_repo

    def list_for_product_slug(self, slug: str, page: int, limit: int) -> dict:
        product = self._product_repo.find_by_slug(slug)
        if not product or not product.is_active:
            raise NotFoundError("Product not found")

        items, total, stats = self._review_repo.list_by_product_id(
            product.id, page, limit
        )
        total_pages = max(1, math.ceil(total / limit))
        return {
            "items": items,
            "stats": stats,
            "pagination": PaginationMeta(
                page=page,
                limit=limit,
                total_items=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
        }

    def create_for_product_slug(
        self, user_id: str, slug: str, rating: int, title: str, comment: str
    ) -> Review:
        product = self._product_repo.find_by_slug(slug)
        if not product or not product.is_active:
            raise NotFoundError("Product not found")

        if not self._order_repo.has_verified_purchase(user_id, product.id):
            raise ForbiddenError(
                "Only verified buyers who purchased this item can leave a review",
                code="VERIFIED_PURCHASE_REQUIRED",
            )

        if self._review_repo.find_by_user_and_product(user_id, product.id):
            raise ConflictError(
                "You have already reviewed this product",
                code="DUPLICATE_REVIEW",
            )

        user = self._user_repo.find_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        review = self._review_repo.create(
            CreateReviewInput(
                product_id=product.id,
                user_id=user_id,
                user_name=user.name,
                rating=rating,
                title=title.strip(),
                comment=comment.strip(),
                verified_purchase=True,
            )
        )
        stats = self._review_repo.get_stats_for_product(product.id)
        self._product_repo.update_rating_stats(
            product.id, stats.average, stats.count
        )
        return review

    def delete_review(self, review_id: str, user_id: str, is_admin: bool) -> None:
        review = (
            self._review_repo.find_by_id(review_id)
            if is_admin
            else self._review_repo.find_by_id_for_user(review_id, user_id)
        )
        if not review or (not is_admin and review.user_id != user_id):
            raise NotFoundError("Review not found")

        deleted = (
            self._review_repo.delete(review.id)
            if is_admin
            else self._review_repo.delete_for_user(review.id, user_id)
        )
        if not deleted:
            raise NotFoundError("Review not found")
        stats = self._review_repo.get_stats_for_product(review.product_id)
        self._product_repo.update_rating_stats(
            review.product_id, stats.average, stats.count
        )
