"""One error shape for every failure: {"error": {"code", "message", "details", "request_id"}}."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("iris_api")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None,
                 headers: Optional[dict[str, str]] = None):
        self.status, self.code, self.message, self.details, self.headers = status, code, message, details, headers or {}


def _body(request: Request, code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details,
                      "request_id": getattr(request.state, "request_id", "-")}}


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(request: Request, e: ApiError):
        return JSONResponse(_body(request, e.code, e.message, e.details), e.status, headers=e.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, e: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in err["loc"] if p != "body"), "problem": err["msg"]}
                   for err in e.errors()]
        return JSONResponse(_body(request, "validation_error", "Request failed validation.", details), 422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, e: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(e.status_code, "http_error")
        return JSONResponse(_body(request, code, str(e.detail)), e.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, e: Exception):
        log.exception("unhandled error request_id=%s", getattr(request.state, "request_id", "-"))
        return JSONResponse(_body(request, "internal_error", "Internal server error."), 500)
