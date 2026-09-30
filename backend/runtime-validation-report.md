# Runtime Validation Report

**Generated**: 2026-09-30
**Target**: `backend/`

## Summary

| Step | Status | Exit Code | Details |
|------|--------|-----------|---------|
| Compilation/import | PASS | 0 | `compileall` succeeded; `import main` succeeded after legacy deletion |
| Backend integration | PASS | 0 | 249 pytest tests passed using isolated SQLite databases |
| Runtime journeys | PASS | 0 | Resume parse/import/read-back, recruiter criteria/report/read-back, and full interview pipeline persistence |
| Startup/readiness | PASS | 0 | Uvicorn started on `127.0.0.1:8011`; `/healthz` returned 200 |
| Live HTTP smoke | PASS | 0 | Registration, `/auth/me`, profile write, and profile read-back succeeded |
| Frontend typecheck | PASS | 0 | `npm run typecheck` succeeded after adding resume import and criteria/report UI |
| Browser E2E | PASS | 0 | 4 Playwright tests passed, including resume review/save and criteria edit/save journeys |

**Overall**: PASS for the reorganized backend and local SQLite runtime.

## Environment

- Docker CLI: installed, but `docker info` reported that the daemon was unavailable.
- Infrastructure tier: fallback SQLite, using the preserved `backend/evalia.db` path.
- Node.js: available (`v22.14.0`).
- Playwright: Chromium provisioning succeeded; browser tests passed.
- Live external LLM: not exercised. Tests use deterministic fakes or the resume parser's fallback because no live provider was configured.
- Resume upload UI: upload -> parse -> editable review -> explicit profile save is covered with a mocked browser API journey; the backend parse/import contract is covered with live TestClient flows.
- Recruiter criteria/report UI: criteria load -> weighted edit -> save is covered with a mocked browser API journey; report generation/read-back is covered with live TestClient flows.

## Package Deletion Verification

The old flat compatibility modules were removed after all imports were migrated to `backend/app` packages. The backend root now retains only the application entry point and demo seeder as Python modules. A repository-wide backend import scan found no direct imports of the deleted module names.

Canonical packages now include:

- `app/auth`, `app/admin`
- `app/candidate`, `app/hiring`
- `app/resume`, `app/interview_criteria`
- `app/evaluation`, `app/prep`, `app/review`
- `app/config`, `app/shared`, `app/worker`

## Known Gaps

- PostgreSQL/RLS validation was not run because the Docker daemon was unavailable. The existing PostgreSQL verification script remains available for an environment with a live `DATABASE_URL`.
- Playwright coverage validates the frontend with mocked API responses; the live backend API journeys are covered separately by the three runtime-validation pytest flows and the Uvicorn HTTP smoke.
- `get_errors` still reports pre-existing Sonar-style maintainability findings in moved modules, including complexity, duplicated literals, and type-hint suggestions. These did not prevent compilation, import, startup, or any test from passing and were outside the organization/deletion change.
- Pytest and CrewAI emit deprecation warnings; they do not affect the passing exit codes.
