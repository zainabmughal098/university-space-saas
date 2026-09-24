"""API composition and process health."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import register_error_handlers
from app.routes import router
from app.reservation_routes import router as reservation_router

app = FastAPI(title="University Space API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Accept", "Content-Type"],
)
register_error_handlers(app)
app.include_router(router)
app.include_router(reservation_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report process health independently of database availability."""
    return {"status": "ok"}
