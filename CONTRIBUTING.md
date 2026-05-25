# Contributing To ContextSchema

ContextSchema is experimental and pre-0.1. Contributions are welcome, but the
bar for changes is clarity: explain the decision being validated, the evidence
shape, and the failure mode the change improves.

## Good First Contribution Areas

- Add or improve enterprise examples.
- Add edge-case tests for scoring, timestamps, events, source reliability, and
  evidence privacy.
- Improve docs where the current API or research boundary is unclear.
- Add benchmark scripts that compare ContextSchema against a clear baseline.

## Current Scope

In scope:

- Core Python validation behavior.
- Dependency-free examples.
- Tests for context matching, confidence scoring, event invalidation, and
  evidence records.
- Documentation that helps users understand what ContextSchema is and is not.

Out of scope for now:

- Hosted services.
- Vector database or retriever implementations.
- Full observability dashboards.
- LangChain, LlamaIndex, Redis, Zep, dbt, Langfuse, or Braintrust adapters
  until the core API has settled.

## Development Setup

```bash
git clone https://github.com/Novice-ninja/contextschema-py.git
cd contextschema-py
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests examples
```

## Pull Request Expectations

- Keep changes tightly scoped.
- Add tests for behavior changes.
- Update README, examples docs, or research docs when public behavior or
  positioning changes.
- Avoid adding dependencies unless the benefit is clear and documented.
- Do not store raw retrieved text in evidence by default.

## API Stability

The current package is `0.0.1`. Public names may still change, but the intended
public boundary is documented in the README:

- `ContextSchemaError`
- `ContextSchema.schema_definition()`
- `ValidationResult.to_policy_input()`

Any change to those names or shapes should update tests, README, and the
changelog.

## Release Policy

The current release path is public GitHub first. PyPI publishing is deferred
until a tagged `0.1.0` release candidate has a stable enough API, passing CI,
and a clearer changelog.
