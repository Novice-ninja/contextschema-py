"""Sales/revops example: validate context before recommending a next step.

Scenario:
    A revenue agent is about to recommend the next action for opportunity
    OPP-9001: send a discount proposal, book an executive call, or wait.

Assumptions:
    - CRM stage and stakeholder map can change quickly.
    - Pricing guidance and legal constraints must be reasonably fresh.
    - Intent signals from email/call summaries are useful but lower trust than CRM.
    - If pricing guidance was updated after retrieval, the agent should retry before
      sending a commercial recommendation.
"""

from datetime import UTC, datetime, timedelta

from contextschema import ActionPolicy, ContextField, ContextSchema, EventRecord, RetrievedItem


class SalesNextStepDecision(ContextSchema):
    schema_version = "example-1"
    action_policy = ActionPolicy(
        proceed_at_or_above=0.84,
        retry_below=0.72,
        soft_flag_below=0.84,
        hard_gate_on_event_invalidated_required_field=True,
    )

    opportunity_stage = ContextField(
        source="crm",
        ttl=timedelta(minutes=30),
        criticality=1.0,
        required=True,
        invalidates_on=["opportunity_stage_changed"],
    )
    stakeholder_map = ContextField(
        source=["crm", "call_summary"],
        ttl=timedelta(days=7),
        criticality=0.8,
        required=True,
        invalidates_on=["stakeholder_updated"],
    )
    pricing_guidance = ContextField(
        source="pricing_policy",
        ttl=timedelta(days=3),
        criticality=1.0,
        required=True,
        invalidates_on=["discount_policy_updated"],
    )
    buyer_intent = ContextField(
        source=["email_summary", "call_summary"],
        ttl=timedelta(days=2),
        criticality=0.6,
        required=True,
        min_source_reliability=0.7,
    )


def run():
    evaluated_at = datetime(2026, 5, 25, 19, 0, tzinfo=UTC)
    items = [
        RetrievedItem(
            id="crm-stage",
            text="Opportunity OPP-9001 is in procurement review.",
            metadata={
                "context_field": "opportunity_stage",
                "source": "crm",
                "source_ref": "crm:opportunity:OPP-9001",
                "valid_at": "2026-05-25T18:45:00Z",
            },
        ),
        RetrievedItem(
            id="stakeholders",
            text="Economic buyer is VP Ops; security reviewer joined last week.",
            metadata={
                "context_field": "stakeholder_map",
                "source": "call_summary",
                "source_ref": "call:OPP-9001:2026-05-22",
                "valid_at": "2026-05-22T20:00:00Z",
                "source_reliability": 0.78,
            },
        ),
        RetrievedItem(
            id="pricing",
            text="Discounts above 15 percent require finance approval.",
            metadata={
                "context_field": "pricing_guidance",
                "source": "pricing_policy",
                "source_ref": "pricing:discount:v4",
                "last_modified_at": "2026-05-20T12:00:00Z",
            },
        ),
        RetrievedItem(
            id="intent",
            text="Buyer asked for implementation dates and procurement paperwork.",
            metadata={
                "context_field": "buyer_intent",
                "source": "email_summary",
                "source_ref": "email-thread:OPP-9001",
                "valid_at": "2026-05-24T15:00:00Z",
                "source_reliability": 0.74,
            },
        ),
    ]
    events = [
        EventRecord(
            event_id="evt-price-2",
            event_type="discount_policy_updated",
            occurred_at=datetime(2026, 5, 25, 9, 0, tzinfo=UTC),
            affected_fields=["pricing_guidance"],
            affected_sources=["pricing_policy"],
            source_ref="pricing:discount:v4",
        )
    ]

    return SalesNextStepDecision.validate_retrieved(
        items,
        decision_id="sales-next-step-OPP-9001",
        events=events,
        evaluated_at=evaluated_at,
        context={"opportunity_id": "OPP-9001"},
    )


if __name__ == "__main__":
    result = run()
    print(result.action)
    print(result.schema_confidence.score)
    print(result.to_policy_input())
