import os
from datetime import UTC, datetime

import aiosqlite
import pytest

from app.core.memory import MemoryDisabledError, MemoryStore


@pytest.mark.asyncio
async def test_fact_crud_and_database_permissions(tmp_path) -> None:
    database_path = tmp_path / "data" / "piagent.db"
    memory = MemoryStore(database_path)
    await memory.initialize()
    await memory.remember_fact("favorite color", "blue")

    assert await memory.get_fact("favorite color") == "blue"
    await memory.remember_fact("favorite color", "green")
    assert await memory.get_fact("favorite color") == "green"
    assert await memory.get_fact("missing") is None

    if os.name == "posix" and database_path.stat().st_mode & 0o777 != 0o600:
        pytest.fail("SQLite memory file should have owner-only permissions.")


@pytest.mark.asyncio
async def test_sensitive_history_is_disabled_by_default(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db")
    await memory.initialize()

    assert await memory.add_conversation_turn("user", "private request") is False
    assert (
        await memory.store_notification(
            "id-1",
            "WhatsApp",
            "com.whatsapp",
            "Sender",
            "private message",
            datetime.now(UTC),
        )
        is False
    )
    with pytest.raises(MemoryDisabledError):
        await memory.recent_conversation()

    async with aiosqlite.connect(tmp_path / "piagent.db") as database:
        async with database.execute("SELECT COUNT(*) FROM notifications") as cursor:
            row = await cursor.fetchone()
    assert row is not None and row[0] == 0


@pytest.mark.asyncio
async def test_opt_in_conversation_context_is_capped_at_six_turns(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db", store_conversations=True)
    await memory.initialize()
    for index in range(8):
        await memory.add_conversation_turn("user", f"turn {index}")

    context = await memory.recent_conversation()

    assert len(context) == 6
    assert context[0] == ("user", "turn 2")
    assert context[-1] == ("user", "turn 7")
    with pytest.raises(ValueError, match="between 1 and 6"):
        await memory.recent_conversation(limit=7)


@pytest.mark.asyncio
async def test_reminders_are_local_and_can_be_completed(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db")
    await memory.initialize()
    reminder = await memory.create_reminder(
        "Call the pharmacy",
        datetime(2026, 10, 27, 9, 0, tzinfo=UTC),
    )

    assert (await memory.pending_reminders()) == [reminder]
    assert await memory.mark_reminder_done(reminder.id) is True
    assert await memory.pending_reminders() == []
    assert await memory.mark_reminder_done(reminder.id) is False


@pytest.mark.asyncio
async def test_reminder_rejects_naive_due_time(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db")
    await memory.initialize()

    with pytest.raises(ValueError, match="timezone"):
        await memory.create_reminder("Call the pharmacy", datetime(2026, 10, 27, 9, 0))


@pytest.mark.asyncio
async def test_action_audit_stores_metadata_without_body_fields(tmp_path) -> None:
    memory = MemoryStore(tmp_path / "piagent.db")
    await memory.initialize()
    await memory.record_action("task-1", "open_app", "low", "allowed", "succeeded")

    async with aiosqlite.connect(tmp_path / "piagent.db") as database:
        async with database.execute(
            "SELECT action, risk, decision, result FROM actions_audit"
        ) as cursor:
            row = await cursor.fetchone()

    assert row == ("open_app", "low", "allowed", "succeeded")
