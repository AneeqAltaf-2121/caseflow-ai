# 008 — Pluggable LLM generation provider

## Status
Accepted

## Context
Citation-grounded RAG (Phase 19) and LLM-as-a-judge evaluation (Phase 28)
both need to call an LLM to generate text, but neither should hard-depend
on a specific vendor SDK, and the test suite needs to exercise the full
RAG/eval pipeline without a real API key or network access.

## Decision
`GenerationProvider` (app/integrations/generation.py) is a small protocol
— `generate(system_prompt, user_prompt, temperature, max_tokens) ->
GenerationResult` (text + model + token counts) — selected by
`settings.llm_provider`, same pattern as embeddings/storage/auth:

- **mock** (default): `MockGenerationProvider` returns a caller-supplied
  `canned_response` verbatim, or an echo of the prompt otherwise. Tests
  set `canned_response` to control exactly what "the model said" —
  including deliberately malformed output, to test a caller's fallback
  behavior (see LLMReranker's tests).
- **openai**: real Chat Completions API call (`gpt-4o-mini`). Requires
  `OPENAI_API_KEY`.
- **anthropic**: real Messages API call (`claude-3-5-haiku-20241022`).
  Requires `ANTHROPIC_API_KEY`.

Neither real provider is exercised in CI — only `MockGenerationProvider`
runs in the test suite, by design.

## Rationale
- Matches ADR 007's reasoning exactly: a dependency-free default keeps
  the app runnable and the RAG/eval pipeline fully testable with zero
  provider credentials, while the real integrations exist and are a
  one-line config change away (`LLM_PROVIDER=openai` or `=anthropic`) once
  keys are available.
- A controllable canned response (rather than only a fixed echo) is what
  makes callers like `LLMReranker` genuinely testable: the tests exercise
  both "the model returned a valid ranking" and "the model returned
  garbage" without needing a real, unpredictable LLM to produce garbage
  on demand.

## Consequences
- Adding a third real vendor (e.g. a self-hosted model via an
  OpenAI-compatible endpoint) is a new `GenerationProvider` implementation
  registered in `get_generation_provider`, not a rewrite of any caller.
- Every caller that degrades gracefully on unparseable model output
  (LLMReranker today; the RAG service and judge graders later) can be
  tested for that behavior directly via `canned_response`, without
  needing to reproduce a real model's failure modes.
