"""Core ContextSchema validation primitives.

This module intentionally avoids external dependencies. It implements the MVP
from the planning docs: metadata-first field matching, deterministic scoring,
action recommendation, and local replayable evidence records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from collections.abc import Iterator, Mapping
from typing import Any, ClassVar, Literal


Action = Literal["proceed", "soft_flag", "retry_recommended", "hard_gate"]
EventPolicy = Literal["optional", "required"]
FieldStatus = Literal[
    "valid",
    "stale",
    "event_invalidated",
    "missing",
    "missing_optional",
    "metadata_insufficient",
    "weak_source",
    "fallback_used",
]
Severity = Literal["info", "warning", "error"]

TIMESTAMP_KEYS = ("valid_at", "last_modified_at", "loaded_at", "retrieved_at")


class ContextSchemaError(ValueError):
    """Raised when a schema, field, item, or event is invalid."""


@dataclass(frozen=True)
class Reason:
    """Machine-readable explanation for a confidence penalty or policy signal."""

    code: str
    severity: Severity
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation of the reason."""

        result = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.details:
            result["details"] = _jsonable(self.details)
        return result


@dataclass
class ContextField:
    """Declarative contract for one piece of context required by a decision.

    A field can constrain expected sources, freshness, requiredness,
    invalidation events, minimum source reliability, and privacy tags. Define
    fields as class attributes on a `ContextSchema` subclass.
    """

    source: str | list[str] | tuple[str, ...] | None = None
    ttl: timedelta | None = None
    criticality: float = 1.0
    required: bool = True
    invalidates_on: list[str] | tuple[str, ...] = field(default_factory=list)
    event_policy: EventPolicy = "optional"
    min_source_reliability: float | None = None
    allow_fallback_extractor: bool = False
    privacy_tags: list[str] | tuple[str, ...] = field(default_factory=list)
    name: str | None = field(default=None, init=False, compare=False)

    def __post_init__(self) -> None:
        if not 0.0 <= self.criticality <= 1.0:
            raise ContextSchemaError("ContextField.criticality must be between 0.0 and 1.0")
        if self.source is not None and not isinstance(self.source, (str, list, tuple)):
            raise ContextSchemaError("ContextField.source must be a string, list, tuple, or None")
        for source in self.sources:
            if not isinstance(source, str) or not source:
                raise ContextSchemaError("ContextField.source values must be non-empty strings")
        if self.ttl is not None and self.ttl <= timedelta(0):
            raise ContextSchemaError("ContextField.ttl must be positive when provided")
        for event_type in self.invalidates_on:
            if not isinstance(event_type, str) or not event_type:
                raise ContextSchemaError("ContextField.invalidates_on values must be non-empty strings")
        for tag in self.privacy_tags:
            if not isinstance(tag, str) or not tag:
                raise ContextSchemaError("ContextField.privacy_tags values must be non-empty strings")
        if self.event_policy not in ("optional", "required"):
            raise ContextSchemaError("ContextField.event_policy must be 'optional' or 'required'")
        if self.event_policy == "required" and not self.invalidates_on:
            raise ContextSchemaError("event_policy='required' requires invalidates_on")
        if self.min_source_reliability is not None and not 0.0 <= self.min_source_reliability <= 1.0:
            raise ContextSchemaError("min_source_reliability must be between 0.0 and 1.0")

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    @property
    def sources(self) -> tuple[str, ...]:
        """Return configured sources as a normalized tuple."""

        if self.source is None:
            return ()
        if isinstance(self.source, str):
            return (self.source,)
        return tuple(self.source)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible field definition."""

        return {
            "name": self.name,
            "source": list(self.sources),
            "ttl_seconds": self.ttl.total_seconds() if self.ttl else None,
            "criticality": self.criticality,
            "required": self.required,
            "invalidates_on": list(self.invalidates_on),
            "event_policy": self.event_policy,
            "min_source_reliability": self.min_source_reliability,
            "allow_fallback_extractor": self.allow_fallback_extractor,
            "privacy_tags": list(self.privacy_tags),
        }


@dataclass(frozen=True)
class RetrievedItem:
    """Retrieved context candidate supplied to a schema validation run.

    `metadata` should carry field hints, source, provenance/source refs,
    timestamps, and optional source reliability. `text` is never stored in
    evidence records unless `store_raw_text=True`.
    """

    id: str
    text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ContextSchemaError("RetrievedItem.id is required")
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
        if not isinstance(self.metadata, dict):
            raise ContextSchemaError("RetrievedItem.metadata must be a dict")


@dataclass(frozen=True)
class EventRecord:
    """Business or system event that can invalidate previously retrieved context."""

    event_id: str
    event_type: str
    occurred_at: datetime
    affected_fields: list[str] | tuple[str, ...] = field(default_factory=list)
    affected_sources: list[str] | tuple[str, ...] = field(default_factory=list)
    source_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ContextSchemaError("EventRecord.event_id is required")
        if not self.event_type:
            raise ContextSchemaError("EventRecord.event_type is required")
        object.__setattr__(self, "occurred_at", _ensure_aware(self.occurred_at))
        object.__setattr__(self, "affected_fields", _as_string_list(self.affected_fields))
        object.__setattr__(self, "affected_sources", _as_string_list(self.affected_sources))
        object.__setattr__(self, "metadata", _as_dict(self.metadata))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventRecord":
        """Build an event record from a JSON-compatible mapping."""

        return cls(
            event_id=str(data["event_id"]),
            event_type=str(data["event_type"]),
            occurred_at=parse_datetime(data["occurred_at"]),
            affected_fields=_as_string_list(data.get("affected_fields", [])),
            affected_sources=_as_string_list(data.get("affected_sources", [])),
            source_ref=data.get("source_ref"),
            metadata=_as_dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible event record."""

        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "affected_fields": list(self.affected_fields),
            "affected_sources": list(self.affected_sources),
            "source_ref": self.source_ref,
            "metadata": _jsonable(self.metadata),
        }


