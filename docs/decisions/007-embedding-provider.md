# 007 — Pluggable embedding provider, hashing-trick local default

## Status
Accepted

## Context
The embedding pipeline (Phase 13) and query embedding (Phase 14) both need
to turn text into vectors, but the app shouldn't hard-depend on a specific
vendor SDK, an API key, or a multi-gigabyte model download just to run its
test suite or a local demo.

## Decision
`EmbeddingProvider` (app/integrations/embeddings.py) is a small protocol —
`embed(texts) -> list[vector]` plus a `dimensions` attribute. Three
implementations, selected by `settings.embedding_provider`:

- **mock** (default): a deterministic hash-of-text vector. Same input
  always produces the same output, nothing more — good for exact-equality
  assertions, not for testing retrieval quality.
- **local**: the hashing trick (feature-hash each word into one of N
  buckets, weight by term frequency, L2-normalize). A genuinely real
  lexical embedding — texts sharing vocabulary score more similar than
  unrelated ones — with no model download, no network call, and no
  ML-framework dependency (no torch/sentence-transformers).
- **openai**: calls OpenAI's real embeddings API. Requires
  `OPENAI_API_KEY`; not exercised in CI.

## Rationale
- A deep sentence-transformer model would give materially better
  semantic embeddings than the hashing trick, but pulls in torch and a
  model download — heavy for local dev/CI and unnecessary for this
  project's grading/demo purposes. The hashing trick is a well-established
  technique (Vowpal Wabbit, scikit-learn's HashingVectorizer) that's
  genuinely useful for keyword/terminology-heavy documents (contracts,
  case files) even without deep semantics.
- Keeping `dimensions` fixed (`EMBEDDING_DIMENSIONS = 384`, see
  app/models/chunk.py) across all three providers means the pgvector
  column width never has to change just from switching providers in
  config — only from actually changing that constant (which does need a
  migration).
- Matches the same pattern as app/integrations/storage.py and
  app/auth/providers.py: one settings field selects an implementation
  behind a narrow interface, with a dependency-free option as the default
  so nothing in the app requires external credentials just to boot.

## Consequences
- Swapping in a real deep-semantic local model later
  (sentence-transformers, a local ONNX model, etc.) is a new
  `EmbeddingProvider` implementation, not a rewrite of anything that calls
  `embed()`.
- Retrieval quality with `mock` or `local` will be materially worse than
  with a real semantic model — expected and acceptable for this project's
  scope; the evaluation framework (Phase 15+) is what would surface that
  gap quantitatively if it mattered for a real deployment.
