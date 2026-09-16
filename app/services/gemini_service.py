"""
Gemini LLM service for NyayaOS.

Uses the official google-genai SDK. Keeps API key handling and model calls
out of FastAPI routes. Does not connect to Gemini until a method is called.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiConfigError(RuntimeError):
    """Raised when Gemini is not configured (missing API key)."""


class GeminiRequestError(RuntimeError):
    """Raised when a Gemini API call fails."""


class GeminiService:
    """Thin wrapper around google-genai. Client is created lazily."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self._model = model or settings.GEMINI_MODEL
        self._client: Any | None = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def _require_key(self) -> str:
        if not self.is_configured:
            raise GeminiConfigError(
                "GEMINI_API_KEY is missing. Set it in your .env file."
            )
        return self._api_key.strip()  # type: ignore[union-attr]

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        api_key = self._require_key()
        try:
            from google import genai
        except ImportError as exc:
            raise GeminiConfigError(
                "google-genai is not installed. Run: pip install google-genai"
            ) from exc
        self._client = genai.Client(api_key=api_key)
        return self._client

    def generate_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Generate a text response for a single prompt.

        Does not log the API key or raw credentials. Call only when AI output
        is actually needed.
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

        client = self._get_client()
        use_model = model or self._model
        config: dict[str, Any] | None = None
        if temperature is not None:
            config = {"temperature": temperature}

        try:
            response = client.models.generate_content(
                model=use_model,
                contents=prompt,
                config=config,
            )
        except GeminiConfigError:
            raise
        except Exception as exc:  # noqa: BLE001 — map SDK errors to a clear type
            logger.exception("Gemini generate_content failed (model=%s)", use_model)
            raise GeminiRequestError(
                "Gemini request failed. Check GEMINI_API_KEY, model name, and network."
            ) from exc

        text = getattr(response, "text", None)
        if not text:
            raise GeminiRequestError("Gemini returned an empty response")
        return text


@lru_cache
def get_gemini_service() -> GeminiService:
    """Cached factory for dependency injection."""
    return GeminiService()
