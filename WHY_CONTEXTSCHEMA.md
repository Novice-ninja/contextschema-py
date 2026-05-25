# Why ContextSchema

ContextSchema is not only a runtime validation library. It is also a design
discipline for agent teams.

Most agent systems are designed against the happy path: the prompt, harness, or
workflow assumes the agent receives enough clean, current context to reason
well. In production, the harder failure is often earlier than reasoning. The
agent may receive only part of the commercial, operational, technical, or
policy picture, then produce a confident recommendation as if the full picture
was known.

ContextSchema helps teams make those context assumptions explicit.

It asks product managers and engineers to declare:

- What context is required for this decision?
- Which context is expected but not strictly required?
- Which sources are acceptable?
- How fresh does each field need to be?
- What events invalidate previously retrieved evidence?
- What should the agent do when context is missing, stale, ambiguous, or weakly
  sourced?
- What evidence should be logged so the recommendation can be reviewed later?

The goal is not to make every agent refuse to answer. The goal is to prevent
silent overconfidence.

## The Failure Mode

An agent can sound most confident when the system gives it a polished but
partial context bundle.

For example, a merchandising analyst agent may receive:

- recent sales
- current inventory
- current price
- promotion calendar
- product hierarchy

But it may not have:

- inbound supply or purchase-order status
- allocation constraints
- competitor pricing
- vendor funding
- margin guardrails
- weather or local events
- known data outages
- stockout or lost-sales flags
- assortment changes
- traffic, search, or conversion data

The agent can still write a fluent recommendation:

> Sales are declining while inventory remains available. Consider a markdown or
> promotion to stimulate demand.

That may be reasonable if price and demand are the main drivers. It may be
wrong if the missing context shows a competitor markdown, hidden stockout,
supply interruption, allocation issue, or upcoming vendor-funded promotion.

The problem is not just hallucination. The problem is false analytical
completeness: a recommendation framed as if the decision space was fully
examined, even though the agent only saw a slice of the context.

## What ContextSchema Changes

ContextSchema lets the team define a decision-specific context sufficiency
contract.

For a merchandising recommendation, the contract might say:

| Context Field | Required? | Why It Matters |
| --- | --- | --- |
| Recent sales trend | Required | Defines the observed performance issue. |
| Current inventory position | Required | Separates demand issues from availability issues. |
| Stockout or lost-sales signal | Required for root-cause claims | Prevents interpreting suppressed availability as low demand. |
| Current price | Required | Needed before recommending price action. |
| Promotion status | Required | Promo changes can explain sales and margin movement. |
| Inbound supply status | Expected or required for allocation decisions | Prevents recommending actions that supply cannot support. |
| Competitor price signal | Expected | Missing competitor context should qualify pricing recommendations. |
| Margin guardrail | Required for markdown recommendations | Prevents commercially invalid recommendations. |
| Known exception events | Expected | Captures data outages, store closures, weather, or operational disruptions. |
| Data freshness timestamp | Required | Prevents recommendations from stale snapshots. |

Then the agent can produce a calibrated outcome:

| Context State | Better Agent Behavior |
| --- | --- |
| Required fields present and fresh | Make the recommendation. |
| Competitor price missing | Give a qualified recommendation and disclose the missing context. |
| Inventory snapshot stale | Retry or refresh before recommending allocation or replenishment. |
| Margin guardrail missing | Do not recommend markdown depth; ask for margin context. |
| Stockout signal missing | Do not make a strong root-cause claim about demand. |
| Exception event after retrieval | Hard gate or refresh the affected context. |

This turns the agent from "confident by default" into "confident when the
declared decision context supports confidence."

## Domain Examples

### Retail Merchandising

Decision: recommend what to do about a SKU, category, store, or channel
performance issue.

Common partial context:

- sales and inventory are present
- price and promo are partially present
- supply chain, competitor pricing, exceptions, or margin are missing

Risk:

- the agent recommends markdown, replenishment, allocation, or root cause using
  only the visible slice of data
- the response sounds like a complete commercial diagnosis

How ContextSchema helps:

