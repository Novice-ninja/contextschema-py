from datetime import UTC, datetime, timedelta
import json
import tempfile
import unittest

from contextschema import (
    ActionPolicy,
    ContextField,
    ContextSchema,
    ContextSchemaError,
    DecisionEvidenceLog,
    DecisionRegistry,
    EventRecord,
    RetrievedItem,
    SchemaRouter,
    explain_evidence,
    load_events_jsonl,
)


class RetailBuyDecision(ContextSchema):
    schema_version = "test"
    action_policy = ActionPolicy(
        retry_below=0.75,
        soft_flag_below=0.75,
        hard_gate_on_event_invalidated_required_field=True,
    )

    inventory_available = ContextField(
        source=["inventory_api", "warehouse_snapshot"],
        ttl=timedelta(minutes=5),
        invalidates_on=["inventory_adjusted"],
        criticality=1.0,
        required=True,
    )
    current_price = ContextField(
        source="pricing_api",
        ttl=timedelta(minutes=15),
        criticality=1.0,
        required=True,
    )
    return_policy = ContextField(
        source="policy_cms",
        ttl=timedelta(days=7),
        criticality=0.4,
        required=False,
    )


class SoftFlagDecision(ContextSchema):
    action_policy = ActionPolicy(
        proceed_at_or_above=0.9,
        retry_below=0.5,
        soft_flag_below=0.9,
    )

    fresh_field = ContextField(
        source="trusted_source",
        ttl=timedelta(hours=1),
        criticality=1.0,
        required=True,
    )


class OptionalFieldDecision(ContextSchema):
    optional_note = ContextField(
        source="notes",
        ttl=timedelta(hours=1),
        criticality=0.2,
        required=False,
    )


class RequiredEventCoverageDecision(ContextSchema):
    action_policy = ActionPolicy(retry_below=0.75)

    entitlement = ContextField(
        source="entitlements_api",
        ttl=timedelta(minutes=30),
        criticality=1.0,
        required=True,
        invalidates_on=["entitlement_changed"],
        event_policy="required",
    )


class AmbiguousSourceDecision(ContextSchema):
    duplicate_context = ContextField(
        source="shared_source",
        ttl=timedelta(hours=1),
        criticality=1.0,
        required=True,
    )


class WeakSourceDecision(ContextSchema):
    action_policy = ActionPolicy(retry_below=0.9)

    account_risk = ContextField(
        source="risk_service",
        ttl=timedelta(hours=1),
        criticality=1.0,
        required=True,
        min_source_reliability=0.8,
    )


class MetadataPenaltyDecision(ContextSchema):
    required_metadata = ContextField(
        source="trusted_source",
        ttl=timedelta(minutes=5),
        criticality=1.0,
        required=True,
    )


class MarkdownDecision(ContextSchema):
    schema_version = "test-router"
    action_policy = ActionPolicy(hard_gate_on_missing_required=True)

    sales_trend = ContextField(
        source="sales_mart",
        ttl=timedelta(hours=2),
        criticality=1.0,
        required=True,
    )
    current_price = ContextField(
        source="pricing_api",
        ttl=timedelta(hours=1),
        criticality=1.0,
        required=True,
    )
    margin_guardrail = ContextField(
        source="pricing_policy",
        ttl=timedelta(days=1),
        criticality=1.0,
        required=True,
    )
    competitor_price = ContextField(
        source="competitor_feed",
        ttl=timedelta(hours=12),
        criticality=0.4,
        required=False,
    )


class StoreTransferDecision(ContextSchema):
    schema_version = "test-router"
    action_policy = ActionPolicy(hard_gate_on_missing_required=True)

    source_store_inventory = ContextField(
        source="inventory_api",
        ttl=timedelta(minutes=30),
        criticality=1.0,
        required=True,
    )
    destination_store_demand = ContextField(
        source="demand_forecast",
        ttl=timedelta(hours=4),
        criticality=1.0,
        required=True,
    )
    transfer_constraints = ContextField(
        source="transfer_rules",
        ttl=timedelta(days=7),
        criticality=1.0,
        required=True,
    )


class EmptyDecision(ContextSchema):
    pass


