"""Customer service example: validate refund-decision context."""

from datetime import UTC, datetime, timedelta

from contextschema import ActionPolicy, ContextField, ContextSchema, EventRecord, RetrievedItem


class RefundDecision(ContextSchema):
    schema_version = "example-1"
    action_policy = ActionPolicy(
        proceed_at_or_above=0.85,
        retry_below=0.72,
        soft_flag_below=0.85,
        hard_gate_on_event_invalidated_required_field=True,
    )

    order_status = ContextField(
        source=["orders_api", "crm_order_snapshot"],
        ttl=timedelta(minutes=10),
        criticality=1.0,
        required=True,
        invalidates_on=["order_status_changed"],
    )
    refund_policy = ContextField(
        source="policy_cms",
        ttl=timedelta(days=7),
        criticality=0.7,
        required=True,
        invalidates_on=["refund_policy_updated"],
    )
    customer_entitlement = ContextField(
        source=["entitlements_api", "billing_api"],
        ttl=timedelta(minutes=30),
        criticality=1.0,
        required=True,
        invalidates_on=["subscription_changed", "chargeback_opened"],
    )
    account_risk = ContextField(
        source="risk_service",
        ttl=timedelta(hours=1),
        criticality=0.8,
        required=True,
        min_source_reliability=0.8,
    )


def run():
    evaluated_at = datetime(2026, 5, 25, 17, 0, tzinfo=UTC)
    items = [
        RetrievedItem(
            id="order-123",
            text="Order A1001 was delivered yesterday.",
            metadata={
                "context_field": "order_status",
                "source": "crm_order_snapshot",
                "source_ref": "crm:orders:A1001",
                "valid_at": "2026-05-25T16:45:00Z",
                "source_reliability": 0.72,
            },
        ),
        RetrievedItem(
            id="policy-refund-v8",
            text="Refunds are available within 30 days for unopened items.",
            metadata={
                "context_field": "refund_policy",
                "source": "policy_cms",
                "source_ref": "policy:refund:v8",
                "last_modified_at": "2026-05-19T12:00:00Z",
            },
        ),
        RetrievedItem(
            id="entitlement-44",
            text="Customer has active premium support entitlement.",
            metadata={
                "context_field": "customer_entitlement",
                "source": "entitlements_api",
                "source_ref": "entitlement:customer:C44",
                "valid_at": "2026-05-25T16:50:00Z",
            },
        ),
        RetrievedItem(
            id="risk-44",
            text="No current refund abuse flags.",
            metadata={
                "context_field": "account_risk",
                "source": "risk_service",
                "source_ref": "risk:customer:C44",
                "valid_at": "2026-05-25T16:40:00Z",
                "source_reliability": 0.91,
            },
        ),
    ]
    events = [
        EventRecord(
            event_id="evt-order-9",
            event_type="order_status_changed",
            occurred_at=datetime(2026, 5, 25, 16, 54, tzinfo=UTC),
            affected_fields=["order_status"],
            affected_sources=["crm_order_snapshot"],
            source_ref="crm:orders:A1001",
        )
    ]

    return RefundDecision.validate_retrieved(
        items,
        decision_id="refund-decision-A1001",
        events=events,
        evaluated_at=evaluated_at,
        context={"customer_id": "C44", "order_id": "A1001"},
    )


if __name__ == "__main__":
    result = run()
    print(result.action)
    print(result.schema_confidence.score)
    print(result.to_policy_input())
