"""Route a merchandising super-agent to different context schemas.

Scenario:
    One merchandising agent can answer multiple decision types:
    - markdown recommendation
    - store-to-store inventory transfer

    Each decision needs a different context validity contract. Markdown needs
    price and margin guardrails. Store transfer needs source inventory,
    destination demand, and transfer constraints. One giant schema would either
    over-gate simple decisions or under-gate risky ones.
"""

from datetime import UTC, datetime, timedelta

from contextschema import ActionPolicy, ContextField, ContextSchema, DecisionRegistry, RetrievedItem, SchemaRouter


class MarkdownDecision(ContextSchema):
    schema_version = "example-1"
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
    schema_version = "example-1"
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


def build_router() -> SchemaRouter:
    registry = DecisionRegistry(
        {
            "markdown": MarkdownDecision,
            "store_transfer": StoreTransferDecision,
        }
    )
    return SchemaRouter(registry)


def run():
    router = build_router()
    evaluated_at = datetime(2026, 5, 25, 16, 5, tzinfo=UTC)

    markdown_result = router.validate(
        "markdown",
        [
            RetrievedItem(
                id="sales-1",
                metadata={
                    "context_field": "sales_trend",
                    "source": "sales_mart",
                    "source_ref": "sales:SKU-742:week-21",
                    "valid_at": "2026-05-25T16:05:00Z",
                },
            ),
            RetrievedItem(
                id="price-1",
                metadata={
                    "context_field": "current_price",
                    "source": "pricing_api",
                    "source_ref": "pricebook:US:SKU-742",
                    "valid_at": "2026-05-25T16:05:00Z",
                },
            ),
        ],
        decision_id="merch-markdown-1",
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
                    "source_ref": "inventory:store-100:SKU-742",
                    "valid_at": "2026-05-25T16:05:00Z",
                },
            ),
            RetrievedItem(
                id="demand-1",
                metadata={
                    "context_field": "destination_store_demand",
                    "source": "demand_forecast",
                    "source_ref": "forecast:store-212:SKU-742",
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
        decision_id="merch-transfer-1",
        evaluated_at=evaluated_at,
    )

    return {
        "markdown": markdown_result,
        "store_transfer": transfer_result,
        "schema_definitions": router.schema_definitions(),
    }


if __name__ == "__main__":
    results = run()
    print("markdown", results["markdown"].action, results["markdown"].schema_confidence.required_missing)
    print("store_transfer", results["store_transfer"].action, results["store_transfer"].schema_confidence.score)
