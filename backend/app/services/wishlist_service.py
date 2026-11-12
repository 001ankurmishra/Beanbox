from __future__ import annotations

from app.models.domain import Product
from app.repositories.interfaces import ProductRepository, WishlistRepository
from app.utils.errors import NotFoundError


class WishlistService:
    def __init__(
        self, wishlist_repo: WishlistRepository, product_repo: ProductRepository
    ) -> None:
        self._wishlist_repo = wishlist_repo
        self._product_repo = product_repo

    def list(self, user_id: str) -> list[Product]:
        entries = self._wishlist_repo.list_by_user_id(user_id)
        products: list[Product] = []
        for entry in entries:
            product = self._product_repo.find_by_id(entry.product_id)
            if product and product.is_active:
                products.append(product)
        return products

    def add(self, user_id: str, product_id: str) -> list[Product]:
        product = self._product_repo.find_by_id(product_id)
        if not product or not product.is_active:
            raise NotFoundError("Product not found")
        self._wishlist_repo.add(user_id, product_id)
        return self.list(user_id)

    def remove(self, user_id: str, product_id: str) -> list[Product]:
        removed = self._wishlist_repo.remove(user_id, product_id)
        if not removed:
            raise NotFoundError("Wishlist item not found")
        return self.list(user_id)
