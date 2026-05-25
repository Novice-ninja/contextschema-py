# ContextSchema Examples

These examples model common enterprise agent decisions without integrating any
external systems. They use `RetrievedItem` objects as already-retrieved context
and `EventRecord` objects as already-known business events.

The examples intentionally include assumptions in each file. The point is not
to automate the whole workflow; it is to validate whether the context is fresh,
complete, and reliable enough before an agent takes the next action.

| Example | Decision Being Validated | Expected Action |
| --- | --- | --- |
| `customer_service_refund.py` | Can a support agent offer a refund? | `hard_gate` because order status evidence was invalidated. |
| `coding_agent_change.py` | Can a coding agent proceed with a code edit? | `hard_gate` because failing-test evidence was invalidated. |
| `merchandising_super_agent_router.py` | Can one merchandising agent route markdown and transfer decisions to different schemas? | Markdown `hard_gate`; transfer `proceed`. |
| `sales_opportunity_next_step.py` | Can a sales agent recommend the next commercial action? | `hard_gate` because pricing guidance was invalidated. |
| `procurement_vendor_onboarding.py` | Can procurement approve vendor onboarding? | `hard_gate` because sanctions screening was invalidated. |
| `finance_invoice_approval.py` | Can finance approve an invoice for payment? | `hard_gate` because PO-match evidence was invalidated. |
| `hr_employee_policy.py` | Can HR answer an employee leave-policy question? | Usually `soft_flag` because optional approval is missing and evidence has aged. |
| `security_access_review.py` | Can an IAM/security agent approve temporary access? | `hard_gate` because manager approval was updated after retrieval. |

Run all examples from the repository root:

```bash
for file in examples/*.py; do
  echo "$file"
  PYTHONPATH=src python3 "$file"
done
```

Run one example:

```bash
PYTHONPATH=src python3 examples/customer_service_refund.py
PYTHONPATH=src python3 examples/coding_agent_change.py
PYTHONPATH=src python3 examples/merchandising_super_agent_router.py
```

## Customer Service Refund

`customer_service_refund.py` models a support agent deciding whether it can
offer a refund or should stop and refresh order context first.

Assumptions:

- The agent has already retrieved order status, refund policy, customer tier,
  and payment settlement evidence.
- Order status is required and can be invalidated by fulfillment events.
- Policy and customer-tier context can age without necessarily hard-gating the
  action.
- Raw customer/order text should not be stored in the evidence log by default.

Expected result:

```text
Action: hard_gate
```

The example hard-gates because an `order_status_changed` event occurred after
the order-status evidence was retrieved. A real support workflow would use that
result to refresh order status before offering or denying the refund.

## Coding Agent Change

`coding_agent_change.py` models a coding agent deciding whether it can safely
edit code based on retrieved task, repository, ownership, and test evidence.

Assumptions:

- The agent has already retrieved task requirements, target files, ownership
  data, recent test status, and dependency-risk notes.
- Recent test status is required and can be invalidated by CI events.
- Ownership and dependency notes can be stale or optional depending on the
  action policy.
- ContextSchema is not a coding-agent framework; it only validates whether the
  context is reliable enough before the agent changes files or runs tools.

Expected result:

```text
Action: hard_gate
```

The example hard-gates because a `ci_status_changed` event occurred after the
test-status evidence was retrieved. A real coding agent would refresh CI/test
context before proceeding with the code change.

## Merchandising Super-Agent Router

`merchandising_super_agent_router.py` models one agent that can validate
different merchandising decision types with different schemas.

Assumptions:

- Markdown recommendations need sales, price, and margin guardrail context.
- Store-transfer recommendations need source inventory, destination demand, and
  transfer constraints.
- One giant schema would over-gate some decisions and under-gate others.

Expected result:

```text
markdown hard_gate ['margin_guardrail']
store_transfer proceed 1.0
```

The markdown path hard-gates because margin guardrails are missing. The
store-transfer path proceeds because its own decision-specific fields are
present and fresh.
