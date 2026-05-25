# Changelog

All notable project changes should be recorded here.

This project is pre-0.1. Until the first tagged release, entries describe the
state of the public GitHub repository rather than a PyPI package.

## Unreleased

### Added

- Repository hygiene docs: contributing guide, code of conduct, changelog, and
  GitHub issue templates.
- Explicit release-path decision: public GitHub first; PyPI deferred until a
  tagged `0.1.0` release candidate.
- README sections for intended users, when to use ContextSchema, compatibility
  with adjacent tools, and visual flow diagrams.
- `WHY_CONTEXTSCHEMA.md`, a scenario-driven guide for PMs and engineers
  evaluating context sufficiency as a design-time contract.
- Expanded the guide to cover provenance, relevance, timeliness, retrieval
  metadata requirements, and why prompts alone are a weak enforcement layer for
  consequential decisions.

## 0.0.1 - Pre-Release

### Added

- Minimal dependency-free Python core under `src/contextschema/`.
- Declarative `ContextSchema` and `ContextField` API.
- `RetrievedItem`, `EventRecord`, `ActionPolicy`, `ValidationResult`,
  `FieldConfidence`, `SchemaConfidence`, and `DecisionEvidenceLog`.
- Deterministic scoring for required fields, optional fields, TTL age,
  malformed or missing metadata, event invalidation, source reliability, and
  ambiguous candidates.
- Evidence JSONL support with raw retrieved text excluded by default.
- Enterprise examples for customer service, coding agents, sales, procurement,
  finance, HR, and security access review.
- README with install instructions, quickstart, expected output, API summary,
  maturity warning, example links, and research links.
- MIT license.
- Python 3.11, 3.12, and 3.13 CI configuration.
- Public research summary.

### Notes

- This is not published to PyPI.
- API stability is not guaranteed yet.
- External integrations remain deferred.