@dataclass(frozen=True)
class FieldConfidence:
    """Per-field validation result with score, status, reasons, and evidence refs."""

    field_name: str
    score: float
    components: dict[str, float]
    status: FieldStatus
    reasons: list[Reason]
    matched_item_ids: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    timestamps: dict[str, str] = field(default_factory=dict)
    invalidating_events: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible field-confidence payload."""

        return {
            "field_name": self.field_name,
            "score": self.score,
            "components": {key: round(value, 6) for key, value in self.components.items()},
            "status": self.status,
            "reasons": [reason.to_dict() for reason in self.reasons],
            "matched_item_ids": list(self.matched_item_ids),
            "source_refs": list(self.source_refs),
            "timestamps": dict(self.timestamps),
            "invalidating_events": list(self.invalidating_events),
        }


@dataclass(frozen=True)
class SchemaConfidence:
    """Whole-schema confidence aggregated from required and optional fields."""

    score: float
    aggregation_method: str
    weakest_fields: list[str]
    required_missing: list[str]
    event_invalidated: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible schema-confidence payload."""

        return {
            "score": self.score,
            "aggregation_method": self.aggregation_method,
            "weakest_fields": list(self.weakest_fields),
            "required_missing": list(self.required_missing),
            "event_invalidated": list(self.event_invalidated),
        }


