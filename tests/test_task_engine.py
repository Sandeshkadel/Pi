import asyncio
import json
from uuid import uuid4

import aiosqlite
import pytest

from app.ai.intent_router import IntentRouter
from app.core.memory import MemoryStore
from app.core.task_engine import ActionDispatchError, TaskEngine


class FakeLLM:
    def __init__(self, response: str = '{"draft":"Sorry, I cannot come today."}') -> None:
        self.response = response
        self.prompts: list[str] = []

    async def generate_json(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class FakeDispatcher:
    def __init__(self) -> None:
        self.opened_apps: list[str] = []

    async def open_app(self, app: str) -> None:
        self.opened_apps.append(app)


class FailingDispatcher(FakeDispatcher):
    async def open_app(self, app: str) -> None:
        self.opened_apps.append(app)
        raise ActionDispatchError("test adapter failure")


@pytest.mark.asyncio
async def test_open_app_requires_task_bound_spoken_confirmation(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db")
    await memory.initialize()
    dispatcher = FakeDispatcher()
    engine = TaskEngine(
        IntentRouter(),
        dispatcher=dispatcher,
        memory=memory,
    )

    pending = await engine.handle("Open YouTube")

    assert pending.status == "confirmation_required"
    assert 'Say "do" to confirm' in pending.response
    assert dispatcher.opened_apps == []

    result = await engine.confirm_task(pending.task_id, "do")

    assert result.status == "completed"
    assert dispatcher.opened_apps == ["YouTube"]
    async with aiosqlite.connect(tmp_path / "piagent.db") as database:
        async with database.execute("SELECT COUNT(*) FROM actions_audit") as cursor:
            row = await cursor.fetchone()
    assert row is not None and row[0] == 2


@pytest.mark.asyncio
async def test_non_confirmation_cancels_pending_action(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db")
    await memory.initialize()
    dispatcher = FakeDispatcher()
    engine = TaskEngine(IntentRouter(), dispatcher=dispatcher, memory=memory)
    pending = await engine.handle("Open YouTube")

    result = await engine.confirm_task(pending.task_id, "maybe later")

    assert result.status == "cancelled"
    assert dispatcher.opened_apps == []


@pytest.mark.asyncio
async def test_new_command_cannot_confirm_or_replace_previous_action(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db")
    await memory.initialize()
    dispatcher = FakeDispatcher()
    engine = TaskEngine(IntentRouter(), dispatcher=dispatcher, memory=memory)
    first = await engine.handle("Open YouTube")

    cancelled = await engine.handle("Open Gmail")
    second = await engine.handle("Open Gmail")

    assert first.status == "confirmation_required"
    assert cancelled.status == "cancelled"
    assert cancelled.app == "YouTube"
    assert second.status == "confirmation_required"
    assert second.app == "Gmail"
    assert dispatcher.opened_apps == []


@pytest.mark.asyncio
async def test_confirmation_is_task_bound(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db")
    await memory.initialize()
    dispatcher = FakeDispatcher()
    engine = TaskEngine(IntentRouter(), dispatcher=dispatcher, memory=memory)
    pending = await engine.handle("Open YouTube")

    mismatch = await engine.confirm_task(uuid4(), "do")
    completed = await engine.confirm_task(pending.task_id, "do")

    assert mismatch.status == "unavailable"
    assert completed.status == "completed"
    assert dispatcher.opened_apps == ["YouTube"]


@pytest.mark.asyncio
async def test_confirmation_expires_without_dispatch(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db")
    await memory.initialize()
    dispatcher = FakeDispatcher()
    engine = TaskEngine(
        IntentRouter(),
        dispatcher=dispatcher,
        memory=memory,
        confirmation_timeout_seconds=0.01,
    )
    pending = await engine.handle("Open YouTube")
    await asyncio.sleep(0.02)

    result = await engine.confirm_task(pending.task_id, "do")

    assert result.status == "unavailable"
    assert "expired" in result.response
    assert dispatcher.opened_apps == []


@pytest.mark.asyncio
async def test_dispatch_failure_is_audited_and_not_reported_as_success(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db")
    await memory.initialize()
    dispatcher = FailingDispatcher()
    engine = TaskEngine(IntentRouter(), dispatcher=dispatcher, memory=memory)
    pending = await engine.handle("Open YouTube")

    result = await engine.confirm_task(pending.task_id, "do")

    assert result.status == "unavailable"
    assert "couldn't open" in result.response
    async with aiosqlite.connect(tmp_path / "piagent.db") as database:
        async with database.execute(
            "SELECT result FROM actions_audit ORDER BY id"
        ) as cursor:
            rows = await cursor.fetchall()
    assert rows == [("pending",), ("failed",)]


@pytest.mark.asyncio
async def test_reply_draft_uses_model_but_never_sends() -> None:
    llm = FakeLLM()
    engine = TaskEngine(IntentRouter(), llm=llm)

    result = await engine.handle("Write a polite reply saying I cannot come today.")

    assert result.status == "draft_ready"
    assert result.draft == "Sorry, I cannot come today."
    assert "I will not send it" in result.response
    assert "Never send it" in llm.prompts[0]


@pytest.mark.asyncio
async def test_invalid_local_reply_json_fails_closed() -> None:
    engine = TaskEngine(
        IntentRouter(),
        llm=FakeLLM(response=json.dumps({"action": "send_message"})),
    )

    result = await engine.handle("Write a polite reply saying I am late")

    assert result.status == "unavailable"
    assert result.draft is None
    assert "did not send" in result.response


@pytest.mark.asyncio
async def test_blank_local_reply_draft_fails_closed() -> None:
    engine = TaskEngine(IntentRouter(), llm=FakeLLM(response='{"draft":"  "}'))

    result = await engine.handle("Write a polite reply saying I am late")

    assert result.status == "unavailable"
    assert result.draft is None


@pytest.mark.asyncio
async def test_open_app_without_phone_does_not_claim_success() -> None:
    engine = TaskEngine(IntentRouter())

    result = await engine.handle("Open YouTube")

    assert result.status == "unavailable"
    assert "did not open" in result.response


@pytest.mark.asyncio
async def test_unknown_command_gets_helpful_fallback() -> None:
    result = await TaskEngine(IntentRouter()).handle("Do something impossible")

    assert result.status == "unknown"
    assert "couldn't identify" in result.response
