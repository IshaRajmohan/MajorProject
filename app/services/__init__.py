"""OWNER: shared services package."""
from app.services.gemini_service import GeminiService, get_gemini_service

__all__ = ["GeminiService", "get_gemini_service"]
