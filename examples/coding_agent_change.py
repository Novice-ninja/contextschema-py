"""Coding-agent example: validate context before editing code."""

from datetime import UTC, datetime, timedelta

from contextschema import ActionPolicy, ContextField, ContextSchema, EventRecord, RetrievedItem


class CodeChangeDecision(ContextSchema):
    schema_version = "example-1"
    action_policy = ActionPolicy(
        proceed_at_or_above=0.82,
        retry_below=0.70,
        soft_flag_below=0.82,
        hard_gate_on_event_invalidated_required_field=True,
    )

    task_requirements = ContextField(
        source=["issue_tracker", "user_prompt"],
        ttl=timedelta(hours=4),
        criticality=1.0,
        required=True,
        invalidates_on=["issue_scope_changed"],
    )
    repo_state = ContextField(
        source=["git_status", "workspace_snapshot"],
        ttl=timedelta(minutes=5),
        criticality=1.0,
        required=True,
        invalidates_on=["branch_updated", "files_changed"],
    )
    failing_tests = ContextField(
        source=["test_runner", "ci_status"],
        ttl=timedelta(minutes=15),
        criticality=0.9,
        required=True,
        invalidates_on=["tests_rerun", "ci_completed"],
    )
    dependency_policy = ContextField(
        source=["package_manifest", "security_policy"],
        ttl=timedelta(days=14),
        criticality=0.6,
        required=False,
    )


def run():
    evaluated_at = datetime(2026, 5, 25, 18, 0, tzinfo=UTC)
    items = [
        RetrievedItem(
            id="issue-77",
            text="Fix customer import retry behavior without changing public API.",
            metadata={
                "context_field": "task_requirements",
                "source": "issue_tracker",
                "source_ref": "issue:77",
                "valid_at": "2026-05-25T17:30:00Z",
            },
        ),
        RetrievedItem(
            id="git-1",
            text="Working tree has no unstaged user changes.",
            metadata={
                "context_field": "repo_state",
                "source": "git_status",
                "source_ref": "git:main:abc123",
                "valid_at": "2026-05-25T17:57:00Z",
            },
        ),
        RetrievedItem(
            id="tests-1",
            text="Unit tests failed in customer import retry test.",
            metadata={
                "context_field": "failing_tests",
                "source": "test_runner",
                "source_ref": "pytest:run:991",
                "valid_at": "2026-05-25T17:40:00Z",
            },
        ),
        RetrievedItem(
            id="deps-1",
            text="Do not add runtime dependencies for this fix.",
            metadata={
                "field_hints": ["dependency_policy"],
                "source": "package_manifest",
                "source_ref": "pyproject.toml",
                "last_modified_at": "2026-05-20T10:00:00Z",
            },
        ),
    ]
    events = [
        EventRecord(
            event_id="evt-tests-2",
            event_type="tests_rerun",
            occurred_at=datetime(2026, 5, 25, 17, 50, tzinfo=UTC),
            affected_fields=["failing_tests"],
            affected_sources=["test_runner"],
            source_ref="pytest:run:991",
        )
    ]

    return CodeChangeDecision.validate_retrieved(
        items,
        decision_id="code-change-77",
        events=events,
        evaluated_at=evaluated_at,
        context={"issue_id": "77", "branch": "main"},
    )


if __name__ == "__main__":
    result = run()
    print(result.action)
    print(result.schema_confidence.score)
    print(result.to_policy_input())
