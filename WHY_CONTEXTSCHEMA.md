# Why ContextSchema

ContextSchema is not only a runtime validation library. It is also a design
discipline for agent teams.

Most agent systems are designed against the happy path: the prompt, harness, or
workflow assumes the agent receives enough clean, current context to reason
well. In production, the harder failure is often earlier than reasoning. The
agent may receive only part of the commercial, operational, technical, or
policy picture, then produce a confident recommendation as if the full picture
was known.

ContextSchema helps teams make those context assumptions explicit. That is
broader than asking "do we have enough context?" A useful context contract also
asks whether the context is from the right source, relevant to the decision,
fresh enough, not invalidated by later events, and traceable enough to review.

It asks product managers and engineers to declare:

- What context is required for this decision?
- Which context is expected but not strictly required?
- What makes retrieved context relevant to each field?
- Which sources are acceptable?
- Which source references or provenance records are needed?
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

ContextSchema lets the team define a decision-specific context validity
contract.

Validity has several parts:

| Validity Dimension | Question It Forces |
| --- | --- |
| Sufficiency | Do we have the fields needed for this decision? |
| Relevance | Does each retrieved item actually map to the decision field it claims to support? |
| Provenance | Do we know the source and source reference behind the evidence? |
| Timeliness | Is the evidence fresh enough for this decision type? |
| Invalidation | Did a later business or system event make the evidence unusable? |
| Source reliability | Is this source trusted enough for this field? |
| Action policy | Should the agent proceed, qualify, retry, or stop? |

For a merchandising recommendation, the contract might say:

| Context Field | Required? | Source / Provenance | Freshness / Validity Rule | Why It Matters |
| --- | --- | --- | --- | --- |
| Recent sales trend | Required | Sales mart, report ID, snapshot timestamp | Fresh for the latest selling period | Defines the observed performance issue. |
| Current inventory position | Required | Inventory service, location/SKU ref | Fresh enough for replenishment/allocation decisions | Separates demand issues from availability issues. |
| Stockout or lost-sales signal | Required for root-cause claims | Availability/lost-sales model, SKU/store ref | Must match the same period as sales | Prevents interpreting suppressed availability as low demand. |
| Current price | Required | Pricing service, pricebook ref | Current price must be effective for the decision window | Needed before recommending price action. |
| Promotion status | Required | Promo calendar, promo ID | Current and upcoming promo windows must be clear | Promo changes can explain sales and margin movement. |
| Inbound supply status | Expected or required for allocation decisions | PO/supply-chain system, PO ref | Must include relevant open or delayed supply events | Prevents recommending actions that supply cannot support. |
| Competitor price signal | Expected | Competitive intelligence source, competitor/SKU ref | Must be recent enough to support price comparison | Missing competitor context should qualify pricing recommendations. |
| Margin guardrail | Required for markdown recommendations | Finance or pricing policy source, rule ref | Must be current policy | Prevents commercially invalid recommendations. |
| Known exception events | Expected | Exception/event log, event ID | Events after retrieval can invalidate evidence | Captures data outages, store closures, weather, or operational disruptions. |

Then the agent can produce a calibrated outcome:

| Context State | Better Agent Behavior |
| --- | --- |
| Required fields present and fresh | Make the recommendation. |
| Retrieved item has no source reference | Lower confidence or retry with provenance-preserving retrieval. |
| Retrieved item is topically related but not field-relevant | Do not treat it as satisfying the field. |
| Competitor price missing | Give a qualified recommendation and disclose the missing context. |
| Inventory snapshot stale | Retry or refresh before recommending allocation or replenishment. |
| Margin guardrail missing | Do not recommend markdown depth; ask for margin context. |
| Stockout signal missing | Do not make a strong root-cause claim about demand. |
| Exception event after retrieval | Hard gate or refresh the affected context. |

This turns the agent from "confident by default" into "confident when the
declared decision context supports confidence."

## Metadata Is Part Of The Contract

ContextSchema works best when retrieval preserves metadata. The framework can
only validate provenance, relevance, and timeliness if the retrieved context
keeps enough evidence about where it came from and when it was valid.

At minimum, retrieved items should try to include:

| Metadata | Purpose |
| --- | --- |
| `context_field` or `field_hints` | Says which decision field the item is intended to satisfy. |
| `source` | Identifies the upstream system, document class, or service. |
| `source_ref` or `provenance_ref` | Points back to the record, document, query, report, or snapshot. |
| `valid_at`, `last_modified_at`, `loaded_at`, or `retrieved_at` | Lets the schema judge freshness and event ordering. |
| `source_reliability` | Lets lower-trust sources reduce confidence. |

