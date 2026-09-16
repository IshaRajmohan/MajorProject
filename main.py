"""Backward-compatible entrypoint. Prefer: uvicorn app.main:app --reload """
from app.main import app

__all__ = ["app"]
