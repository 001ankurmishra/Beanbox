from datetime import datetime, timezone
from typing import Optional

from app.models.domain import CamelModel, Cart, CartItem
from app.repositories.interfaces import CartRepository, ProductRepository
from app.services.pricing_service import (
    FREE_SHIPPING_THRESHOLD_PAISE,
    calculate_order_pricing,
)
from app.utils.errors import BadRequestError, ConflictError, NotFoundError


class HydratedCartItem(CamelModel):
    product_id: str
    variant_id: str
    product_name: str
    product_slug: str
    variant_label: str
    sku: str
    image: str
    unit_price_paise: int
    quantity: int
    line_total_paise: int
    available_stock: int
    in_stock: bool


class HydratedCart(CamelModel):
    items: list[HydratedCartItem]
    item_count: int
    items_subtotal_paise: int
    estimated_gst_paise: int
    estimated_shipping_paise: int
    estimated_total_paise: int
    free_shipping_threshold_paise: int
    amount_to_free_shipping_paise: int


class CartOwner:
    def __init__(
        self, user_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> None:
        self.user_id = user_id
        self.session_id = session_id


class CartService:
    def __init__(
        self, cart_repo: CartRepository, product_repo: ProductRepository
    ) -> None:
        self._cart_repo = cart_repo
        self._product_repo = product_repo

    def _get_cart(self, owner: CartOwner) -> Optional[Cart]:
        if owner.user_id:
            return self._cart_repo.find_by_user_id(owner.user_id)
        if owner.session_id:
            return self._cart_repo.find_by_session_id(owner.session_id)
        return None

    def _save_items(self, owner: CartOwner, items: list[CartItem]) -> Cart:
        if owner.user_id:
            return self._cart_repo.upsert_for_user(owner.user_id, items)
        assert owner.session_id is not None
        return self._cart_repo.upsert_for_session(owner.session_id, items)

    def hydrate(self, cart: Optional[Cart]) -> HydratedCart:
        raw_items = cart.items if cart else []
        hydrated_items: list[HydratedCartItem] = []
        items_subtotal_paise = 0
        item_count = 0

        for item in raw_items:
            resolved = self._product_repo.find_variant_by_id(
                item.product_id, item.variant_id
            )
            if not resolved:
                continue
            product, variant = resolved
            if not product.is_active:
                continue

            line_total = variant.price_paise * item.quantity
            items_subtotal_paise += line_total
            item_count += item.quantity

            hydrated_items.append(
                HydratedCartItem(
                    product_id=product.id,
                    variant_id=variant.id,
                    product_name=product.name,
                    product_slug=product.slug,
                    variant_label=variant.label,
                    sku=variant.sku,
                    image=product.images[0]
                    if product.images
                    else "/images/products/beans-medium.svg",
                    unit_price_paise=variant.price_paise,
                    quantity=item.quantity,
                    line_total_paise=line_total,
                    available_stock=variant.stock,
                    in_stock=variant.stock >= item.quantity and variant.stock > 0,
                )
            )

        pricing = calculate_order_pricing(items_subtotal_paise)
        amount_to_free = max(0, FREE_SHIPPING_THRESHOLD_PAISE - items_subtotal_paise)

        return HydratedCart(
            items=hydrated_items,
            item_count=item_count,
            items_subtotal_paise=pricing.items_subtotal_paise,
            estimated_gst_paise=pricing.gst_paise,
            estimated_shipping_paise=pricing.shipping_paise,
            estimated_total_paise=pricing.total_paise,
            free_shipping_threshold_paise=FREE_SHIPPING_THRESHOLD_PAISE,
            amount_to_free_shipping_paise=amount_to_free,
        )

    def get_hydrated_cart(self, owner: CartOwner) -> HydratedCart:
        return self.hydrate(self._get_cart(owner))

    def add_item(
        self, owner: CartOwner, product_id: str, variant_id: str, quantity: int
    ) -> HydratedCart:
        if quantity < 1 or quantity > 20:
            raise BadRequestError("Quantity must be between 1 and 20")

        resolved = self._product_repo.find_variant_by_id(product_id, variant_id)
        if not resolved or not resolved[0].is_active:
            raise NotFoundError("Product variant not found")

        product, variant = resolved
        cart = self._get_cart(owner)
        items = list(cart.items) if cart else []

        existing_idx = next(
            (
                idx
                for idx, i in enumerate(items)
                if i.product_id == product_id and i.variant_id == variant_id
            ),
            -1,
        )
        existing_qty = items[existing_idx].quantity if existing_idx >= 0 else 0
        next_qty = existing_qty + quantity

        if next_qty > variant.stock:
            raise ConflictError(
                f"Only {variant.stock} unit(s) available for {product.name} ({variant.label})",
                details={"availableStock": variant.stock, "requested": next_qty},
                code="INSUFFICIENT_STOCK",
            )

        if existing_idx >= 0:
            items[existing_idx].quantity = next_qty
        else:
            items.append(
                CartItem(
                    product_id=product_id,
                    variant_id=variant_id,
                    quantity=quantity,
                    added_at=datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                )
            )

        saved = self._save_items(owner, items)
        return self.hydrate(saved)

    def update_item_quantity(
        self, owner: CartOwner, variant_id: str, quantity: int
    ) -> HydratedCart:
        cart = self._get_cart(owner)
        items = list(cart.items) if cart else []
        idx = next(
            (i for i, item in enumerate(items) if item.variant_id == variant_id), -1
        )
        if idx == -1:
            raise NotFoundError("Cart item not found")

        if quantity <= 0:
            items.pop(idx)
            saved = self._save_items(owner, items)
            return self.hydrate(saved)

        if quantity > 20:
            raise BadRequestError("Maximum 20 units per item allowed")

        target = items[idx]
        resolved = self._product_repo.find_variant_by_id(
            target.product_id, target.variant_id
        )
        if not resolved or not resolved[0].is_active:
            items.pop(idx)
            saved = self._save_items(owner, items)
            return self.hydrate(saved)

        product, variant = resolved
        if quantity > variant.stock:
            raise ConflictError(
                f"Only {variant.stock} unit(s) available for {product.name} ({variant.label})",
                details={"availableStock": variant.stock, "requested": quantity},
                code="INSUFFICIENT_STOCK",
            )

        items[idx].quantity = quantity
        saved = self._save_items(owner, items)
        return self.hydrate(saved)

    def remove_item(self, owner: CartOwner, variant_id: str) -> HydratedCart:
        cart = self._get_cart(owner)
        existing_items = list(cart.items) if cart else []
        if not any(i.variant_id == variant_id for i in existing_items):
            raise NotFoundError("Cart item not found")
        items = [i for i in existing_items if i.variant_id != variant_id]
        saved = self._save_items(owner, items)
        return self.hydrate(saved)

    def clear(self, owner: CartOwner) -> HydratedCart:
        if owner.user_id:
            self._cart_repo.clear_for_user(owner.user_id)
        elif owner.session_id:
            self._cart_repo.clear_for_session(owner.session_id)
        return self.hydrate(None)

    def merge_guest_cart_into_user(self, session_id: str, user_id: str) -> None:
        if not session_id:
            return
        guest_cart = self._cart_repo.find_by_session_id(session_id)
        if not guest_cart or not guest_cart.items:
            self._cart_repo.delete_by_session_id(session_id)
            return

        user_cart = self._cart_repo.find_by_user_id(user_id)
        merged: dict[tuple[str, str], CartItem] = {}
        for item in user_cart.items if user_cart else []:
            merged[(item.product_id, item.variant_id)] = item.model_copy(deep=True)

        for guest_item in guest_cart.items:
            resolved = self._product_repo.find_variant_by_id(
                guest_item.product_id, guest_item.variant_id
            )
            if not resolved:
                continue
            product, variant = resolved
            if not product.is_active or variant.stock <= 0:
                continue

            key = (guest_item.product_id, guest_item.variant_id)
            existing = merged.get(key)
            combined = (existing.quantity if existing else 0) + guest_item.quantity
            capped = min(combined, variant.stock, 20)
            if capped > 0:
                merged[key] = CartItem(
                    product_id=guest_item.product_id,
                    variant_id=guest_item.variant_id,
                    quantity=capped,
                    added_at=existing.added_at if existing else guest_item.added_at,
                )

        self._cart_repo.upsert_for_user(user_id, list(merged.values()))
        self._cart_repo.delete_by_session_id(session_id)
