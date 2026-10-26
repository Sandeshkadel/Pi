# PiAgent Copilot Instructions

Follow the root [AGENTS.md](../AGENTS.md) for project constraints and definition
of done.

## Working approach

- Implement one roadmap phase at a time. Verify its acceptance criteria before
  moving to the next phase.
- Preserve existing user data and inspect the worktree before destructive
  changes. Never wipe unknown Pi storage; inventory and back it up first.
- Keep tests hardware-independent with mocked audio, BLE, phone, and local-model
  adapters. Label real-device checks separately.
- Treat all model output and device/network input as untrusted. Validate API
  and WebSocket payloads with Pydantic.
- Require explicit, task-specific user confirmation for risky actions.
  Confirmation never permits lock-screen bypass, credential/OTP entry, or
  banking/payment automation.
- Never put credentials or private notification content in code, logs,
  examples, or commits. Do not reuse a credential that has been exposed.
- Keep private content on the local Pi/phone network; do not make a cloud model
  or API key a requirement.

## Validation

Run the smallest relevant checks, and before completing a phase run:

```bash
ruff check .
pytest -q
```

For Android changes also run:

```bash
gradle testDebugUnitTest assembleDebug
```

Document checks that need a real Pi or Android device and do not report them as
passing until actually run.
