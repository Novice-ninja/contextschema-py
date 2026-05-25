"""HR employee-support example: validate context before answering a leave request.

Scenario:
    An HR agent is about to tell employee E-810 whether they can take leave next
    week and what policy applies.

Assumptions:
    - Policy documents are slower-moving but must be current enough.
    - Employee eligibility and local holiday calendars change more frequently.
    - Manager approval is optional for this answer, but missing approval should be
      surfaced as a warning rather than blocking a policy explanation.
"""

from datetime import UTC, datetime, timedelta

from contextschema import ActionPolicy, ContextField, ContextSchema, RetrievedItem


class LeaveGuidanceDecision(ContextSchema):
    schema_version = "example-1"
    action_policy = ActionPolicy(
        proceed_at_or_above=0.75,
        retry_below=0.55,
        soft_flag_below=0.75,
    )

    leave_policy = ContextField(
        source="hr_policy_cms",
        ttl=timedelta(days=14),
        criticality=0.8,
        required=True,
        invalidates_on=["leave_policy_updated"],
    )
    employee_eligibility = ContextField(
        source="hris",
        ttl=timedelta(hours=12),
        criticality=1.0,
        required=True,
        invalidates_on=["employee_status_changed"],
    )
    regional_calendar = ContextField(
        source="calendar_service",
        ttl=timedelta(days=7),
        criticality=0.5,
        required=True,
    )
    manager_approval = ContextField(
        source="workflow",
        ttl=timedelta(days=2),
        criticality=0.4,
        required=False,
    )


def run():
    evaluated_at = datetime(2026, 5, 25, 22, 0, tzinfo=UTC)
    items = [
        RetrievedItem(
            id="policy-leave",
            text="Employees may use accrued PTO after 30 days of employment.",
            metadata={
                "context_field": "leave_policy",
                "source": "hr_policy_cms",
                "source_ref": "hr:policy:pto:v12",
                "last_modified_at": "2026-05-20T12:00:00Z",
            },
        ),
        RetrievedItem(
            id="eligibility",
            text="Employee E-810 is active and has 64 PTO hours available.",
            metadata={
                "context_field": "employee_eligibility",
                "source": "hris",
                "source_ref": "hris:employee:E-810:pto",
                "valid_at": "2026-05-25T18:00:00Z",
            },
        ),
        RetrievedItem(
            id="calendar",
            text="No regional public holidays overlap the requested dates.",
            metadata={
                "context_field": "regional_calendar",
                "source": "calendar_service",
                "source_ref": "calendar:US-CA:2026-W22",
                "valid_at": "2026-05-24T12:00:00Z",
            },
        ),
    ]

    return LeaveGuidanceDecision.validate_retrieved(
        items,
        decision_id="leave-guidance-E-810",
        evaluated_at=evaluated_at,
        context={"employee_id": "E-810", "region": "US-CA"},
    )


if __name__ == "__main__":
    result = run()
    print(result.action)
    print(result.schema_confidence.score)
    print(result.to_policy_input())