@dataclass(frozen=True)
class ActionPolicy:
    """Map schema and field confidence into a recommended orchestration action."""

    proceed_at_or_above: float = 0.75
    retry_below: float = 0.75
    soft_flag_below: float = 0.75
    hard_gate_below: float | None = None
    hard_gate_on_event_invalidated_required_field: bool = False
    hard_gate_on_missing_required: bool = False

    def __post_init__(self) -> None:
        for attr in ("proceed_at_or_above", "retry_below", "soft_flag_below"):
            value = getattr(self, attr)
            if not 0.0 <= value <= 1.0:
                raise ContextSchemaError(f"ActionPolicy.{attr} must be between 0.0 and 1.0")
        if self.hard_gate_below is not None and not 0.0 <= self.hard_gate_below <= 1.0:
            raise ContextSchemaError("ActionPolicy.hard_gate_below must be between 0.0 and 1.0")

    def choose(
        self,
        schema_confidence: SchemaConfidence,
        field_confidences: list[FieldConfidence],
    ) -> tuple[Action, list[str], list[str]]:
        """Choose an action, warnings, and retry recommendations for a result."""

        warnings: list[str] = []
        retry_recommendations: list[str] = []

        if self.hard_gate_on_missing_required and schema_confidence.required_missing:
            return (
                "hard_gate",
                [f"required_field_missing:{field_name}" for field_name in schema_confidence.required_missing],
                retry_recommendations,
            )

        if self.hard_gate_on_event_invalidated_required_field and schema_confidence.event_invalidated:
            return (
                "hard_gate",
                [f"required_field_event_invalidated:{field_name}" for field_name in schema_confidence.event_invalidated],
                retry_recommendations,
            )

        if self.hard_gate_below is not None and schema_confidence.score < self.hard_gate_below:
            return (
                "hard_gate",
                [f"schema_score_below_hard_gate:{schema_confidence.score}"],
                retry_recommendations,
            )

        weak_retry_fields = [
            field.field_name
            for field in field_confidences
            if field.status in ("missing", "stale", "metadata_insufficient", "event_invalidated", "weak_source")
            and field.score < self.retry_below
        ]
        if schema_confidence.score < self.retry_below and weak_retry_fields:
            retry_recommendations = [f"refresh_or_retry_field:{name}" for name in weak_retry_fields]
            return (
                "retry_recommended",
                [f"schema_score_below_retry:{schema_confidence.score}"],
                retry_recommendations,
            )

        if schema_confidence.score < self.soft_flag_below or schema_confidence.score < self.proceed_at_or_above:
            warnings.append(f"schema_score_below_soft_flag:{schema_confidence.score}")
            return "soft_flag", warnings, retry_recommendations

        return "proceed", warnings, retry_recommendations

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible action-policy definition."""

        return {
            "proceed_at_or_above": self.proceed_at_or_above,
            "retry_below": self.retry_below,
            "soft_flag_below": self.soft_flag_below,
            "hard_gate_below": self.hard_gate_below,
            "hard_gate_on_event_invalidated_required_field": self.hard_gate_on_event_invalidated_required_field,
            "hard_gate_on_missing_required": self.hard_gate_on_missing_required,
        }


@dataclass(frozen=True)
class ValidationResult:
    """Top-level output from `ContextSchema.validate_retrieved()`."""

    decision_id: str
    schema_name: str
    schema_version: str
    evaluated_at: datetime
    context: dict[str, Any]
    field_confidences: list[FieldConfidence]
    schema_confidence: SchemaConfidence
    action: Action
    warnings: list[str]
    retry_recommendations: list[str]
    evidence_record: dict[str, Any]

    def field(self, field_name: str) -> FieldConfidence:
        """Return the confidence object for one field name."""

        for confidence in self.field_confidences:
            if confidence.field_name == field_name:
                return confidence
        raise KeyError(field_name)

    def weak_fields(self, threshold: float = 0.75) -> list[FieldConfidence]:
        """Return fields whose score is below `threshold`."""

        return [
            confidence
            for confidence in self.field_confidences
            if confidence.score < threshold
        ]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible result payload including evidence."""

        return {
            "decision_id": self.decision_id,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "evaluated_at": self.evaluated_at.isoformat(),
            "context": _jsonable(self.context),
            "field_confidences": [field.to_dict() for field in self.field_confidences],
            "schema_confidence": self.schema_confidence.to_dict(),
            "action": self.action,
            "warnings": list(self.warnings),
            "retry_recommendations": list(self.retry_recommendations),
            "evidence_record": _jsonable(self.evidence_record),
        }

    def to_json(self, **kwargs: Any) -> str:
        """Serialize the result payload to JSON."""

        return json.dumps(self.to_dict(), **kwargs)

    def to_policy_input(self) -> dict[str, Any]:
        """Return the stable pre-policy handoff shape for this result.

        This helper is part of the intended public API for pre-0.1 users.
        Future versions may add keys, but the current top-level keys should be
        treated as compatibility-sensitive.
        """

        fields = []
        evidence_fields = self.evidence_record.get("fields", {})
        for confidence in self.field_confidences:
            evidence = evidence_fields.get(confidence.field_name, {})
            fields.append(
                {
                    "field": confidence.field_name,
                    "required": evidence.get("required"),
                    "criticality": evidence.get("criticality"),
                    "confidence": confidence.score,
                    "status": confidence.status,
                    "reasons": [reason.code for reason in confidence.reasons],
                    "matched_item_ids": list(confidence.matched_item_ids),
                    "source_refs": list(confidence.source_refs),
                    "invalidating_events": list(confidence.invalidating_events),
                }
            )
        return {
            "decision_id": self.decision_id,
            "schema": {
                "name": self.schema_name,
                "version": self.schema_version,
            },
            "schema_confidence": self.schema_confidence.score,
            "action": self.action,
            "fields": fields,
        }


class DecisionEvidenceLog:
    """Append-only JSONL writer for validation evidence records."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def write(self, result: ValidationResult) -> None:
        """Append one validation result's evidence record to the JSONL log."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result.evidence_record, sort_keys=True) + "\n")


