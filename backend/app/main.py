"""Minimal API entry point. Business features will be added in later phases."""

from fastapi import FastAPI

app = FastAPI(title="University Space API", version="0.1.0")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report process health; no external services are configured yet."""
    return {"status": "ok"}
