"""Security/IAM example: validate context before approving access.

Scenario:
    An internal agent is about to approve temporary production database access.

Assumptions:
    - Identity state, manager approval, ticket scope, and risk score are all needed.
    - Access decisions should hard gate on stale or invalidated identity/approval
      evidence.
    - The example avoids integrating IAM systems; it only models the context
      validity check before an agent would call an access tool.
"""

from datetime import UTC, datetime, timedelta

from contextschema import ActionPolicy, ContextField, ContextSchema, EventRecord, RetrievedItem


class AccessApprovalDecision(ContextSchema):
    schema_version = "example-1"
    action_policy = ActionPolicy(
        proceed_at_or_above=0.9,
        retry_below=0.78,
        soft_flag_below=0.9,
        hard_gate_on_event_invalidated_required_field=True,
        hard_gate_on_missing_required=True,
    )

    identity_status = ContextField(
        source="identity_provider",
        ttl=timedelta(minutes=15),
        criticality=1.0,
        required=True,
        invalidates_on=["identity_status_changed"],
    )
    manager_approval = ContextField(
        source="access_workflow",
        ttl=timedelta(hours=2),
        criticality=1.0,
        required=True,
        invalidates_on=["approval_revoked", "approval_updated"],
    )
    ticket_scope = ContextField(
        source="ticketing",
        ttl=timedelta(hours=4),
        criticality=0.8,
        required=True,
        invalidates_on=["ticket_scope_changed"],
    )
    risk_score = ContextField(
        source="security_risk_service",
        ttl=timedelta(minutes=30),
        criticality=1.0,
        required=True,
        min_source_reliability=0.85,
    )


def run():
    evaluated_at = datetime(2026, 5, 25, 23, 0, tzinfo=UTC)
    items = [
        RetrievedItem(
            id="identity",
            text="User U-501 is active and MFA enrolled.",
            metadata={
                "context_field": "identity_status",
                "source": "identity_provider",
                "source_ref": "idp:user:U-501",
                "valid_at": "2026-05-25T22:52:00Z",
            },
        ),
        RetrievedItem(
            id="approval",
            text="Manager approved access until 2026-05-26 03:00 UTC.",
            metadata={
                "context_field": "manager_approval",
                "source": "access_workflow",
                "source_ref": "access:approval:A-778",
                "valid_at": "2026-05-25T21:45:00Z",
            },
        ),
        RetrievedItem(
            id="ticket",
            text="Ticket scope is read-only prod DB access for incident INC-901.",
            metadata={
                "context_field": "ticket_scope",
                "source": "ticketing",
                "source_ref": "ticket:INC-901",
                "valid_at": "2026-05-25T20:30:00Z",
            },
        ),
        RetrievedItem(
            id="risk",
            text="Risk score is low for temporary access.",
            metadata={
                "context_field": "risk_score",
                "source": "security_risk_service",
                "source_ref": "risk:user:U-501",
                "valid_at": "2026-05-25T22:15:00Z",
                "source_reliability": 0.91,
            },
        ),
    ]
    events = [
        EventRecord(
            event_id="evt-approval-2",
            event_type="approval_updated",
            occurred_at=datetime(2026, 5, 25, 22, 30, tzinfo=UTC),
            affected_fields=["manager_approval"],
            affected_sources=["access_workflow"],
            source_ref="access:approval:A-778",
        )
    ]

    return AccessApprovalDecision.validate_retrieved(
        items,
        decision_id="access-approval-U-501",
        events=events,
        evaluated_at=evaluated_at,
        context={"user_id": "U-501", "ticket_id": "INC-901"},
    )


if __name__ == "__main__":
    result = run()
    print(result.action)
    print(result.schema_confidence.score)
    print(result.to_policy_input())