class ContextSchema:
    """Base class for declarative decision-context schemas.

    Subclasses define `ContextField` attributes and call `validate_retrieved()`
    with retrieved items and optional invalidation events.
    """

    schema_name: ClassVar[str | None] = None
    schema_version: ClassVar[str] = "1"
    action_policy: ClassVar[ActionPolicy] = ActionPolicy()

    @classmethod
    def fields(cls) -> dict[str, ContextField]:
        """Return declared context fields keyed by field name."""

        fields_by_name: dict[str, ContextField] = {}
        for base in reversed(cls.__mro__):
            for name, value in vars(base).items():
                if isinstance(value, ContextField):
                    value.name = value.name or name
                    fields_by_name[name] = value
        return fields_by_name

    @classmethod
    def schema_definition(cls) -> dict[str, Any]:
        """Return the stable JSON-compatible schema definition.

        This helper is part of the intended public API for pre-0.1 users.
        Future versions may add keys, but current names and field-policy
        structure should be considered compatibility-sensitive.
        """

        return {
            "schema_name": cls._schema_name(),
            "schema_version": cls.schema_version,
            "fields": {
                name: field.to_dict()
                for name, field in cls.fields().items()
            },
            "action_policy": cls.action_policy.to_dict(),
        }

    @classmethod
    def validate_retrieved(
        cls,
        items: list[RetrievedItem],
        *,
        decision_id: str,
        events: list[EventRecord] | None = None,
        evaluated_at: datetime | None = None,
        context: dict[str, Any] | None = None,
        source_reliability: dict[str, float] | None = None,
        evidence_log: DecisionEvidenceLog | str | Path | None = None,
        store_raw_text: bool = False,
    ) -> ValidationResult:
        """Validate retrieved context for one decision.

        The method scores every declared field, aggregates schema confidence,
        chooses an action through `action_policy`, and optionally appends a
        replayable evidence record.
        """

        if not decision_id:
            raise ContextSchemaError("decision_id is required")

        evaluated = _ensure_aware(evaluated_at or datetime.now(UTC))
        schema_fields = cls.fields()
        if not schema_fields:
            raise ContextSchemaError("ContextSchema subclasses must define at least one ContextField")
        event_records = events or []
        field_confidences = [
            _score_field(
                field_name=name,
                field=field,
                items=items,
                events=event_records,
                evaluated_at=evaluated,
                source_reliability=source_reliability or {},
            )
            for name, field in schema_fields.items()
        ]
        schema_confidence = _aggregate_schema_confidence(schema_fields, field_confidences)
        action, warnings, retry_recommendations = cls.action_policy.choose(
            schema_confidence,
            field_confidences,
        )
        evidence_record = _build_evidence_record(
            decision_id=decision_id,
            schema_name=cls._schema_name(),
            schema_version=cls.schema_version,
            evaluated_at=evaluated,
            context=context or {},
            field_confidences=field_confidences,
            schema_confidence=schema_confidence,
            action=action,
            warnings=warnings,
            retry_recommendations=retry_recommendations,
            action_policy=cls.action_policy,
            store_raw_text=store_raw_text,
            items=items,
            fields=schema_fields,
        )
        result = ValidationResult(
            decision_id=decision_id,
            schema_name=cls._schema_name(),
            schema_version=cls.schema_version,
            evaluated_at=evaluated,
            context=context or {},
            field_confidences=field_confidences,
            schema_confidence=schema_confidence,
            action=action,
            warnings=warnings,
            retry_recommendations=retry_recommendations,
            evidence_record=evidence_record,
        )

        if evidence_log is not None:
            writer = evidence_log if isinstance(evidence_log, DecisionEvidenceLog) else DecisionEvidenceLog(evidence_log)
            writer.write(result)

        return result

    @classmethod
    def _schema_name(cls) -> str:
        return cls.schema_name or cls.__name__


class DecisionRegistry:
    """Named registry of schemas for agents that handle multiple decision types.

    Use one `ContextSchema` subclass per decision/action class, then register
    those schemas under stable decision-type names such as `"markdown"`,
    `"store_transfer"`, or `"root_cause"`.
    """

    def __init__(self, schemas: Mapping[str, type[ContextSchema]] | None = None):
        self._schemas: dict[str, type[ContextSchema]] = {}
        for decision_type, schema in (schemas or {}).items():
            self.register(decision_type, schema)

    def __contains__(self, decision_type: object) -> bool:
        return decision_type in self._schemas

    def __iter__(self) -> Iterator[str]:
        return iter(self._schemas)

    def __len__(self) -> int:
        return len(self._schemas)

    def register(
        self,
        decision_type: str,
        schema: type[ContextSchema],
        *,
        replace: bool = False,
    ) -> "DecisionRegistry":
        """Register a schema class for a decision type.

        By default, duplicate decision types raise `ContextSchemaError`.
        Pass `replace=True` to intentionally update an existing registration.
        """

        normalized = _normalize_decision_type(decision_type)
        _validate_schema_class(schema)
        if normalized in self._schemas and not replace:
            raise ContextSchemaError(f"Decision type already registered: {normalized}")
        self._schemas[normalized] = schema
        return self

    def unregister(self, decision_type: str) -> type[ContextSchema]:
        """Remove and return the schema registered for a decision type."""

        normalized = _normalize_decision_type(decision_type)
        try:
            return self._schemas.pop(normalized)
        except KeyError:
            raise ContextSchemaError(f"Unknown decision type: {normalized}") from None

    def get(self, decision_type: str) -> type[ContextSchema] | None:
        """Return the schema for a decision type, or `None` if not registered."""

        return self._schemas.get(_normalize_decision_type(decision_type))

    def require(self, decision_type: str) -> type[ContextSchema]:
        """Return the schema for a decision type or raise `ContextSchemaError`."""

        normalized = _normalize_decision_type(decision_type)
        schema = self._schemas.get(normalized)
        if schema is None:
            available = ", ".join(self.decision_types()) or "none"
            raise ContextSchemaError(f"Unknown decision type: {normalized}. Available decision types: {available}")
        return schema

    def decision_types(self) -> tuple[str, ...]:
        """Return registered decision types in registration order."""

        return tuple(self._schemas)

    def schema_definitions(self) -> dict[str, dict[str, Any]]:
        """Return JSON-compatible definitions for all registered schemas."""

        return {
            decision_type: schema.schema_definition()
            for decision_type, schema in self._schemas.items()
        }


