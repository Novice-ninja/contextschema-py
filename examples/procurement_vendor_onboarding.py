"""Procurement example: validate context before approving vendor onboarding.

Scenario:
    A procurement agent is about to approve vendor V-204 for onboarding.

Assumptions:
    - Sanctions/risk evidence is critical and can be invalidated by new screening.
    - Contract and insurance evidence changes less often but must be present.
    - Spend threshold determines whether finance approval is required.
    - If sanctions screening changes after retrieval, the onboarding action must stop.
"""

from datetime import UTC, datetime, timedelta

from contextschema import ActionPolicy, ContextField, ContextSchema, EventRecord, RetrievedItem


class VendorOnboardingDecision(ContextSchema):
    schema_version = "example-1"
    action_policy = ActionPolicy(
        proceed_at_or_above=0.86,
        retry_below=0.74,
        soft_flag_below=0.86,
        hard_gate_on_event_invalidated_required_field=True,
        hard_gate_on_missing_required=True,
    )

    sanctions_screening = ContextField(
        source="risk_screening",
        ttl=timedelta(hours=12),
        criticality=1.0,
        required=True,
        invalidates_on=["sanctions_screening_updated"],
        min_source_reliability=0.9,
    )
    contract_status = ContextField(
        source="contract_lifecycle",
        ttl=timedelta(days=1),
        criticality=0.9,
        required=True,
        invalidates_on=["contract_status_changed"],
    )
    insurance_certificate = ContextField(
        source="vendor_portal",
        ttl=timedelta(days=30),
        criticality=0.6,
        required=True,
        invalidates_on=["insurance_certificate_updated"],
    )
    spend_approval = ContextField(
        source="erp",
        ttl=timedelta(days=2),
        criticality=0.8,
        required=True,
        invalidates_on=["approval_matrix_changed"],
    )


def run():
    evaluated_at = datetime(2026, 5, 25, 20, 0, tzinfo=UTC)
    items = [
        RetrievedItem(
            id="risk-v204",
            text="Vendor V-204 passed sanctions screening.",
            metadata={
                "context_field": "sanctions_screening",
                "source": "risk_screening",
                "source_ref": "risk:vendor:V-204",
                "valid_at": "2026-05-25T07:00:00Z",
                "source_reliability": 0.96,
            },
        ),
        RetrievedItem(
            id="contract-v204",
            text="MSA is approved pending countersignature.",
            metadata={
                "context_field": "contract_status",
                "source": "contract_lifecycle",
                "source_ref": "clm:contract:V-204",
                "valid_at": "2026-05-25T13:30:00Z",
            },
        ),
        RetrievedItem(
            id="insurance-v204",
            text="Certificate of insurance valid through 2027-02-01.",
            metadata={
                "context_field": "insurance_certificate",
                "source": "vendor_portal",
                "source_ref": "vendor:V-204:coi",
                "last_modified_at": "2026-05-01T10:00:00Z",
            },
        ),
        RetrievedItem(
            id="approval-v204",
            text="Spend is below finance approval threshold.",
            metadata={
                "context_field": "spend_approval",
                "source": "erp",
                "source_ref": "erp:vendor:V-204:approval",
                "valid_at": "2026-05-24T18:00:00Z",
            },
        ),
    ]
    events = [
        EventRecord(
            event_id="evt-risk-77",
            event_type="sanctions_screening_updated",
            occurred_at=datetime(2026, 5, 25, 18, 40, tzinfo=UTC),
            affected_fields=["sanctions_screening"],
            affected_sources=["risk_screening"],
            source_ref="risk:vendor:V-204",
        )
    ]

    return VendorOnboardingDecision.validate_retrieved(
        items,
        decision_id="vendor-onboarding-V-204",
        events=events,
        evaluated_at=evaluated_at,
        context={"vendor_id": "V-204"},
    )


if __name__ == "__main__":
    result = run()
    print(result.action)
    print(result.schema_confidence.score)
    print(result.to_policy_input())
