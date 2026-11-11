from fastapi import APIRouter, Depends, Path

from app.dependencies import AuthPrincipal, get_services, require_auth
from app.repositories.interfaces import CreateAddressInput, UpdateAddressInput
from app.schemas.address import CreateAddressRequest, UpdateAddressRequest
from app.services import Services
from app.utils.response import make_success_response

router = APIRouter(prefix="/api/addresses", tags=["Addresses"])


@router.get("")
def list_addresses(
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    return make_success_response({"items": services.address_service.list(principal.id)})


@router.post("")
def create_address(
    body: CreateAddressRequest,
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    addr = services.address_service.create(
        CreateAddressInput(
            user_id=principal.id,
            label=body.label,
            full_name=body.full_name,
            phone=body.phone,
            line1=body.line1,
            line2=body.line2,
            city=body.city,
            state=body.state,
            postal_code=body.postal_code,
            is_default=body.is_default,
        )
    )
    return make_success_response({"address": addr}, status_code=201)


@router.patch("/{address_id}")
def update_address(
    body: UpdateAddressRequest,
    address_id: str = Path(min_length=1, max_length=120),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    patch = body.model_dump(exclude_unset=True)
    addr = services.address_service.update(
        address_id, principal.id, UpdateAddressInput(**patch)
    )
    return make_success_response({"address": addr})


@router.delete("/{address_id}")
def delete_address(
    address_id: str = Path(min_length=1, max_length=120),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    services.address_service.remove(address_id, principal.id)
    return make_success_response({"message": "Address deleted"})


@router.patch("/{address_id}/default")
def set_default_address(
    address_id: str = Path(min_length=1, max_length=120),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    addr = services.address_service.set_default(address_id, principal.id)
    return make_success_response({"address": addr})
