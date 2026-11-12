import json
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.dependencies import (
    AuthPrincipal,
    get_app_settings,
    get_services,
    require_auth,
    require_verified,
)
from app.schemas.order import (
    CreatePaymentSessionRequest,
    TriggerMockPaymentRequest,
)
from app.services import Services
from app.services.payment_service import sign_mock_webhook_payload
from app.utils.errors import BadRequestError, NotFoundError
from app.utils.response import make_success_response

router = APIRouter(prefix="/api/payments", tags=["Payments"])


@router.post("/checkout-session")
def create_checkout_session(
    body: CreatePaymentSessionRequest,
    principal: AuthPrincipal = Depends(require_verified),
    services: Services = Depends(get_services),
):
    session = services.order_service.create_payment_session(
        principal.id, body.order_id
    )
    return make_success_response({"session": session}, status_code=201)


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    services: Services = Depends(get_services),
):
    raw_body = await request.body()
    if not raw_body:
        raise BadRequestError("Webhook requires raw application/json payload")

    signature = (
        request.headers.get("stripe-signature")
        or request.headers.get("x-mock-signature")
        or ""
    )
    result = services.order_service.handle_payment_webhook(raw_body, signature)
    return JSONResponse(status_code=200, content=result)


@router.post("/mock/trigger")
def trigger_mock_payment(
    body: TriggerMockPaymentRequest,
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    if settings.app_env == "production" or services.payment_provider.name != "mock":
        raise NotFoundError("Mock payment trigger is disabled")

    order = services.order_service.get_order_for_user(
        body.order_id, principal.id, False
    )
    event_type = (
        "checkout.session.completed"
        if body.outcome == "success"
        else "checkout.session.expired"
        if body.outcome == "expired"
        else "payment_intent.payment_failed"
    )

    payload = {
        "id": f"evt_mock_{uuid4().hex}",
        "type": event_type,
        "data": {
            "orderId": order.id,
            "sessionId": order.payment_session_id,
            "paymentIntentId": order.payment_intent_id or f"mock_pi_{uuid4().hex[:12]}",
            "amountPaise": order.pricing.total_paise,
            "currency": "INR",
        },
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    signature = sign_mock_webhook_payload(raw_bytes, settings.mock_webhook_secret)
    webhook_res = services.order_service.handle_payment_webhook(raw_bytes, signature)
    updated_order = services.order_service.get_order_for_user(
        order.id, principal.id, False
    )
    return make_success_response({"webhookResult": webhook_res, "order": updated_order})
