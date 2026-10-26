# Local memory

## Defaults

- SQLite data is kept under the configured local data directory, which is
  ignored by Git.
- Notification history is off by default; `store_notification` makes the
  disabled state explicit and writes nothing.
- Conversation history is off by default. When enabled, old turns are pruned
  using the configured retention period and only the latest six turns can be
  returned for local model context.
- Facts and reminders are local. The database file is set to owner-only mode
  on POSIX systems.
- Action audit rows contain task/action/risk/decision/result metadata only;
  callers must not put message bodies, tokens, or credentials in those fields.

## Current limitations

The `MemoryStore` is implemented and tested, but the default application does
not initialize it or expose data-management controls. Audit-retention
pruning, encryption at rest, and a user-facing wipe/export flow must be
implemented before production deployment. Do not delete or reset unknown Pi
storage as a substitute for an explicit memory-management feature.
