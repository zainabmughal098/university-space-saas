"""Consistent public errors without SQL, credentials, or echoed request bodies."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


class APIError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, *, details: dict | None = None):
        super().__init__(status_code, detail={"code": code, "message": message, **(details or {})})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        detail = error.detail if isinstance(error, APIError) else {
            "code": "http_error", "message": str(error.detail),
        }
        return JSONResponse(status_code=error.status_code, content={"detail": detail}, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": {
            "code": "validation_error", "message": "Invalid request fields, identifiers, or query parameters.",
        }})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail": {
            "code": "database_unavailable", "message": "The database operation could not be completed.",
        }})
