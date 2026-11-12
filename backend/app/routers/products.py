from typing import Literal, Optional

from fastapi import APIRouter, Depends, Path, Query, Request

from app.dependencies import AuthPrincipal, get_services, require_auth
from app.models.domain import ProductCategory, RoastLevel
from app.repositories.interfaces import ProductListQuery
from app.schemas.review import CreateReviewRequest
from app.services import Services
from app.utils.response import make_success_response

products_router = APIRouter(prefix="/api/products", tags=["Products & Reviews"])
reviews_router = APIRouter(prefix="/api/reviews", tags=["Products & Reviews"])


@products_router.get("")
def list_products(
    request: Request,
    search: Optional[str] = Query(default=None, max_length=100),
    category: Optional[ProductCategory] = Query(default=None),
    roast: Optional[RoastLevel] = Query(default=None),
    origin: Optional[str] = Query(default=None, max_length=80),
    min_price: Optional[float] = Query(default=None, alias="minPrice", ge=0, le=100000),
    max_price: Optional[float] = Query(default=None, alias="maxPrice", ge=0, le=100000),
    in_stock: Optional[bool] = Query(default=None, alias="inStock"),
    featured: Optional[bool] = Query(default=None),
    sort: Literal["newest", "price_asc", "price_desc", "rating_desc", "popular"] = Query(
        default="popular"
    ),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=12, ge=1, le=48),
    services: Services = Depends(get_services),
):
    query = ProductListQuery(
        search=search,
        category=category,
        roast=roast,
        origin=origin,
        min_price_paise=round(min_price * 100) if min_price is not None else None,
        max_price_paise=round(max_price * 100) if max_price is not None else None,
        in_stock_only=in_stock,
        featured_only=featured,
        sort=sort,
        page=page,
        limit=limit,
    )
    req_id = getattr(request.state, "request_id", "-")
    data, cache_hit = services.product_service.list_with_cache(query, request_id=req_id)
    res = make_success_response(data)
    res.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    return res


@products_router.get("/{slug}")
def product_detail(
    request: Request,
    slug: str = Path(min_length=1, max_length=160, pattern=r"^[a-z0-9-]+$"),
    services: Services = Depends(get_services),
):
    req_id = getattr(request.state, "request_id", "-")
    product, cache_hit = services.product_service.get_by_slug_with_cache(
        slug, request_id=req_id
    )
    res = make_success_response({"product": product})
    res.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    return res


@products_router.get("/{slug}/related")
def related_products(
    slug: str = Path(min_length=1, max_length=160, pattern=r"^[a-z0-9-]+$"),
    limit: int = Query(default=4, ge=1, le=8),
    services: Services = Depends(get_services),
):
    items = services.product_service.get_related_by_slug(slug, limit)
    return make_success_response({"items": items})


@products_router.get("/{slug}/reviews")
def list_reviews(
    slug: str = Path(min_length=1, max_length=160, pattern=r"^[a-z0-9-]+$"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=12, ge=1, le=50),
    services: Services = Depends(get_services),
):
    result = services.review_service.list_for_product_slug(slug, page, limit)
    return make_success_response(result)


@products_router.post("/{slug}/reviews")
def create_review(
    body: CreateReviewRequest,
    slug: str = Path(min_length=1, max_length=160, pattern=r"^[a-z0-9-]+$"),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    review = services.review_service.create_for_product_slug(
        user_id=principal.id,
        slug=slug,
        rating=body.rating,
        title=body.title,
        comment=body.comment,
    )
    return make_success_response({"review": review}, status_code=201)


@reviews_router.delete("/{review_id}")
def delete_review(
    review_id: str = Path(min_length=1, max_length=120),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    services.review_service.delete_review(
        review_id=review_id,
        user_id=principal.id,
        is_admin=principal.is_effective_admin,
        is_admin_role=principal.role == "admin",
    )
    return make_success_response({"message": "Review deleted"})