class SchemaRouter:
    """Route validation to the schema registered for a decision type."""

    def __init__(self, registry: DecisionRegistry | Mapping[str, type[ContextSchema]]):
        self.registry = registry if isinstance(registry, DecisionRegistry) else DecisionRegistry(registry)

    def route(self, decision_type: str) -> type[ContextSchema]:
        """Return the schema class registered for `decision_type`."""

        return self.registry.require(decision_type)

    def validate(
        self,
        decision_type: str,
        items: list[RetrievedItem],
        *,
        decision_id: str,
        events: list[EventRecord] | None = None,
        evaluated_at: datetime | None = None,
        context: dict[str, Any] | None = None,
        source_reliability: dict[str, float] | None = None,
        evidence_log: DecisionEvidenceLog | str | Path | None = None,
        store_raw_text: bool = False,
    ) -> ValidationResult:
        """Validate retrieved context using the schema for `decision_type`."""

        schema = self.route(decision_type)
        return schema.validate_retrieved(
            items,
            decision_id=decision_id,
            events=events,
            evaluated_at=evaluated_at,
            context=context,
            source_reliability=source_reliability,
            evidence_log=evidence_log,
            store_raw_text=store_raw_text,
        )

    def schema_definitions(self) -> dict[str, dict[str, Any]]:
        """Return schema definitions keyed by registered decision type."""

        return self.registry.schema_definitions()


def load_events_jsonl(path: str | Path, *, strict: bool = True) -> list[EventRecord]:
    """Load invalidation events from JSONL.

    In strict mode, the first malformed line raises `ContextSchemaError`.
    With `strict=False`, malformed lines are skipped.
    """

    events: list[EventRecord] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(EventRecord.from_dict(json.loads(stripped)))
            except Exception:
                if strict:
                    raise ContextSchemaError(f"Invalid event JSONL record at line {line_number}") from None
    return events


def explain_evidence(record: dict[str, Any]) -> str:
    """Return a short human-readable summary of an evidence record."""

    action = record.get("action", "unknown")
    score = record.get("schema_confidence", {}).get("score", "unknown")
    weakest = record.get("schema_confidence", {}).get("weakest_fields", [])
    lines = [
        f"Decision {record.get('decision_id', 'unknown')} returned {action}.",
        f"Schema confidence: {score}.",
    ]
    if weakest:
        lines.append(f"Weakest fields: {', '.join(weakest)}.")
    return " ".join(lines)


def _score_field(
    *,
    field_name: str,
    field: ContextField,
    items: list[RetrievedItem],
    events: list[EventRecord],
    evaluated_at: datetime,
    source_reliability: dict[str, float],
) -> FieldConfidence:
    candidates, ambiguous = _match_candidates(field_name, field, items)
    if not candidates:
        status: FieldStatus = "missing" if field.required else "missing_optional"
        score = 0.0 if field.required else 1.0
        reason = "missing_required_field" if field.required else "missing_optional_field"
        return FieldConfidence(
            field_name=field_name,
            score=score,
            components={
                "match_factor": score,
                "metadata_factor": 1.0,
                "time_factor": 1.0,
                "event_factor": 1.0,
                "source_reliability_factor": 1.0,
                "fallback_factor": 1.0,
            },
            status=status,
            reasons=[Reason(reason, "error" if field.required else "info", f"{field_name} did not match retrieved context.")],
        )

    scored = [
        _score_candidate(field_name, field, candidate, events, evaluated_at, source_reliability, ambiguous)
        for candidate in candidates
    ]
    scored.sort(key=lambda result: (-result.score, result.matched_item_ids[0]))
    best = scored[0]
    if ambiguous:
        best = _with_ambiguity_context(best, candidates, scored)
    return best