This has an architectural implication: retrieval should not flatten everything
into plain text. If a retriever returns a paragraph without source, timestamp,
or field mapping, the model may still use it, but the system cannot reliably
decide whether that context is current, relevant, or auditable.

For merchandising, that means a sales summary should not just say "sales are
down." It should carry the sales source, SKU/store/category scope, snapshot
time, period covered, and report or query reference. A competitor price signal
should carry the source and observation time. A supply-chain note should carry
the PO, shipment, vendor, or exception reference.

The design target is not "more context." It is context with enough metadata to
be judged.

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
- require source refs and timestamps for sales, inventory, pricing, promo, and
  supply-chain evidence
- distinguish relevant context from merely adjacent context
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
around context validity boundaries.

For each agent decision, the team can ask:

| Design Question | Why It Matters |
| --- | --- |
| What is the decision type? | Different decisions need different context contracts. |
| What fields are required? | Avoids treating nice-to-have context as enough for action. |
| What fields are expected but optional? | Allows useful qualified answers instead of blanket refusal. |
| What makes retrieved context relevant to a field? | Prevents adjacent facts from being treated as decision evidence. |
| Which sources and source refs are acceptable? | Makes provenance reviewable instead of hidden inside prompt text. |
| What makes a field stale? | Makes freshness explicit instead of relying on prompt caution. |
| What events invalidate context? | Handles reality changing after retrieval. |
| What action is safe under missing context? | Separates proceed, qualify, retry, and hard stop. |
| What evidence must be logged? | Makes behavior reviewable and debuggable. |

This is especially useful for PM and engineering alignment. A PM can define
what "enough context" means for a business decision. An engineer can encode it
as fields, relevance hints, TTLs, sources, source refs, invalidation events,
and action policy.

## Why Not Just Put This In The Prompt?

This is a fair concern. Some of the ContextSchema discipline can and should
influence prompts. A good system prompt can tell an agent to mention missing
context, avoid overclaiming, cite sources, and ask for refreshes.

For low-risk use cases, that may be enough.

But prompts are a weak place to enforce context validity when decisions are
consequential.

| Prompt-Only Instruction | ContextSchema Contract |
| --- | --- |
| The model is asked to notice missing context. | Required and optional fields are declared outside the model. |
| The model decides whether a source seems reliable. | Accepted sources and reliability thresholds are explicit. |
| The model is told to be careful about stale data. | TTLs and evidence timestamps are scored deterministically. |
| The model may or may not notice invalidation events. | Events after retrieval can mechanically reduce confidence or hard-gate. |
| Missing evidence appears in prose if the model remembers to mention it. | Missing, stale, weak, or invalid context appears in structured reasons. |
| Behavior can vary across models, prompts, and temperature. | The validation step is repeatable and testable. |
| It is hard to audit why the agent proceeded. | Evidence records can be logged without storing raw text by default. |

So the right framing is not "prompt or ContextSchema." The better pattern is:

```text
ContextSchema determines context validity.
The prompt teaches the agent how to communicate and act on that validity.
```

For example, the prompt can say:

> If ContextSchema returns `soft_flag`, provide a qualified recommendation and
> name the missing or weak fields. If it returns `retry_recommended`, refresh
> the specified fields before recommending. If it returns `hard_gate`, do not
> make the prescriptive recommendation.

That is stronger than asking the model to infer all of this from raw context.
The prompt handles expression and workflow. The schema handles the contract.

## What This Does Not Guarantee

ContextSchema does not guarantee the agent's final recommendation is correct.

Complete context can still be misinterpreted. Business rules can still be
wrong. Retrieval can still miss documents. The model can still reason poorly.

ContextSchema addresses a narrower failure:

> The agent should not silently act as if its context is sufficient, relevant,
> traceable, current, and decision-valid when the declared context contract says
> otherwise.

That makes the system more honest. It also creates a better place to connect
retrieval, policy, observability, and evaluation later.

## How To Evaluate Whether You Need It

You probably need this abstraction if your agent:

- makes recommendations that depend on multiple data domains
- acts on data that changes over time
- can be wrong because a missing field changes the recommended action
- needs provenance, source refs, or timestamps preserved through retrieval
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
with these provenance records,
relevant to these fields,
fresh within these bounds,
not invalidated by these events,
otherwise the agent must qualify, retry, or stop.
```

That contract is the point. The Python library is the current implementation of
that contract.