class TestContextSchemaCore(unittest.TestCase):
    def test_event_invalidated_required_field_hard_gates(self) -> None:
        now = datetime(2026, 5, 25, 16, 5, tzinfo=UTC)
        items = [
            RetrievedItem(
                id="inv-1",
                text="2 units available",
                metadata={
                    "context_field": "inventory_available",
                    "source": "warehouse_snapshot",
                    "source_ref": "warehouse:EWR-1:COAT-742",
                    "valid_at": "2026-05-25T16:00:00Z",
                },
            ),
            RetrievedItem(
                id="price-1",
                text="$139.00",
                metadata={
                    "context_field": "current_price",
                    "source": "pricing_api",
                    "source_ref": "pricebook:US:COAT-742",
                    "valid_at": "2026-05-25T16:04:00Z",
                },
            ),
        ]
        events = [
            EventRecord(
                event_id="evt-1",
                event_type="inventory_adjusted",
                occurred_at=datetime(2026, 5, 25, 16, 3, tzinfo=UTC),
                affected_fields=["inventory_available"],
                affected_sources=["warehouse_snapshot"],
                source_ref="warehouse:EWR-1:COAT-742",
            )
        ]

        result = RetailBuyDecision.validate_retrieved(
            items,
            decision_id="retail-1",
            events=events,
            evaluated_at=now,
        )

        self.assertEqual(result.action, "hard_gate")
        self.assertEqual(result.schema_confidence.event_invalidated, ["inventory_available"])
        inventory = next(field for field in result.field_confidences if field.field_name == "inventory_available")
        self.assertEqual(inventory.status, "event_invalidated")
        self.assertEqual(inventory.score, 0.0)
        self.assertIn("evt-1", inventory.invalidating_events)
        self.assertNotIn("raw_text", result.evidence_record["fields"]["inventory_available"])

    def test_missing_required_field_caps_schema_score(self) -> None:
        now = datetime(2026, 5, 25, 16, 5, tzinfo=UTC)
        result = RetailBuyDecision.validate_retrieved(
            [
                RetrievedItem(
                    id="price-1",
                    metadata={
                        "context_field": "current_price",
                        "source": "pricing_api",
                        "source_ref": "pricebook:US:COAT-742",
                        "valid_at": "2026-05-25T16:04:00Z",
                    },
                )
            ],
            decision_id="retail-2",
            evaluated_at=now,
        )

        self.assertEqual(result.schema_confidence.score, 0.0)
        self.assertEqual(result.schema_confidence.required_missing, ["inventory_available"])
        self.assertEqual(result.action, "retry_recommended")

    def test_metadata_first_matching_uses_field_hints(self) -> None:
        now = datetime(2026, 5, 25, 16, 5, tzinfo=UTC)
        result = RetailBuyDecision.validate_retrieved(
            [
                RetrievedItem(
                    id="policy-1",
                    metadata={
                        "field_hints": ["return_policy"],
                        "source": "policy_cms",
                        "source_ref": "policy:return:v1",
                        "valid_at": "2026-05-25T10:00:00Z",
                    },
                ),
                RetrievedItem(
                    id="inv-1",
                    metadata={
                        "context_field": "inventory_available",
                        "source": "inventory_api",
                        "source_ref": "inventory:COAT-742",
                        "valid_at": "2026-05-25T16:04:00Z",
                    },
                ),
                RetrievedItem(
                    id="price-1",
                    metadata={
                        "context_field": "current_price",
                        "source": "pricing_api",
                        "source_ref": "pricebook:US:COAT-742",
                        "valid_at": "2026-05-25T16:04:00Z",
                    },
                ),
            ],
            decision_id="retail-3",
            evaluated_at=now,
        )

        policy = next(field for field in result.field_confidences if field.field_name == "return_policy")
        self.assertEqual(policy.matched_item_ids, ["policy-1"])
        self.assertEqual(policy.status, "valid")

    def test_evidence_log_writes_jsonl_and_explains(self) -> None:
        now = datetime(2026, 5, 25, 16, 5, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            log = DecisionEvidenceLog(f"{directory}/evidence.jsonl")
            result = RetailBuyDecision.validate_retrieved(
                [
                    RetrievedItem(
                        id="inv-1",
                        metadata={
                            "context_field": "inventory_available",
                            "source": "inventory_api",
                            "source_ref": "inventory:COAT-742",
                            "valid_at": "2026-05-25T16:04:00Z",
                        },
                    ),
                    RetrievedItem(
                        id="price-1",
                        metadata={
                            "context_field": "current_price",
                            "source": "pricing_api",
                            "source_ref": "pricebook:US:COAT-742",
                            "valid_at": "2026-05-25T16:04:00Z",
                        },
                    ),
                ],
                decision_id="retail-4",
                evaluated_at=now,
                evidence_log=log,
            )

            with open(log.path, encoding="utf-8") as handle:
                record = json.loads(handle.readline())

        self.assertEqual(record["decision_id"], "retail-4")
        self.assertEqual(record["record_version"], "contextschema.evidence.v1")
        self.assertIn(result.action, explain_evidence(record))

    def test_result_helpers_and_policy_input(self) -> None:
        now = datetime(2026, 5, 25, 16, 5, tzinfo=UTC)
        result = RetailBuyDecision.validate_retrieved(
            [
                RetrievedItem(
                    id="inv-1",
                    metadata={
                        "context_field": "inventory_available",
                        "source": "inventory_api",
                        "source_ref": "inventory:COAT-742",
                        "valid_at": "2026-05-25T16:04:00Z",
                    },
                ),
                RetrievedItem(
                    id="price-1",
                    metadata={
                        "context_field": "current_price",
                        "source": "pricing_api",
                        "source_ref": "pricebook:US:COAT-742",
                        "valid_at": "2026-05-25T16:04:00Z",
                    },
                ),
            ],
            decision_id="retail-helpers",
            evaluated_at=now,
        )

        self.assertEqual(result.field("inventory_available").matched_item_ids, ["inv-1"])
        self.assertEqual(result.to_policy_input()["fields"][0]["required"], True)
        self.assertIn("inventory_available", RetailBuyDecision.schema_definition()["fields"])

    def test_proceed_threshold_can_soft_flag_without_retry(self) -> None:
        result = SoftFlagDecision.validate_retrieved(
            [
                RetrievedItem(
                    id="fresh-1",
                    metadata={
                        "context_field": "fresh_field",
                        "source": "trusted_source",
                        "source_ref": "trusted:fresh",
                        "valid_at": "2026-05-25T15:35:00Z",
                    },
                )
            ],
            decision_id="soft-flag",
            evaluated_at=datetime(2026, 5, 25, 16, 5, tzinfo=UTC),
        )

        self.assertEqual(result.action, "soft_flag")
        self.assertFalse(result.retry_recommendations)

    def test_load_events_jsonl_strict_false_skips_bad_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/events.jsonl"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{bad json}\n")
                handle.write(json.dumps({
                    "event_id": "evt-ok",
                    "event_type": "inventory_adjusted",
                    "occurred_at": "2026-05-25T16:03:00Z",
                    "affected_fields": ["inventory_available"],
                }) + "\n")

            events = load_events_jsonl(path, strict=False)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, "evt-ok")

    def test_load_events_jsonl_strict_true_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/events.jsonl"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{bad json}\n")

            with self.assertRaises(ContextSchemaError):
                load_events_jsonl(path, strict=True)

    def test_optional_missing_field_does_not_reduce_schema_score(self) -> None:
        result = OptionalFieldDecision.validate_retrieved(
            [],
            decision_id="optional-missing",
            evaluated_at=datetime(2026, 5, 25, 16, 5, tzinfo=UTC),
        )

        self.assertEqual(result.schema_confidence.score, 1.0)
        self.assertEqual(result.field("optional_note").status, "missing_optional")
        self.assertEqual(result.action, "proceed")

    def test_store_raw_text_is_explicit_opt_in(self) -> None:
        result = RetailBuyDecision.validate_retrieved(
            [
                RetrievedItem(
                    id="inv-1",
                    text="sensitive inventory text",
                    metadata={
                        "context_field": "inventory_available",
                        "source": "inventory_api",
                        "source_ref": "inventory:COAT-742",
                        "valid_at": "2026-05-25T16:04:00Z",
                    },
                ),
                RetrievedItem(
                    id="price-1",
                    text="sensitive price text",
                    metadata={
                        "context_field": "current_price",
                        "source": "pricing_api",
                        "source_ref": "pricebook:US:COAT-742",
                        "valid_at": "2026-05-25T16:04:00Z",
                    },
                ),
            ],
            decision_id="raw-text",
            evaluated_at=datetime(2026, 5, 25, 16, 5, tzinfo=UTC),
            store_raw_text=True,
        )

        raw_text = result.evidence_record["fields"]["inventory_available"]["raw_text"]
        self.assertEqual(raw_text["inv-1"], "sensitive inventory text")
        self.assertTrue(result.evidence_record["privacy"]["raw_text_stored"])

    def test_required_event_policy_without_timestamp_reduces_confidence(self) -> None:
        result = RequiredEventCoverageDecision.validate_retrieved(
            [
                RetrievedItem(
                    id="ent-1",
                    metadata={
                        "context_field": "entitlement",
                        "source": "entitlements_api",
                        "source_ref": "entitlement:C44",
                    },
                )
            ],
            decision_id="event-policy",
            evaluated_at=datetime(2026, 5, 25, 16, 5, tzinfo=UTC),
        )

        self.assertEqual(result.field("entitlement").components["event_factor"], 0.6)
        self.assertIn("event_comparison_unknown", result.to_policy_input()["fields"][0]["reasons"])

    def test_ambiguous_candidates_report_candidate_ids(self) -> None:
        result = AmbiguousSourceDecision.validate_retrieved(
            [
                RetrievedItem(
                    id="candidate-b",
                    metadata={
                        "source": "shared_source",
                        "source_ref": "shared:b",
                        "valid_at": "2026-05-25T16:03:00Z",
                        "source_reliability": "not-a-number",
                    },
                ),
                RetrievedItem(
                    id="candidate-a",
                    metadata={
                        "source": "shared_source",
                        "source_ref": "shared:a",
                        "valid_at": "2026-05-25T16:04:00Z",
                    },
                ),
            ],
            decision_id="ambiguous",
            evaluated_at=datetime(2026, 5, 25, 16, 5, tzinfo=UTC),
        )

        field = result.field("duplicate_context")
        ambiguity = next(reason for reason in field.reasons if reason.code == "ambiguous_multiple_candidates")
        self.assertEqual(ambiguity.details["candidate_item_ids"], ["candidate-a", "candidate-b"])
        self.assertEqual(field.matched_item_ids, ["candidate-a"])

    def test_weak_source_status_and_retry_recommendation(self) -> None:
        result = WeakSourceDecision.validate_retrieved(
            [
                RetrievedItem(
                    id="risk-1",
                    metadata={
                        "context_field": "account_risk",
                        "source": "risk_service",
                        "source_ref": "risk:C44",
                        "valid_at": "2026-05-25T16:04:00Z",
                        "source_reliability": 0.55,
                    },
                )
            ],
            decision_id="weak-source",
            evaluated_at=datetime(2026, 5, 25, 16, 5, tzinfo=UTC),
        )

        self.assertEqual(result.field("account_risk").status, "weak_source")
        reason_codes = [reason.code for reason in result.field("account_risk").reasons]
        self.assertIn("source_reliability_below_minimum", reason_codes)
        self.assertEqual(result.action, "retry_recommended")

    def test_malformed_timestamp_receives_metadata_and_ttl_penalties(self) -> None:
        result = MetadataPenaltyDecision.validate_retrieved(
            [
                RetrievedItem(
                    id="bad-time",
                    metadata={
                        "context_field": "required_metadata",
                        "source": "trusted_source",
                        "source_ref": "trusted:record-1",
                        "valid_at": "not-a-timestamp",
                    },
                )
            ],
            decision_id="malformed-timestamp",
            evaluated_at=datetime(2026, 5, 25, 16, 5, tzinfo=UTC),
        )

        field = result.field("required_metadata")
        reason_codes = [reason.code for reason in field.reasons]
        self.assertEqual(field.status, "metadata_insufficient")
        self.assertEqual(field.components["time_factor"], 0.6)
        self.assertLess(field.components["metadata_factor"], 1.0)
        self.assertIn("metadata_timestamp_missing", reason_codes)
        self.assertIn("timestamp_missing_for_ttl", reason_codes)

    def test_missing_metadata_penalties_are_explicit(self) -> None:
        result = MetadataPenaltyDecision.validate_retrieved(
            [
                RetrievedItem(
                    id="metadata-light",
                    metadata={
                        "context_field": "required_metadata",
                    },
                )
            ],
            decision_id="missing-metadata",
            evaluated_at=datetime(2026, 5, 25, 16, 5, tzinfo=UTC),
        )

        field = result.field("required_metadata")
        reason_codes = [reason.code for reason in field.reasons]
        self.assertEqual(field.status, "metadata_insufficient")
        self.assertLess(field.components["metadata_factor"], 1.0)
        self.assertIn("metadata_source_missing", reason_codes)
        self.assertIn("metadata_source_ref_missing", reason_codes)
        self.assertIn("metadata_timestamp_missing", reason_codes)
        self.assertIn("metadata_provenance_missing", reason_codes)
        self.assertIn("source_not_expected", reason_codes)

    def test_empty_schema_raises(self) -> None:
        with self.assertRaises(ContextSchemaError):
            EmptyDecision.validate_retrieved([], decision_id="empty")

    def test_event_record_normalizes_string_lists(self) -> None:
        event = EventRecord.from_dict(
            {
                "event_id": "evt-string",
                "event_type": "order_status_changed",
                "occurred_at": "2026-05-25T16:03:00Z",
                "affected_fields": "order_status",
                "affected_sources": "orders_api",
            }
        )

        self.assertEqual(event.affected_fields, ["order_status"])
        self.assertEqual(event.affected_sources, ["orders_api"])

    def test_decision_registry_routes_to_decision_specific_schema(self) -> None:
        registry = DecisionRegistry(
            {
                "markdown": MarkdownDecision,
                "store_transfer": StoreTransferDecision,
            }
        )
        router = SchemaRouter(registry)
        evaluated_at = datetime(2026, 5, 25, 16, 5, tzinfo=UTC)

        markdown_result = router.validate(
            "markdown",
            [
                RetrievedItem(
                    id="sales-1",
                    metadata={
                        "context_field": "sales_trend",
                        "source": "sales_mart",
                        "source_ref": "sales:SKU-1:week-21",
                        "valid_at": "2026-05-25T16:05:00Z",
                    },
                ),
                RetrievedItem(
                    id="price-1",
                    metadata={
                        "context_field": "current_price",
                        "source": "pricing_api",
                        "source_ref": "price:SKU-1",
                        "valid_at": "2026-05-25T16:05:00Z",
                    },
                ),
            ],
            decision_id="markdown-1",
            evaluated_at=evaluated_at,
        )

        transfer_result = router.validate(
            "store_transfer",
            [
                RetrievedItem(
                    id="source-inv-1",
                    metadata={
                        "context_field": "source_store_inventory",
                        "source": "inventory_api",
                        "source_ref": "inventory:store-1:SKU-1",
                        "valid_at": "2026-05-25T16:05:00Z",
                    },
                ),
                RetrievedItem(
                    id="demand-1",
                    metadata={
                        "context_field": "destination_store_demand",
                        "source": "demand_forecast",
                        "source_ref": "forecast:store-2:SKU-1",
                        "valid_at": "2026-05-25T16:05:00Z",
                    },
                ),
                RetrievedItem(
                    id="rules-1",
                    metadata={
                        "context_field": "transfer_constraints",
                        "source": "transfer_rules",
                        "source_ref": "transfer-rules:standard",
                        "valid_at": "2026-05-25T16:05:00Z",
                    },
                ),
            ],
            decision_id="transfer-1",
            evaluated_at=evaluated_at,
        )

        self.assertEqual(markdown_result.schema_name, "MarkdownDecision")
        self.assertEqual(markdown_result.action, "hard_gate")
        self.assertEqual(markdown_result.schema_confidence.required_missing, ["margin_guardrail"])
        self.assertEqual(transfer_result.schema_name, "StoreTransferDecision")
        self.assertEqual(transfer_result.action, "proceed")
        self.assertEqual(router.route("markdown"), MarkdownDecision)
        self.assertEqual(registry.decision_types(), ("markdown", "store_transfer"))
        self.assertIn("store_transfer", router.schema_definitions())

    def test_decision_registry_rejects_unknown_duplicate_and_invalid_schemas(self) -> None:
        registry = DecisionRegistry()
        registry.register("markdown", MarkdownDecision)

        with self.assertRaises(ContextSchemaError):
            registry.register("markdown", MarkdownDecision)

        with self.assertRaises(ContextSchemaError):
            registry.require("unknown")

        with self.assertRaises(ContextSchemaError):
            registry.register("empty", EmptyDecision)

        registry.register("markdown", StoreTransferDecision, replace=True)
        self.assertEqual(registry.require("markdown"), StoreTransferDecision)


if __name__ == "__main__":
    unittest.main()
