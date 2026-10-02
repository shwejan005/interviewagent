# Decisions required before Phase 0

Each decision below is **expensive or impossible to reverse later**. They are listed in the order they block work. A recommendation is given for each — the recommendation is a starting position for a discussion, not a substitute for one.

Companion to [PRODUCT_BLUEPRINT.md](PRODUCT_BLUEPRINT.md).

---

## Settled — 2026-09-28

The decision-maker was unavailable, so the four blocking decisions were taken
autonomously to unblock Phase 1. **Each was resolved to the reversible or
lower-risk option**, and each is recorded here with its reversal cost so the
call can be revisited on review.

| ID | Settled as | Rationale | Cost to reverse |
|---|---|---|---|
| **D-01** | Application-layer tenancy now; **RLS deferred** until a real-Postgres test environment exists | The whole test suite runs on SQLite, which has no RLS. Adding it now means shipping *untested* security code and creating false confidence. The schema is RLS-ready (`org_id` on every tenant table), so adding it later is additive. | Low — additive migration plus policy DDL |
| **D-02** | **Keep in-house auth** | Works, is tested, and no enterprise SSO requirement exists yet. Migrating now would pay a real cost for a hypothetical customer. | Medium, and rises with usage. Revisit the moment SSO is actually asked for |
| **D-05** | **Design to the strictest, activate per-market later** | Consent, retention, and bias-audit *capture* are built into the schema now; enforcement is configuration. Retrofitting consent onto data already collected without it is not legally possible. | Low if built now, very high if deferred — hence building now |
| **D-10** | **No automated rejection.** Automated stages produce a recommendation; a human confirms every adverse decision | An automated employment decision is a regulated act in several target markets. Defaulting to human confirmation is slower and is the correct default for a hiring product. Implemented as a per-posting `auto_reject_enabled` flag defaulting to `false`, so an org can opt in deliberately and auditably. | Low — flip a default |

**D-07 (build order)** was settled as **marketplace-first**: campaigns →
postings → applications → tracking. Reasoning: the prep suite is only
valuable to candidates who have jobs to apply to, and the existing agent
pipeline is already the differentiated part of the hiring flow. Marketplace
work also exercises the tenancy model hardest, surfacing foundation problems
early rather than after a second product is built on top.

**D-08** was settled as **preserve and retrofit**, and this is now done — see
the Phase 0 entry in [CHANGELOG.md](CHANGELOG.md).

### One consequence worth flagging

Because D-10 was settled as "no automated rejection", the new application
pipeline does **not** inherit the legacy evaluation behaviour where a FAIL
verdict auto-rejects. The standalone `/start` evaluation flow keeps its
existing behaviour unchanged (it is not attached to a job posting and has no
applicant to notify), but an application moving through an automated stage
lands in `PENDING_REVIEW` with the recommendation attached, not `REJECTED`.
These two flows now differ deliberately.

---



## D-01 · Tenancy isolation model
**Blocks:** every table, every query. **Reversibility:** very low.

| Option | Isolation | Cost | Notes |
|---|---|---|---|
| Shared schema + `org_id` column | App-enforced | Low | Simplest, fastest, most common |
| Shared schema + `org_id` + Postgres RLS | DB-enforced | Medium | Survives an application bug; complicates pooling |
| Schema-per-tenant | Strong | High | Migration pain grows linearly with tenants |
| Database-per-tenant | Strongest | Very high | Only justified by enterprise/regulatory demand |

**Recommendation:** shared schema + `org_id` + RLS. The pooling complexity is real but bounded; a missed tenant check becoming a failed query instead of a data breach is worth it for a product holding candidate PII across competing employers.

**Open question:** does any target customer have a data-residency or physical-isolation requirement? If yes, that forces option 4 for those tenants and should be known now.

---

## D-02 · Authentication provider
**Blocks:** Phase 0 identity work. **Reversibility:** medium (migration is possible but painful).

| Option | Pros | Cons |
|---|---|---|
| Build in-house | Full control, no vendor cost | Security-critical code you now own forever; MFA, OAuth, SSO, account recovery all become your problem |
| Auth0 / Clerk / WorkOS | Fast, secure by default, enterprise SSO included | Per-MAU cost, vendor dependency |
| Supabase Auth / Better Auth | Cheaper, self-hostable | Less enterprise SSO maturity |

**Recommendation:** a managed provider, specifically one with **SAML/OIDC SSO on the roadmap** — enterprise recruiting customers will require SSO, and retrofitting it into a hand-rolled system is a multi-week detour. WorkOS and Clerk are both reasonable; the deciding factor is pricing at projected MAU.

**Constraint to verify:** the provider must support the dual-persona model (one identity, both candidate and org-member roles) without forcing separate accounts.

---

## D-03 · Code execution sandbox
**Blocks:** Phase 3. **Reversibility:** medium. **Risk if wrong:** severe (RCE, crypto-mining, data exfiltration).

