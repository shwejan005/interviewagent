# Evalia documentation

This is the canonical documentation set for Evalia. It reflects the **actual
current state of the code** in this repository, verified by reading the
source and by running the automated test suite — not the aspirational state
described in the two planning documents at the repository root
([PRODUCTION_ROADMAP.md](../PRODUCTION_ROADMAP.md) and
[CODEBASE_REVIEW.md](../CODEBASE_REVIEW.md)). Where this documentation and
those planning documents disagree, **this documentation is correct for the
present code**, and [GAP_ANALYSIS.md](GAP_ANALYSIS.md) explains the
difference explicitly.

## How to use this documentation

### Current system

| Document | What it covers | Read this if you want to... |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System components, request flow, agent pipeline, bias-isolation design, memory model | Understand how the system is put together and why. |
| [API_REFERENCE.md](API_REFERENCE.md) | Every HTTP endpoint: request/response shapes, status codes, error contracts | Integrate with the API or debug a specific call. |
| [DATA_MODEL.md](DATA_MODEL.md) | Database tables, columns, indexes, constraints, invariants | Understand or modify persistence. |
| [SETUP.md](SETUP.md) | Local dev setup for backend + frontend, environment variables, Windows notes | Get the project running on your machine. |
| [TESTING.md](TESTING.md) | Test suite structure, what is/isn't covered, how to run tests, live-agent testing | Run or extend the automated tests. |
| [SECURITY.md](SECURITY.md) | Current security posture, fixed issues, and known open gaps, mapped to CODEBASE_REVIEW.md findings | Understand what protections exist and what doesn't yet. |
| [GAP_ANALYSIS.md](GAP_ANALYSIS.md) | Task-by-task comparison of PRODUCTION_ROADMAP.md against the actual codebase | See exactly what from the roadmap is done, partially done, or not started, with evidence. |
| [DEPLOYMENT.md](DEPLOYMENT.md) | How the app runs today (dev launcher, Docker, Vercel) and what's missing for real production deployment | Deploy it or evaluate deployment readiness. |
| [CHANGELOG.md](CHANGELOG.md) | Chronological log of every substantive change made to this codebase by an AI coding agent, with the reason for each change | Audit what changed, when, and why. |

### Forward-looking plans (not yet implemented)

| Document | What it covers | Read this if you want to... |
|---|---|---|
| [PRODUCT_BLUEPRINT.md](PRODUCT_BLUEPRINT.md) | The full product Evalia becomes: RBAC & multi-tenancy, recruiter campaigns/ATS, candidate profile vault & one-click apply, matching engine, DSA/dev prep suite with in-browser IDE, gamification, auto-apply agent, admin console, phased delivery plan | Understand the target product and how to get there from here. |
| [AI_INTERVIEW_ARCHITECTURE_PLAN.md](AI_INTERVIEW_ARCHITECTURE_PLAN.md) | Research-grounded architecture and phased plan for application-linked, AI-conducted interviews and recruiter evidence reports | Design and plan the role/campaign/posting-specific interviewer before implementation. |
| [DECISIONS.md](DECISIONS.md) | The 10 architectural/product decisions that block the blueprint's Phase 0, each with options, trade-offs, and a recommendation | Make the calls needed before platform work starts. |
| [UI_REVAMP_PLAN.md](UI_REVAMP_PLAN.md) | Glassmorphism design system, motion system, and a phased plan to migrate 501 inline styles into a real styling layer — including why the current UI structurally cannot animate | Understand the UI/UX direction and migration approach. |
| [../PRODUCTION_ROADMAP.md](../PRODUCTION_ROADMAP.md) | Hardening plan for the *existing* interview pipeline (durable execution, evaluation harness, observability) | Improve the pipeline that exists today. |

> **Relationship between the plans:** `PRODUCTION_ROADMAP.md` makes the current pipeline production-grade. `PRODUCT_BLUEPRINT.md` builds a platform around it. The blueprint's Phase 0 subsumes several roadmap items (notably durable execution and migrations) because they become hard prerequisites rather than improvements.


## Ground rules for this documentation

1. **No unverified claims.** Every statement about current behavior is
   grounded in source code read during this documentation pass, or in a test
   that was actually executed (see [TESTING.md](TESTING.md) for what was run
   and when).
2. **Gaps are stated, not hidden.** Where a roadmap item is not implemented,
   the documentation says so plainly and explains why, rather than omitting
   it or implying partial credit it hasn't earned.
3. **Docs are updated alongside code.** If you change backend or frontend
   behavior, update the relevant doc in the same change, and add an entry to
   [CHANGELOG.md](CHANGELOG.md).
