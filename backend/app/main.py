"""API composition and process health."""

from fastapi import FastAPI

from app.errors import register_error_handlers
from app.routes import router
from app.reservation_routes import router as reservation_router

app = FastAPI(title="University Space API", version="0.1.0")
register_error_handlers(app)
app.include_router(router)
app.include_router(reservation_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report process health independently of database availability."""
    return {"status": "ok"}