- declare which data domains are required for a full recommendation
- mark competitor or supply-chain gaps as confidence reducers
- prevent root-cause certainty when causal context is incomplete
- route the agent to refresh, qualify, or hard-stop depending on the missing
  fields

### Customer Service

Decision: approve, deny, or escalate a refund.

Common partial context:

- order history and customer tier are present
- latest fulfillment, return, chargeback, or policy state may be stale

Risk:

- the agent offers a refund after the order status changed
- the agent denies a refund using old policy evidence

How ContextSchema helps:

- require current order status and refund policy
- invalidate evidence after fulfillment or return events
- hard-gate high-risk actions when required context changed after retrieval

### Coding Agents

Decision: edit code, apply a patch, or proceed with a risky change.

Common partial context:

- task description and file snippets are present
- latest CI status, ownership, dependency risk, or branch state may be stale

Risk:

- the agent edits code based on an old failing-test picture
- the agent changes owned code without enough repository context

How ContextSchema helps:

- require fresh CI or test context for high-risk edits
- invalidate test evidence after new CI events
- soft-flag missing ownership or dependency context

### Finance And Procurement

Decision: approve invoice payment or vendor onboarding.

Common partial context:

- invoice, vendor, or purchase-order data is present
- sanctions screening, PO match, bank validation, or approval status may be
  missing or stale

Risk:

- the agent recommends payment or onboarding while compliance context is
  incomplete

How ContextSchema helps:

- require compliance-sensitive fields
- hard-gate on stale screening or missing approval evidence
- produce an evidence record for audit review

### Security And Access Review

Decision: grant, extend, or revoke access.

Common partial context:

- request details and user role are present
- manager approval, ticket status, risk classification, or incident context may
  be missing

Risk:

- the agent grants access from incomplete or outdated approval context

How ContextSchema helps:

- require approval and risk context for privileged actions
- invalidate approvals after ticket or incident events
- recommend retry or hard gate instead of silently proceeding

## Design-Time Value

ContextSchema is useful before any code runs because it forces a design review
around context boundaries.

For each agent decision, the team can ask:

| Design Question | Why It Matters |
| --- | --- |
| What is the decision type? | Different decisions need different context contracts. |
| What fields are required? | Avoids treating nice-to-have context as enough for action. |
| What fields are expected but optional? | Allows useful qualified answers instead of blanket refusal. |
| What makes a field stale? | Makes freshness explicit instead of relying on prompt caution. |
| What events invalidate context? | Handles reality changing after retrieval. |
| What action is safe under missing context? | Separates proceed, qualify, retry, and hard stop. |
| What evidence must be logged? | Makes behavior reviewable and debuggable. |

This is especially useful for PM and engineering alignment. A PM can define
what "enough context" means for a business decision. An engineer can encode it
as fields, TTLs, sources, invalidation events, and action policy.

## What This Does Not Guarantee

ContextSchema does not guarantee the agent's final recommendation is correct.

Complete context can still be misinterpreted. Business rules can still be
wrong. Retrieval can still miss documents. The model can still reason poorly.

ContextSchema addresses a narrower failure:

> The agent should not silently act as if its context is complete, current, and
> decision-valid when the declared context contract says otherwise.

That makes the system more honest. It also creates a better place to connect
retrieval, policy, observability, and evaluation later.

## How To Evaluate Whether You Need It

You probably need this abstraction if your agent:

- makes recommendations that depend on multiple data domains
- acts on data that changes over time
- can be wrong because a missing field changes the recommended action
- needs to explain why it proceeded, retried, qualified, or stopped
- currently relies on system-prompt language like "be careful if context is
  incomplete"

You may not need it if your agent:

- only summarizes static documents
- has no meaningful action or recommendation risk
- already receives a fully validated decision object from another system
- does not need auditable context sufficiency reasons

## The Core Abstraction

ContextSchema is best understood as a small contract:

```text
For this decision,
these fields are required,
from these sources,
fresh within these bounds,
not invalidated by these events,
otherwise the agent must qualify, retry, or stop.
```

That contract is the point. The Python library is the current implementation of
that contract.
