# ContextSchema Research Summary

This public repository contains the Python package, tests, examples, CI, and
contributor docs. The deeper working ledgers are kept out of this repo so the
package front door stays practical.

## Current Thesis

ContextSchema is a small post-retrieval validation layer for AI agents. It
checks whether retrieved context is fresh, provenance-backed, event-valid,
source-appropriate, and complete enough for a specific decision before an agent
acts.

```text
retriever / memory / tool output -> ContextSchema -> proceed | soft_flag | retry_recommended | hard_gate
```

## Current Boundary

ContextSchema is not trying to replace:

- vector databases
- retrievers
- agent frameworks
- memory stores
- data catalogs
- observability platforms
- policy engines
- LLM classifiers or extractors

Those systems can feed or consume ContextSchema. The package focuses on the
portable validity contract between retrieved context and action.

## Why The Public Package Is Small

The first useful artifact is the core Python library because it can be tested
without external services:

- declare expected context fields
- score retrieved items against metadata, TTLs, events, and source reliability
- return field and schema confidence
- recommend proceed, soft flag, retry, or hard gate
- write replayable evidence without storing raw retrieved text by default

Adapters, telemetry exports, policy-engine mappings, and benchmark harnesses are
intentionally deferred until the core API has settled.
