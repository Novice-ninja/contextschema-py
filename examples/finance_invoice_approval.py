"""Finance example: validate context before approving an invoice for payment.

Scenario:
    A finance operations agent is about to approve invoice INV-7781.

Assumptions:
    - Invoice status, purchase-order match, and budget availability are critical.
    - Vendor risk is slower-moving but still matters.
    - If the purchase order was modified after the match evidence was retrieved,
      the agent should retry rather than approve payment.
"""

from datetime import UTC, datetime, timedelta

from contextschema import ActionPolicy, ContextField, ContextSchema, EventRecord, RetrievedItem


class InvoiceApprovalDecision(ContextSchema):
    schema_version = "example-1"
    action_policy = ActionPolicy(
        proceed_at_or_above=0.85,
        retry_below=0.72,
        soft_flag_below=0.85,
        hard_gate_on_event_invalidated_required_field=True,
    )

    invoice_status = ContextField(
        source="erp",
        ttl=timedelta(minutes=30),
        criticality=1.0,
        required=True,
        invalidates_on=["invoice_status_changed"],
    )
    po_match = ContextField(
        source=["erp", "ap_automation"],
        ttl=timedelta(hours=2),
        criticality=1.0,
        required=True,
        invalidates_on=["purchase_order_updated"],
    )
    budget_available = ContextField(
        source="finance_planning",
        ttl=timedelta(hours=4),
        criticality=1.0,
        required=True,
        invalidates_on=["budget_reforecast"],
    )
    vendor_risk = ContextField(
        source="risk_screening",
        ttl=timedelta(days=7),
        criticality=0.7,
        required=True,
        min_source_reliability=0.8,
    )


def run():
    evaluated_at = datetime(2026, 5, 25, 21, 0, tzinfo=UTC)
    items = [
        RetrievedItem(
            id="invoice-status",
            text="Invoice INV-7781 is pending approval.",
            metadata={
                "context_field": "invoice_status",
                "source": "erp",
                "source_ref": "erp:invoice:INV-7781",
                "valid_at": "2026-05-25T20:45:00Z",
            },
        ),
        RetrievedItem(
            id="po-match",
            text="Invoice matches PO-441 within tolerance.",
            metadata={
                "context_field": "po_match",
                "source": "ap_automation",
                "source_ref": "ap:match:INV-7781:PO-441",
                "valid_at": "2026-05-25T18:30:00Z",
            },
        ),
        RetrievedItem(
            id="budget",
            text="Budget remains available in cost center CC-10.",
            metadata={
                "context_field": "budget_available",
                "source": "finance_planning",
                "source_ref": "fpna:budget:CC-10",
                "valid_at": "2026-05-25T19:30:00Z",
            },
        ),
        RetrievedItem(
            id="vendor-risk",
            text="Vendor risk rating is low.",
            metadata={
                "context_field": "vendor_risk",
                "source": "risk_screening",
                "source_ref": "risk:vendor:V-204",
                "valid_at": "2026-05-23T12:00:00Z",
                "source_reliability": 0.84,
            },
        ),
    ]
    events = [
        EventRecord(
            event_id="evt-po-12",
            event_type="purchase_order_updated",
            occurred_at=datetime(2026, 5, 25, 20, 15, tzinfo=UTC),
            affected_fields=["po_match"],
            affected_sources=["ap_automation"],
            source_ref="ap:match:INV-7781:PO-441",
        )
    ]

    return InvoiceApprovalDecision.validate_retrieved(
        items,
        decision_id="invoice-approval-INV-7781",
        events=events,
        evaluated_at=evaluated_at,
        context={"invoice_id": "INV-7781", "vendor_id": "V-204"},
    )


if __name__ == "__main__":
    result = run()
    print(result.action)
    print(result.schema_confidence.score)
    print(result.to_policy_input())