def _match_candidates(
    field_name: str,
    field: ContextField,
    items: list[RetrievedItem],
) -> tuple[list[RetrievedItem], bool]:
    exact = [item for item in items if item.metadata.get("context_field") == field_name]
    if exact:
        return exact, len(exact) > 1

    hinted = []
    for item in items:
        hints = _as_string_list(item.metadata.get("field_hints", []))
        if field_name in hints:
            hinted.append(item)
    if hinted:
        return hinted, len(hinted) > 1

    if field.sources:
        source_matches = [item for item in items if item.metadata.get("source") in field.sources]
        if len(source_matches) == 1:
            return source_matches, False
        if len(source_matches) > 1:
            return source_matches, True

    return [], False


def _score_candidate(
    field_name: str,
    field: ContextField,
    item: RetrievedItem,
    events: list[EventRecord],
    evaluated_at: datetime,
    configured_source_reliability: dict[str, float],
    ambiguous: bool,
) -> FieldConfidence:
    reasons: list[Reason] = []
    source = item.metadata.get("source")
    source_ref = item.metadata.get("source_ref") or item.metadata.get("provenance_ref")
    timestamp_key, timestamp = _evidence_timestamp(item.metadata)
    timestamps = {timestamp_key: timestamp.isoformat()} if timestamp_key and timestamp else {}

    match_factor = 1.0
    metadata_factor = _metadata_factor(field, item, ambiguous, reasons)
    time_factor = _time_factor(field, timestamp, evaluated_at, reasons)
    event_factor, invalidating_events = _event_factor(
        field_name,
        field,
        item,
        events,
        timestamp,
        reasons,
    )
    source_reliability_factor = _source_reliability_factor(
        field,
        item,
        configured_source_reliability,
        reasons,
    )
    fallback_factor = 1.0

    score = _clip(
        match_factor
        * metadata_factor
        * time_factor
        * event_factor
        * source_reliability_factor
        * fallback_factor
    )
    components = {
        "match_factor": match_factor,
        "metadata_factor": metadata_factor,
        "time_factor": time_factor,
        "event_factor": event_factor,
        "source_reliability_factor": source_reliability_factor,
        "fallback_factor": fallback_factor,
    }
    status = _status_from_components(metadata_factor, event_factor, source_reliability_factor, reasons)

    return FieldConfidence(
        field_name=field_name,
        score=round(score, 6),
        components=components,
        status=status,
        reasons=reasons,
        matched_item_ids=[item.id],
        source_refs=[source_ref or source or "unknown"],
        timestamps=timestamps,
        invalidating_events=invalidating_events,
    )


def _with_ambiguity_context(
    best: FieldConfidence,
    candidates: list[RetrievedItem],
    scored: list[FieldConfidence],
) -> FieldConfidence:
    tied = [
        confidence
        for confidence in scored
        if confidence.score == best.score
    ]
    matched_item_ids = sorted(
        {
            item_id
            for confidence in tied
            for item_id in confidence.matched_item_ids
        }
    )
    source_refs = sorted(
        {
            source_ref
            for confidence in tied
            for source_ref in confidence.source_refs
        }
    )
    timestamps = dict(best.timestamps)
    for confidence in tied:
        timestamps.update(confidence.timestamps)

    reasons = list(best.reasons)
    reasons.append(
        Reason(
            "ambiguous_multiple_candidates",
            "warning",
            "Multiple candidates matched; the highest-ranked candidate was used.",
            {
                "candidate_item_ids": sorted(item.id for item in candidates),
                "selected_item_ids": matched_item_ids,
            },
        )
    )
    return FieldConfidence(
        field_name=best.field_name,
        score=best.score,
        components=dict(best.components),
        status=best.status,
        reasons=reasons,
        matched_item_ids=matched_item_ids,
        source_refs=source_refs,
        timestamps=timestamps,
        invalidating_events=sorted(
            {
                event_id
                for confidence in tied
                for event_id in confidence.invalidating_events
            }
        ),
    )


def _metadata_factor(
    field: ContextField,
    item: RetrievedItem,
    ambiguous: bool,
    reasons: list[Reason],
) -> float:
    factor = 1.0
    metadata = item.metadata
    if not metadata.get("source"):
        factor -= 0.20
        reasons.append(Reason("metadata_source_missing", "warning", "Metadata is missing source."))
    if not metadata.get("source_ref"):
        factor -= 0.20
        reasons.append(Reason("metadata_source_ref_missing", "warning", "Metadata is missing source_ref."))
    if field.ttl is not None and _evidence_timestamp(metadata)[1] is None:
        factor -= 0.20
        reasons.append(Reason("metadata_timestamp_missing", "warning", "No usable timestamp exists for a TTL-bound field."))
    if not metadata.get("provenance_ref") and not metadata.get("source_ref"):
        factor -= 0.10
        reasons.append(Reason("metadata_provenance_missing", "warning", "No provenance metadata exists."))
    if ambiguous:
        factor -= 0.10
    return _clip(factor)


