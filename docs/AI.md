# Local intent routing and AI

## Current implementation

- Known stop phrases and a small allowlist of app-launch phrases are routed
  deterministically without an LLM.
- Ambiguous requests may be classified only into `open_app`, `draft_reply`, or
  `unknown`; app names must still match the local allowlist.
- Reply drafting produces a draft only. It never sends a message.
- Every external app action is first read back and requires a task-bound spoken
  approval (`do`, `yes`, `confirm`, or `go ahead`) that expires after 60
  seconds. A changed or mismatched task cannot use that approval.
- `TaskEngine` does not claim phone actions succeeded unless an injected
  dispatcher performs them after approval. Open-app dispatch requires an
  initialized audit store and records pending/result metadata without the
  command body.

## Ollama boundary

`OllamaClient` accepts only loopback HTTP URLs and requests JSON output with a
small generation limit. Remote/cloud Ollama hosts are rejected so private
commands are not sent off-device. Model output is untrusted and validated
before use. The default FastAPI app does not configure an Ollama client or
phone dispatcher yet.

## Resource and license gate

Install a model only after checking that it fits the Pi's memory/latency
budget. The default model name is `qwen2.5:1.5b`; model artifacts remain outside
Git. Review model license and distribution terms before bundling or sharing
weights.
