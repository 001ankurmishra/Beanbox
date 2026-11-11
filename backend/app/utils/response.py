from typing import Any, Optional

from fastapi.responses import JSONResponse
from pydantic import BaseModel


def serialize_camel(value: Any) -> Any:
    """Recursively converts Pydantic CamelModel instances to camelCase JSON-ready structures."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=False)
    if isinstance(value, list):
        return [serialize_camel(item) for item in value]
    if isinstance(value, tuple):
        return [serialize_camel(item) for item in value]
    if isinstance(value, dict):
        return {k: serialize_camel(v) for k, v in value.items()}
    return value


def make_success_response(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": True, "data": serialize_camel(data)},
    )


def make_error_payload(
    code: str,
    message: str,
    request_id: Optional[str] = None,
    details: Optional[Any] = None,
) -> dict[str, Any]:
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error_obj["details"] = serialize_camel(details)
    payload: dict[str, Any] = {"success": False, "error": error_obj}
    if request_id:
        payload["requestId"] = request_id
    return payload