def _time_factor(
    field: ContextField,
    timestamp: datetime | None,
    evaluated_at: datetime,
    reasons: list[Reason],
) -> float:
    if field.ttl is None:
        return 1.0
    if timestamp is None:
        reasons.append(Reason("timestamp_missing_for_ttl", "warning", "TTL is configured but no usable timestamp was found."))
        return 0.6
    age = evaluated_at - timestamp
    if age < timedelta(0):
        reasons.append(Reason("timestamp_in_future", "warning", "Evidence timestamp is in the future."))
        return 1.0
    factor = _clip(1.0 - (age.total_seconds() / field.ttl.total_seconds()))
    if age > field.ttl:
        reasons.append(
            Reason(
                "ttl_decay",
                "warning",
                "Evidence timestamp is older than the configured TTL.",
                {"age_seconds": age.total_seconds(), "ttl_seconds": field.ttl.total_seconds()},
            )
        )
    elif factor < 1.0:
        reasons.append(
            Reason(
                "ttl_age_decay",
                "info",
                "Evidence confidence was reduced as it aged within the configured TTL.",
                {"age_seconds": age.total_seconds(), "ttl_seconds": field.ttl.total_seconds()},
            )
        )
    return factor


def _event_factor(
    field_name: str,
    field: ContextField,
    item: RetrievedItem,
    events: list[EventRecord],
    timestamp: datetime | None,
    reasons: list[Reason],
) -> tuple[float, list[str]]:
    if not field.invalidates_on:
        return 1.0, []

    if timestamp is None:
        severity: Severity = "warning" if field.event_policy == "optional" else "error"
        reasons.append(Reason("event_comparison_unknown", severity, "Cannot compare invalidation events without evidence timestamp."))
        return (0.6 if field.event_policy == "required" else 1.0), []

    invalidating: list[str] = []
    item_source = item.metadata.get("source")
    item_source_ref = item.metadata.get("source_ref") or item.metadata.get("provenance_ref")
    for event in events:
        if event.event_type not in field.invalidates_on:
            continue
        if event.occurred_at <= timestamp:
            continue
        targets_field = not event.affected_fields or field_name in event.affected_fields
        targets_source = not event.affected_sources or item_source in event.affected_sources
        targets_ref = not event.source_ref or event.source_ref == item_source_ref
        if targets_field and targets_source and targets_ref:
            invalidating.append(event.event_id)

    if invalidating:
        reasons.append(
            Reason(
                "event_invalidated",
                "error",
                "A matching invalidation event occurred after the evidence timestamp.",
                {"event_ids": invalidating},
            )
        )
        return 0.0, invalidating

    return 1.0, []


def _source_reliability_factor(
    field: ContextField,
    item: RetrievedItem,
    configured: dict[str, float],
    reasons: list[Reason],
) -> float:
    source = item.metadata.get("source")
    raw = item.metadata.get("source_reliability")
    if raw is None and source is not None:
        raw = configured.get(source)
    value = _coerce_score(raw, default=1.0, reasons=reasons, code="source_reliability_invalid") if raw is not None else 1.0

    if field.sources and source not in field.sources:
        reasons.append(Reason("source_not_expected", "warning", "Source is not configured for this field.", {"source": source}))
        value = min(value, 0.5)

    if field.min_source_reliability is not None and value < field.min_source_reliability:
        reasons.append(
            Reason(
                "source_reliability_below_minimum",
                "warning",
                "Source reliability is below the field minimum.",
                {"source_reliability": value, "minimum": field.min_source_reliability},
            )
        )
    return value


def _status_from_components(
    metadata_factor: float,
    event_factor: float,
    source_reliability_factor: float,
    reasons: list[Reason],
) -> FieldStatus:
    if event_factor == 0.0:
        return "event_invalidated"
    if any(reason.code == "ttl_decay" for reason in reasons):
        return "stale"
    if metadata_factor < 1.0:
        return "metadata_insufficient"
    if source_reliability_factor < 1.0:
        return "weak_source"
    return "valid"


