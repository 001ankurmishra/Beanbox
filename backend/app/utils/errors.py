from typing import Any, Optional


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class BadRequestError(AppError):
    def __init__(
        self,
        message: str,
        details: Optional[Any] = None,
        code: str = "BAD_REQUEST",
    ) -> None:
        super().__init__(400, code, message, details)


class ValidationAppError(AppError):
    def __init__(
        self,
        message: str = "Request validation failed",
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(400, "VALIDATION_ERROR", message, details)


class UnauthorizedError(AppError):
    def __init__(
        self,
        message: str = "Authentication required",
        code: str = "UNAUTHORIZED",
    ) -> None:
        super().__init__(401, code, message)


class ForbiddenError(AppError):
    def __init__(
        self,
        message: str = "Insufficient permissions",
        code: str = "FORBIDDEN",
    ) -> None:
        super().__init__(403, code, message)


class NotFoundError(AppError):
    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "NOT_FOUND",
    ) -> None:
        super().__init__(404, code, message)


class ConflictError(AppError):
    def __init__(
        self,
        message: str,
        details: Optional[Any] = None,
        code: str = "CONFLICT",
    ) -> None:
        super().__init__(409, code, message, details)


class TooManyRequestsError(AppError):
    def __init__(
        self,
        message: str = "Too many requests, please try again later",
        code: str = "RATE_LIMIT_EXCEEDED",
    ) -> None:
        super().__init__(429, code, message)
