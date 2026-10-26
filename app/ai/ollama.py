"""Loopback-only async Ollama client."""

import json
from collections.abc import Mapping
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError


class LLMUnavailableError(RuntimeError):
    """Raised when the configured local model cannot produce a response."""


class _GenerateResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    response: str


class OllamaClient:
    """Call only an Ollama instance on this device; remote/cloud hosts are rejected."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:1.5b",
        timeout_seconds: float = 12,
        max_tokens: int = 180,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Ollama must use a loopback HTTP URL.")
        if not model.strip() or timeout_seconds <= 0 or max_tokens <= 0:
            raise ValueError("Model name, timeout, and token limit must be positive.")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._transport = transport

    async def generate_json(self, prompt: str) -> str:
        """Return a locally generated JSON string or raise an explicit availability error."""
        if not prompt.strip():
            raise ValueError("Prompt must not be empty.")
        payload: Mapping[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": self._max_tokens,
            },
        }

        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            transport=self._transport,
            trust_env=False,
        ) as client:
            try:
                response = await client.post("/api/generate", json=payload)
                response.raise_for_status()
            except httpx.TimeoutException as error:
                raise LLMUnavailableError("Local model request timed out.") from error
            except httpx.HTTPStatusError as error:
                raise LLMUnavailableError(
                    f"Local model returned HTTP {error.response.status_code}."
                ) from error
            except httpx.RequestError as error:
                raise LLMUnavailableError("Local model service is unavailable.") from error

        try:
            result = _GenerateResponse.model_validate(response.json())
        except (json.JSONDecodeError, ValidationError) as error:
            raise LLMUnavailableError("Local model returned an invalid response.") from error
        if not result.response.strip():
            raise LLMUnavailableError("Local model returned an empty response.")
        return result.response