Options and trade-offs are detailed in [PRODUCT_BLUEPRINT.md §7.4](PRODUCT_BLUEPRINT.md#74-code-execution--the-highest-risk-component).

**Recommendation:** managed provider or self-hosted Judge0 for DSA; WebContainers for JS/TS dev challenges. Defer custom Firecracker infrastructure until volume justifies the engineering cost.

**Questions to answer:**
- Which languages must be supported at launch? (Each adds judge surface area.)
- Is there budget for per-execution managed cost, or must this be self-hosted from day one?
- Who owns sandbox security review and ongoing patching?

---

## D-04 · Auto-apply scope and legal posture
**Blocks:** Phase 4. **Reversibility:** high technically, low reputationally/legally.

Browser automation against third-party job boards frequently violates their Terms of Service. This is a business risk decision, not an engineering one.

**Recommendation:** ship native + official ATS API adapters as the supported product. Treat browser automation as either (a) explicitly experimental with mandatory user consent and review, or (b) out of scope pending legal review.

**Questions:** Is there appetite for this legal exposure? Is legal review available before Phase 4?

---

## D-05 · Target jurisdictions and compliance obligations
**Blocks:** data model (consent, retention), bias monitoring, go-to-market. **Reversibility:** low.

Automated employment decision tools are regulated. Specifically:

- **NYC Local Law 144** — annual independent bias audit, published results, candidate notification
- **EU AI Act** — employment AI is classified high-risk: conformity assessment, logging, human oversight
- **GDPR / India DPDP** — consent, retention limits, data subject rights, cross-border transfer rules
- **Illinois AIVI Act** — consent and disclosure for AI video interview analysis

**Recommendation:** decide the launch jurisdiction now and design to its strictest applicable requirement. Retention policy, consent capture, and bias-audit data collection must be in the schema from Phase 0 — they cannot be added retroactively to data already collected without consent.

**Questions:** Which markets at launch? Is legal counsel engaged? Is the product positioned as decision-*support* (human decides) or decision-*making* (system decides)? That distinction materially changes regulatory classification and should be an explicit product stance.

---

## D-06 · Resume parsing approach
**Blocks:** Phase 1 onboarding quality. **Reversibility:** high.

| Option | Accuracy | Cost | Notes |
|---|---|---|---|
| LLM-based (reuse existing screening agent) | Good | Per-parse LLM cost | Already have the capability |
| Dedicated API (Affinda, Sovren, RChilli) | Best | Per-parse cost | Purpose-built, handles edge cases |
| Open source (spaCy pipelines) | Fair | Compute only | Significant tuning effort |

**Recommendation:** start with the existing LLM capability — it is already built and good enough to validate the onboarding flow. Revisit if parse quality measurably drives onboarding drop-off.

---

## D-07 · Build order across Phases 1–3
**Blocks:** roadmap sequencing. **Reversibility:** high.

Phases 1 (marketplace), 2 (intelligence), and 3 (prep suite) are each substantial products. With a small team, doing them in parallel produces three half-products.

Three defensible sequences:

- **Marketplace-first** (1→2→3) — fastest to a real two-sided transaction; the prep suite becomes a retention layer added later. *Recommended default.*
- **Prep-first** (3→1→2) — prep suites acquire candidates more cheaply than job boards do; build the candidate base, then bring employers to it. Strong if candidate acquisition is the harder side.
- **Vertical slice** — one narrow role family (e.g. backend engineers) across all three phases. Smallest total scope, sharpest positioning, hardest to expand later.

**Question:** which side of the marketplace is harder to acquire in your market — candidates or employers? That answer should drive this.

---

## D-08 · Existing pipeline: preserve or rebuild
**Blocks:** Phase 0 retrofit effort estimate. **Reversibility:** high.

The current interview pipeline is well-built (strict output validation, bias-isolated committee, per-evaluation verdict storage, 38 passing tests) but was designed for a single anonymous user.

**Recommendation:** preserve and retrofit. The agent logic, validation discipline, and context-isolation design are all sound and worth keeping. What changes is the surrounding context — it becomes one configurable stage inside a larger pipeline, scoped to a tenant and an application, executed as a background job rather than inside an HTTP request.

---

## D-09 · Infrastructure baseline
**Blocks:** Phase 0 deployment. **Reversibility:** medium.

Currently there is no backend deployment definition at all (see [DEPLOYMENT.md](DEPLOYMENT.md)).

**Needs deciding:** cloud provider, container orchestration (ECS/Fargate vs. Kubernetes vs. a PaaS), managed Postgres provider, object storage, secrets management, and observability stack.

**Recommendation:** the simplest thing that supports a background worker and managed Postgres — ECS/Fargate or a PaaS. Avoid Kubernetes until team size and scale genuinely require it. Pick one observability vendor rather than assembling three.

---

## D-10 · The bias question — product stance
**Blocks:** matching engine design, prep-suite integration, compliance posture. **Reversibility:** low.

Two specific, concrete issues that need an explicit answer:

1. **Does prep-suite performance influence candidate ranking?** If yes, the platform is advantaging candidates with more free time and rewarding grinding over competence, and that must be disclosed. If no, verified skills should be presented as human-readable evidence only, never as a scoring input.

2. **Can the system reject a candidate without a human in the loop?** Today, a FAIL verdict auto-rejects. At product scale, in a regulated jurisdiction, that is an automated employment decision with legal consequences.

**Recommendation:** verified skills shown as evidence, weighted conservatively and transparently if used at all; and **no fully automated rejection** — automated stages produce recommendations, a human confirms adverse decisions. This is slower and is the right default for a hiring product.

---

## Summary

| ID | Decision | Blocks | Urgency |
|---|---|---|---|
| D-01 | Tenancy isolation model | Everything | **Now** |
| D-02 | Auth provider | Phase 0 | **Now** |
| D-05 | Jurisdictions & compliance | Schema, bias monitoring | **Now** |
| D-10 | Bias / automation stance | Matching, prep integration | **Now** |
| D-07 | Build order | Roadmap | Before Phase 1 |
| D-08 | Preserve vs. rebuild pipeline | Phase 0 estimate | Before Phase 0 |
| D-09 | Infrastructure baseline | Deployment | Before Phase 0 ships |
| D-06 | Resume parsing | Onboarding quality | Before Phase 1 |
| D-03 | Code execution sandbox | Phase 3 | Before Phase 3 |
| D-04 | Auto-apply legal posture | Phase 4 | Before Phase 4 |

The four marked **Now** are worth settling before any Phase 0 code is written — each one shapes the schema, and schema changes after data exists are the expensive kind.
