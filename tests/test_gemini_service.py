"""Tests for GeminiService — no live API calls."""
import pytest

from app.services.gemini_service import (
    GeminiConfigError,
    GeminiRequestError,
    GeminiService,
)


def test_missing_api_key_raises_clear_error():
    svc = GeminiService(api_key="", model="gemini-2.5-flash")
    assert svc.is_configured is False
    with pytest.raises(GeminiConfigError, match="GEMINI_API_KEY"):
        svc.generate_text("hello")


def test_empty_prompt_rejected():
    svc = GeminiService(api_key="fake-key", model="gemini-2.5-flash")
    with pytest.raises(ValueError, match="prompt"):
        svc.generate_text("   ")


def test_generate_text_uses_client(monkeypatch):
    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["model"] == "gemini-2.5-flash"
            assert kwargs["contents"] == "ping"

            class Resp:
                text = "pong"

            return Resp()

    class FakeClient:
        models = FakeModels()

    svc = GeminiService(api_key="fake-key", model="gemini-2.5-flash")
    svc._client = FakeClient()
    assert svc.generate_text("ping") == "pong"


def test_generate_maps_sdk_errors(monkeypatch):
    class FakeModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("network boom")

    class FakeClient:
        models = FakeModels()

    svc = GeminiService(api_key="fake-key", model="gemini-2.5-flash")
    svc._client = FakeClient()
    with pytest.raises(GeminiRequestError, match="Gemini request failed"):
        svc.generate_text("ping")
