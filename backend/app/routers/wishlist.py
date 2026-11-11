from fastapi import APIRouter, Depends, Path

from app.dependencies import AuthPrincipal, get_services, require_auth
from app.services import Services
from app.utils.response import make_success_response

router = APIRouter(prefix="/api/wishlist", tags=["Wishlist"])


@router.get("")
def list_wishlist(
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    return make_success_response({"items": services.wishlist_service.list(principal.id)})


@router.post("/{product_id}")
def add_to_wishlist(
    product_id: str = Path(min_length=1, max_length=120),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    items = services.wishlist_service.add(principal.id, product_id)
    return make_success_response({"items": items}, status_code=201)


@router.delete("/{product_id}")
def remove_from_wishlist(
    product_id: str = Path(min_length=1, max_length=120),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    items = services.wishlist_service.remove(principal.id, product_id)
    return make_success_response({"items": items})
