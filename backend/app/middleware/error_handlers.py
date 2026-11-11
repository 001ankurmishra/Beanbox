import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils.errors import AppError
from app.utils.response import make_error_payload

logger = logging.getLogger("beanbox.errors")


def _get_req_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_exception_handlers(app: FastAPI, is_test: bool = False) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=make_error_payload(
                code=exc.code,
                message=exc.message,
                request_id=_get_req_id(request),
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "path": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
                "message": err.get("msg", "Invalid value"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content=make_error_payload(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                request_id=_get_req_id(request),
                details=details,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = "ROUTE_NOT_FOUND" if exc.status_code == 404 else f"HTTP_{exc.status_code}"
        message = (
            f"Cannot {request.method} {request.url.path}"
            if exc.status_code == 404
            else str(exc.detail)
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=make_error_payload(
                code=code,
                message=message,
                request_id=_get_req_id(request),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        req_id = _get_req_id(request)
        if not is_test:
            logger.exception("Unhandled error req=%s", req_id, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=make_error_payload(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected error occurred",
                request_id=req_id,
            ),
        )
