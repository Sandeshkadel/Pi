import asyncio

import pytest

from app.ai.intent_router import IntentRouter


def test_stop_command_precedes_rules_and_local_model() -> None:
    router = IntentRouter()

    intent = asyncio.run(router.route("Hey Pi, stop"))

    assert intent.name == "stop_agent"


@pytest.mark.asyncio
async def test_open_youtube_is_deterministic_without_llm() -> None:
    intent = await IntentRouter().route("Open YouTube")

    assert intent.name == "open_app"
    assert intent.app == "YouTube"
    assert intent.confidence == 1


@pytest.mark.asyncio
async def test_polite_reply_request_is_routed_for_drafting() -> None:
    intent = await IntentRouter().route(
        "Write a polite reply saying I cannot come today."
    )

    assert intent.name == "draft_reply"
    assert intent.request is not None


@pytest.mark.asyncio
async def test_stop_negative_phrase_does_not_cancel() -> None:
    intent = await IntentRouter().route("Please do not stop the music")

    assert intent.name == "unknown"


@pytest.mark.asyncio
async def test_llm_classifier_is_limited_to_registered_apps() -> None:
    class FakeLLM:
        async def generate_json(self, prompt: str) -> str:
            assert "untrusted data" in prompt
            return '{"intent":"open_app","app":"TikTok","confidence":0.95}'

    intent = await IntentRouter(llm=FakeLLM()).route("launch the short video app")

    assert intent.name == "unknown"
    assert intent.app is None


@pytest.mark.asyncio
async def test_unknown_request_has_no_untrusted_action() -> None:
    intent = await IntentRouter().route("Delete my account")

    assert intent.name == "unknown"
    assert intent.app is None
