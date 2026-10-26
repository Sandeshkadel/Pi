"""Asynchronous, local-only SQLite memory with opt-in sensitive history."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field


class MemoryDisabledError(RuntimeError):
    """Raised when an operation requires a storage feature that is disabled."""


class Reminder(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    text: str = Field(min_length=1, max_length=1_000)
    due_at: datetime | None = None
    done: bool = False


class MemoryStore:
    """Own a local SQLite database; no notification or conversation body is stored by default."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        store_conversations: bool = False,
        store_notification_history: bool = False,
        conversation_retention_days: int = 30,
    ) -> None:
        if conversation_retention_days <= 0:
            raise ValueError("Conversation retention must be positive.")
        self._database_path = Path(database_path)
        self._store_conversations = store_conversations
        self._store_notification_history = store_notification_history
        self._conversation_retention_days = conversation_retention_days
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Create the local schema and set restrictive file permissions."""
        async with self._initialize_lock:
            if self._initialized:
                return

            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self._database_path) as database:
                await database.execute("PRAGMA foreign_keys = ON")
                await database.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS facts (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS reminders (
                        id TEXT PRIMARY KEY,
                        text TEXT NOT NULL,
                        due_at TEXT,
                        done INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INTEGER PRIMARY KEY,
                        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                        text TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS notifications (
                        id TEXT PRIMARY KEY,
                        app TEXT NOT NULL,
                        package TEXT NOT NULL,
                        sender TEXT NOT NULL,
                        text TEXT NOT NULL,
                        received_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS actions_audit (
                        id INTEGER PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        risk TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        result TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    """
                )

            if os.name == "posix":
                os.chmod(self._database_path, 0o600)
            self._initialized = True

    async def remember_fact(self, key: str, value: str) -> None:
        """Insert or update a user-approved fact in local memory."""
        self._require_initialized()
        normalized_key = key.strip()
        if not normalized_key or not value.strip():
            raise ValueError("Fact key and value must not be empty.")
        now = _utc_now()
        async with aiosqlite.connect(self._database_path) as database:
            await database.execute(
                """
                INSERT INTO facts (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE
                SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (normalized_key, value.strip(), now),
            )
            await database.commit()

    async def get_fact(self, key: str) -> str | None:
        """Read a stored fact by its exact key."""
        self._require_initialized()
        async with aiosqlite.connect(self._database_path) as database:
            async with database.execute(
                "SELECT value FROM facts WHERE key = ?",
                (key.strip(),),
            ) as cursor:
                row = await cursor.fetchone()
        return None if row is None else str(row[0])

    async def create_reminder(self, text: str, due_at: datetime | None = None) -> Reminder:
        """Store a local reminder after validating its content and optional timezone."""
        self._require_initialized()
        reminder = Reminder(
            id=uuid4(),
            text=text.strip(),
            due_at=due_at,
        )
        if reminder.due_at is not None and (
            reminder.due_at.tzinfo is None or reminder.due_at.utcoffset() is None
        ):
            raise ValueError("Reminder due time must include a timezone.")

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute(
                """
                INSERT INTO reminders (id, text, due_at, done, created_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (
                    str(reminder.id),
                    reminder.text,
                    reminder.due_at.isoformat() if reminder.due_at is not None else None,
                    _utc_now(),
                ),
            )
            await database.commit()
        return reminder

    async def pending_reminders(self) -> list[Reminder]:
        """Return pending reminders in due-time order, with unscheduled items last."""
        self._require_initialized()
        async with aiosqlite.connect(self._database_path) as database:
            async with database.execute(
                """
                SELECT id, text, due_at, done FROM reminders
                WHERE done = 0
                ORDER BY due_at IS NULL, due_at, id
                """
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            Reminder(
                id=UUID(str(row[0])),
                text=str(row[1]),
                due_at=datetime.fromisoformat(row[2]) if row[2] is not None else None,
                done=bool(row[3]),
            )
            for row in rows
        ]

    async def mark_reminder_done(self, reminder_id: UUID) -> bool:
        """Mark a pending reminder complete; return false if it does not exist."""
        self._require_initialized()
        async with aiosqlite.connect(self._database_path) as database:
            cursor = await database.execute(
                "UPDATE reminders SET done = 1 WHERE id = ? AND done = 0",
                (str(reminder_id),),
            )
            await database.commit()
        return cursor.rowcount == 1

    async def add_conversation_turn(self, role: str, text: str) -> bool:
        """Store a conversation turn only when the user has enabled history."""
        self._require_initialized()
        if not self._store_conversations:
            return False
        if role not in {"user", "assistant"} or not text.strip():
            raise ValueError("Conversation role or text is invalid.")

        now = _utc_now()
        cutoff = (datetime.now(UTC) - timedelta(days=self._conversation_retention_days)).isoformat()
        async with aiosqlite.connect(self._database_path) as database:
            await database.execute(
                "INSERT INTO conversations (role, text, created_at) VALUES (?, ?, ?)",
                (role, text, now),
            )
            await database.execute("DELETE FROM conversations WHERE created_at < ?", (cutoff,))
            await database.commit()
        return True

    async def recent_conversation(self, limit: int = 6) -> list[tuple[str, str]]:
        """Return recent turns in chronological order, capped to the small LLM context."""
        self._require_initialized()
        if not self._store_conversations:
            raise MemoryDisabledError("Conversation history is disabled.")
        if not 1 <= limit <= 6:
            raise ValueError("Conversation context limit must be between 1 and 6.")

        async with aiosqlite.connect(self._database_path) as database:
            async with database.execute(
                """
                SELECT role, text FROM conversations
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [(str(row[0]), str(row[1])) for row in reversed(rows)]

    async def store_notification(
        self,
        notification_id: str,
        app: str,
        package: str,
        sender: str,
        text: str,
        received_at: datetime,
    ) -> bool:
        """Persist notification content only when history was explicitly enabled."""
        self._require_initialized()
        if not self._store_notification_history:
            return False
        if received_at.tzinfo is None or received_at.utcoffset() is None:
            raise ValueError("Notification timestamp must include a timezone.")
        async with aiosqlite.connect(self._database_path) as database:
            await database.execute(
                """
                INSERT INTO notifications (id, app, package, sender, text, received_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (notification_id, app, package, sender, text, received_at.isoformat()),
            )
            await database.commit()
        return True

    async def record_action(
        self,
        task_id: str,
        action: str,
        risk: str,
        decision: str,
        result: str,
    ) -> None:
        """Append action metadata only; callers must not pass message bodies or secrets."""
        self._require_initialized()
        if any(not value.strip() for value in (task_id, action, risk, decision, result)):
            raise ValueError("Audit fields must not be empty.")
        async with aiosqlite.connect(self._database_path) as database:
            await database.execute(
                """
                INSERT INTO actions_audit
                    (task_id, action, risk, decision, result, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, action, risk, decision, result, _utc_now()),
            )
            await database.commit()

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("MemoryStore.initialize() must be called before use.")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