def _aggregate_schema_confidence(
    fields: dict[str, ContextField],
    field_confidences: list[FieldConfidence],
) -> SchemaConfidence:
    by_name = {field.field_name: field for field in field_confidences}
    total_weight = sum(field.criticality for field in fields.values())
    if total_weight == 0:
        weighted_mean_score = 1.0
    else:
        weighted_mean_score = sum(
            field.criticality * by_name[name].score
            for name, field in fields.items()
        ) / total_weight

    weakest_penalty = max(
        (field.criticality * (1.0 - by_name[name].score) for name, field in fields.items()),
        default=0.0,
    )
    weakest_penalty_score = 1.0 - weakest_penalty
    score = min(weighted_mean_score, weakest_penalty_score)

    required_missing = [
        name for name, field in fields.items()
        if field.required and by_name[name].status == "missing"
    ]
    event_invalidated = [
        name for name, field in fields.items()
        if field.required and by_name[name].status == "event_invalidated"
    ]
    if required_missing:
        score = 0.0
    if event_invalidated:
        score = min(score, min(by_name[name].score for name in event_invalidated))

    weakest_score = min((field.score for field in field_confidences), default=1.0)
    weakest_fields = [
        field.field_name for field in field_confidences
        if field.score == weakest_score
    ]

    return SchemaConfidence(
        score=round(_clip(score), 6),
        aggregation_method="weighted_weakest_field_with_mean_cap",
        weakest_fields=weakest_fields,
        required_missing=required_missing,
        event_invalidated=event_invalidated,
    )


def _build_evidence_record(
    *,
    decision_id: str,
    schema_name: str,
    schema_version: str,
    evaluated_at: datetime,
    context: dict[str, Any],
    field_confidences: list[FieldConfidence],
    schema_confidence: SchemaConfidence,
    action: Action,
    warnings: list[str],
    retry_recommendations: list[str],
    action_policy: ActionPolicy,
    store_raw_text: bool,
    items: list[RetrievedItem],
    fields: dict[str, ContextField],
) -> dict[str, Any]:
    items_by_id = {item.id: item for item in items}
    field_records: dict[str, Any] = {}
    for confidence in field_confidences:
        record = confidence.to_dict()
        record["privacy_tags"] = list(fields[confidence.field_name].privacy_tags)
        record["required"] = fields[confidence.field_name].required
        record["criticality"] = fields[confidence.field_name].criticality
        if store_raw_text:
            record["raw_text"] = {
                item_id: items_by_id[item_id].text
                for item_id in confidence.matched_item_ids
                if item_id in items_by_id
            }
        field_records[confidence.field_name] = record

    return {
        "record_version": "contextschema.evidence.v1",
        "decision_id": decision_id,
        "schema_name": schema_name,
        "schema_version": schema_version,
        "evaluated_at": evaluated_at.isoformat(),
        "context": _jsonable(context),
        "action": action,
        "warnings": list(warnings),
        "retry_recommendations": list(retry_recommendations),
        "schema_confidence": schema_confidence.to_dict(),
        "fields": field_records,
        "policy": action_policy.to_dict(),
        "privacy": {
            "raw_text_stored": store_raw_text,
            "redaction_tags": sorted(
                {
                    tag
                    for field_definition in fields.values()
                    for tag in field_definition.privacy_tags
                }
            ),
        },
        "exports": {},
    }


def _metadata_completeness_score(item: RetrievedItem) -> int:
    score = 0
    metadata = item.metadata
    score += int(bool(metadata.get("source")))
    score += int(bool(metadata.get("source_ref")))
    score += int(bool(metadata.get("provenance_ref")))
    score += int(_evidence_timestamp(metadata)[1] is not None)
    return score


def _normalize_decision_type(decision_type: str) -> str:
    if not isinstance(decision_type, str):
        raise ContextSchemaError("decision_type must be a string")
    normalized = decision_type.strip()
    if not normalized:
        raise ContextSchemaError("decision_type is required")
    return normalized


def _validate_schema_class(schema: type[ContextSchema]) -> None:
    if not isinstance(schema, type) or not issubclass(schema, ContextSchema) or schema is ContextSchema:
        raise ContextSchemaError("schema must be a ContextSchema subclass")
    if not schema.fields():
        raise ContextSchemaError("registered schemas must define at least one ContextField")


def _evidence_timestamp(metadata: dict[str, Any]) -> tuple[str | None, datetime | None]:
    for key in TIMESTAMP_KEYS:
        parsed = parse_datetime(metadata.get(key), strict=False)
        if parsed is not None:
            return key, parsed
    return None, None


def parse_datetime(value: Any, *, strict: bool = True) -> datetime | None:
    if value is None:
        if strict:
            raise ContextSchemaError("datetime value is required")
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        try:
            return _ensure_aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            if strict:
                raise ContextSchemaError(f"Invalid datetime: {value}") from None
            return None
    if strict:
        raise ContextSchemaError(f"Unsupported datetime value: {value!r}")
    return None


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _coerce_score(raw: Any, *, default: float, reasons: list[Reason], code: str) -> float:
    try:
        return _clip(float(raw))
    except (TypeError, ValueError):
        reasons.append(
            Reason(
                code,
                "warning",
                "Score metadata could not be parsed; default was used.",
                {"raw_value": raw, "default": default},
            )
        )
        return default


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [
            item
            for item in value
            if isinstance(item, str) and item
        ]
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, Reason):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value
