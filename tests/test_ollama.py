import json

import httpx
import pytest

from app.ai.ollama import LLMUnavailableError, OllamaClient


@pytest.mark.asyncio
async def test_ollama_uses_local_json_endpoint_and_token_bound() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "127.0.0.1"
        assert request.url.path == "/api/generate"
        payload = json.loads(request.content)
        assert payload["format"] == "json"
        assert payload["options"]["num_predict"] == 180
        return httpx.Response(200, json={"response": '{"draft":"Hello."}'})

    client = OllamaClient(transport=httpx.MockTransport(handle))

    assert await client.generate_json("Make a draft") == '{"draft":"Hello."}'


def test_ollama_rejects_remote_hosts() -> None:
    with pytest.raises(ValueError, match="loopback"):
        OllamaClient(base_url="https://ollama.com")


@pytest.mark.asyncio
async def test_ollama_surfaces_service_failure() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = OllamaClient(transport=httpx.MockTransport(handle))

    with pytest.raises(LLMUnavailableError, match="HTTP 503"):
        await client.generate_json("Make a draft")
