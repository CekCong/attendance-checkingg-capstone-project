# Migration on hongyu

The implementation is being migrated in independently verified stages. Passing
HTTP contract tests alone does not establish end-to-end attendance or spoof resistance.

## 1. Database-backed reporting and route ownership

Implemented:
- Remove legacy routers that shadow statistics and attendance exports.
- Aggregate audit summaries from persisted events.
- Remove the mock instructor dashboard endpoint and sample-data dependency.
- Remove duplicate device-list registration while retaining the active handler.
- Cover empty reports, unknown sessions, course authorization, and audit counts.

Validation: reporting regressions, API functional tests, observability tests,
frontend/dashboard HTTP contracts, and frontend TypeScript checking.
Production builds currently require Google Fonts network access that the cloud
runtime denies. Browser interaction testing remains outstanding.

## 2. Authentication and deployment

- Route login, refresh, and logout through the backend authority.
- Separate internal Docker service addresses from browser API addresses.
- Verify expiry, refresh, disabled users, logout auditing, and container startup.
- Restore the required rate limits with isolated test configuration.

## 3. Real student attendance workflow

- Replace local mock success and seeded history with backend records.
- Integrate registration, consent persistence, face enrollment, camera capture,
  geolocation, session selection, and device registration.
- Submit fresh server-issued liveness/device challenges and display actual
  approved, flagged, or rejected outcomes.
- Verify the complete workflow in a browser, including permission denial.

## 4. Security and privacy

- Enforce challenge freshness and service-failure behavior consistently.
- Implement impossible-travel checks and test network lookup failures.
- Add account deletion scheduling and personal-data cleanup.
- Limit stored location precision and remove precise coordinates from logs.
- Enforce audit immutability with appropriate database permissions; review
  instructor access to audit records.

## 5. Dashboard completeness and release validation

- Verify pagination, report completeness, scope, and audited exports.
- Add offline app-shell caching without caching authentication or submissions.
- Verify mobile behavior, monitoring, Docker deployment, and the full public suite.
- Evaluate real face/attack samples and concurrent workloads separately from
  endpoint contract tests; record any remaining limitations.
