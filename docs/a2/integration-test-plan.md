# Student Awards Integration Test Plan

**COMP3613 Assignment 2 | Version 1.1 | Status: Planning only - not executed**

This plan addresses the Assignment 2 requirement to cover main application functionality with integration tests implemented later in pytest. It follows the case-block style and Pre-conditions, Test Steps, Test Criteria and Success terminology of the approved [UAT plan](uat-plan.md) and [Unit Test Plan](unit-test-plan.md). There are **20 planned cases**. Parameterized variants are separate invocations under the same plan ID. All results remain blank.

## Scope and integration boundary

Exercise real FastAPI handlers, authentication/session dependencies, services, repositories, SQLModel tables and SQLite persistence together. Future pytest tests will use FastAPI's in-process `TestClient` and real test-database sessions; no running development server or external network is required. Do not mock business rules, repositories or authorization, or substitute an always-authenticated dependency. This differs from the unit plan's isolated service logic and mocked repositories.

The application currently exposes HTML/form workflows, not domain JSON APIs. Submit form-encoded data. Inspect redirects with automatic redirect following disabled, then explicitly GET the Location to check flash messages and rendered results. Successful form actions normally return **303**, not JSON/201. Typed form-validation failures normally return **422**; caught service `ValueError` failures return **303** plus feedback. Read database state in a new session after each action to verify committed changes rather than a cached object.

## Database isolation, startup and repeatability

1. Before pytest collection or any application/security-module import, select `ENV=test` in a fresh process. Load `.env.test`, falling back only to `.env.test.example`. Do not use development credentials or the development server. Clear incompatible inherited overrides; never bypass the profile guard by selecting production.
2. Before connection, client startup or cleanup, require effective mode `test`, SQLite backend and the resolved target **`comp3613a2/a2_test.db`**. Verify the actual application engine points there. Reject development/remote targets and stop if isolation cannot be established. Do not log secrets or connection credentials.
3. Use `TestClient(app)` as a context manager so lifespan startup runs. `app.main.lifespan`, recovery middleware, `app.database.get_session` and CLI-session helpers all reach the configured engine. The imported engine reference in `app.routers.server_config` must also be the test engine. A request dependency override alone is insufficient. If modules already hold a development engine, abort and restart the pytest process with the test profile.
4. Plan function-scoped setup/teardown against this dedicated disposable test schema only. Reset test tables/rows with foreign-key-safe cleanup after the target guard; never reset another database or use `manage.py init` to provision test data. For IT-1.1 start with an empty test schema so lifespan must create the tables. For other cases, fixtures create the schema and insert only that case's baseline records.
5. Every case and parameter variant owns its users, activities, Awards and requests; capture generated IDs instead of relying on fixed IDs or earlier cases. Use real password hashes, fixture-held dummy passwords and separate cookie jars for each actor. Close clients/sessions and release connections in teardown, including after failures. Run serially: the current configuration has one fixed test file, so parallel workers must not share it.
6. Application repositories commit internally; a simple outer-session rollback is not sufficient cleanup. Verify teardown/reset removes each case's committed data. Any schema-recovery retry must remain confined to the same test engine.

**Common fixture data:** student **A** and student **B** have role `regular_user`; administrator **M** has role `admin`. Use unique usernames/emails per case, with no demo accounts assumed. Unless varied, activity data is `Beach Cleanup`, `Campus Volunteers`, date `2026-10-20`, hours `4`, supporting information `Fixture activity`. Award **V** is active, requires `10` hours and has quantity `2`. Hours and thresholds use `Decimal`. Each case states its own approved totals and states; preparation may insert real fixture rows directly into the test database, but the action under test uses the listed HTTP routes.

## Implementation references and known limits

- [Configuration](../../app/config.py), [database/engine](../../app/database.py) and [application lifespan/error handlers](../../app/main.py).
- [Registration](../../app/routers/register.py), [login](../../app/routers/login.py), [logout](../../app/routers/logout.py), [authorization](../../app/dependencies/auth.py) and [token utilities](../../app/utilities/security.py).
- [Hour submission](../../app/routers/volunteer_submissions.py), [administrator review/processing](../../app/routers/admin_reviews.py), [progress](../../app/routers/progress.py), [student Awards](../../app/routers/awards.py) and [Award management](../../app/routers/admin_awards.py), using their real services/repositories.

**Known HTTP issue:** `AdminDep` raises 401 rather than 403 for a signed-in nonadministrator, and the global 401 handler renders `401.html` without an explicit error status, currently implying HTTP 200. Access-control criteria below require denied content/actions and unchanged database state; capture the status as a known defect, not evidence of successful authorization. Do not silently claim correct 401/403 behavior. Application fixes or revised HTTP-contract assertions require a later decision.

SQLite results establish behavior only for this SQLite configuration. They do not establish PostgreSQL numeric precision, locking, isolation, concurrent duplicate prevention or atomic stock updates under competing requests. Those guarantees require separately authorized PostgreSQL integration testing; no such connection is part of this plan.

Keep combined journeys as short scenario tests or named parameter variants, with fresh fixtures for every invocation. The full arithmetic/validation boundary sweeps remain in the unit plan; integration uses representative values plus committed-state, HTTP and ownership assertions. Use the listed combinations rather than every possible input cross-product. Label every variant so a failure identifies its scenario.

## 1. Startup and isolated database baseline

### IT-1.1 Test Lifespan Initialization and Relational Baseline

**Purpose and components:** Verify configuration, lifespan and SQLite schema/connection settings work together.

**Pre-conditions and test data:** Confirmed test engine; empty disposable test schema; no fixture users yet.

**Test Steps:** 1) Enter the client context. 2) Inspect created table names and `PRAGMA foreign_keys` through a real test connection. 3) GET `/health`. 4) Attempt a validly shaped submission referencing a nonexistent user in a separate test transaction; roll back its expected constraint error.

**Test Criteria (expected results):** All five domain tables exist; foreign-key enforcement is 1; health returns 200 with `{"ok":true}`. Orphan insertion raises a database integrity error and leaves no row. Startup/recovery/session paths use only the guarded test engine; the health response alone is not proof of database readiness.

**Database / HTTP interactions:** SQLite DDL/metadata, foreign-key enforcement, rejected INSERT and rollback; GET `/health`.

**Test Type:** Integration - lifecycle, HTTP and real database.

**Success:** Pass [ ] | Fail [ ]

## 2. Registration, authentication and authorization

### IT-2.1 Test Registration Persistence and Student Role

**Purpose and components:** Join registration handler, auth service, user repository and password hashing.

**Pre-conditions and test data:** No matching user; valid unique username/email and a fixture password. Include an extra submitted `role=admin` field.

**Test Steps:** 1) POST `/register`. 2) GET the redirect destination. 3) Read the new user in an independent session.

**Test Criteria (expected results):** 303 to `/login` with `Registration completed! Sign in now!`; exactly one user persists. Password is hashed and verifies against the fixture password; stored role is `regular_user`, ignoring attempted role escalation. Registration does not issue an authenticated access-token cookie.

**Database / HTTP interactions:** Form registration, flash-session cookie and user INSERT/SELECT; no authentication bypass.

**Test Type:** Integration - HTTP, hashing and persistence.

**Success:** Pass [ ] | Fail [ ]

### IT-2.2 Test Duplicate or Invalid Registration

**Purpose and components:** Exercise registration validation, database uniqueness and error handling.

**Pre-conditions and test data:** Existing user; independent variants duplicate its username, duplicate its email, or supply an invalid email with otherwise-new data.

**Test Steps:** 1) POST `/register` with the variant. 2) GET the redirect destination and inspect users through a fresh session.

**Test Criteria (expected results):** 303 to `/register`, generic current registration-error feedback, and no added/altered user. Duplicate attempts preserve the original password/role. Invalid-email feedback is currently generic rather than a dedicated email-validation message.

**Database / HTTP interactions:** User lookup/attempted INSERT, constraint rollback where applicable and post-request SELECT; registration requests.

**Test Type:** Integration - validation/persistence failure paths.

**Success:** Pass [ ] | Fail [ ]

### IT-2.3 Test Valid and Invalid Login

**Purpose and components:** Verify password checks, JWT cookie issuance and role-specific routing.

**Pre-conditions and test data:** Real A/M users; independent variants valid student, valid administrator, incorrect password and unknown username. Each starts with a fresh client.

**Test Steps:** 1) POST `/login`. 2) Follow its Location. 3) For successful variants, request the corresponding protected dashboard.

**Test Criteria (expected results):** Valid A/M logins redirect to `/app` or `/admin`, set the access-token cookie and show the matching dashboard identity. Invalid credentials redirect to `/login` with error feedback and no access-token issuance. Local test cookies have HttpOnly and SameSite=Lax settings; user records remain unchanged.

**Database / HTTP interactions:** User SELECT, password verification and real cookie-authenticated dashboard reads.

**Test Type:** Integration - authentication and HTTP/database dependencies.

**Success:** Pass [ ] | Fail [ ]

### IT-2.4 Test Logout and Unauthenticated Requests

**Purpose and components:** Exercise cookie removal, token validation and protected-route dependencies.

**Pre-conditions and test data:** A exists; separate variants use no cookie, a tampered token, an already-expired test-signed token, or A's client after real logout. Use test-only secrets without recording tokens.

**Test Steps:** 1) For the logout variant, log in and GET `/logout`. 2) Attempt GET `/app/hours` and POST `/app/hours` with otherwise-valid data.

**Test Criteria (expected results):** Logout redirects to `/login` and removes the cookie. Every variant denies protected content/action and creates no submission. Record the known unauthorized-status issue described above; do not infer permission from HTTP 200 alone.

**Database / HTTP interactions:** Cookie/JWT verification and denied read/write requests; fresh-session count comparison.

**Test Type:** Integration - authentication failures through real dependencies.

**Success:** Pass [ ] | Fail [ ]

### IT-2.5 Test Student Denial of Administrator Operations

**Purpose and components:** Verify `AdminDep` protects both views and mutations.

**Pre-conditions and test data:** Authenticated A; B has one pending submission and redemption; V exists. Snapshot their records.

**Test Steps:** 1) GET `/admin`, `/admin/approvals`, `/admin/awards`. 2) POST valid-looking forms to create/edit Awards, review B's submission and process B's redemption using their real IDs.

**Test Criteria (expected results):** Administrator content and actions are denied; no private review data is exposed, no Award is added/changed, no decision metadata changes and stock is untouched. Capture the known status defect separately.

**Database / HTTP interactions:** All existing administrator GET/POST route families with A's real cookie; before/after SELECT snapshots.

**Test Type:** Integration - route authorization and write prevention.

**Success:** Pass [ ] | Fail [ ]

## 3. Volunteer submissions and administrator review

### IT-3.1 Test Submission, Persistence and Administrator Review

**Purpose and components:** Join form parsing, submission/review services, repositories and both actor views.

**Pre-conditions and test data:** Real A/M sessions; A starts with no submissions. Independent (hours, decision) variants: (4, approved), (4.5, approved), (4.5, rejected). Use padded text and include a blank optional supporting-information variant.

**Test Steps:** 1) As A, POST `/app/hours`; follow the redirect and reload history. 2) Read the committed row in a fresh session and inspect its details in M's Approvals. 3) POST its review decision; reload both views and query fresh state.

**Test Criteria (expected results):** Submission returns 303/success and persists one A-owned Pending row with normalized data, correct hours/date, timestamp and null review metadata. History survives reload and formats 4/4.5 cleanly. Review returns 303/feedback, persists M/time and the chosen status, removes the pending row and updates A's history. Verified hours equal submitted hours only when approved; otherwise 0.

**Database / HTTP interactions:** Hour POST/INSERT, separate history/queue SELECTs, review POST/UPDATE and approved-total reads.

**Test Type:** Integration - independent request-to-review persistence journeys.

**Success:** Pass [ ] | Fail [ ]

### IT-3.2 Test Submission Parsing and Validation Failures

**Purpose and components:** Distinguish HTTP parsing failures from service validation and prevent writes.

**Pre-conditions and test data:** Authenticated A; snapshot submission count. Independent variants omit one representative required field, use malformed date/nonnumeric hours, whitespace activity/organization, or hours `0`/`-0.25`.

**Test Steps:** 1) POST the variant to `/app/hours`. 2) Inspect the immediate response, follow only redirects, and query submissions.

**Test Criteria (expected results):** Missing/malformed typed fields produce 422; service-invalid values produce 303 with validation feedback. No variant inserts a row or alters existing data. HTTP tests do not assume browser quarter-hour restrictions are server rules.

**Database / HTTP interactions:** Form binding, service rejection and no-write verification via SELECT.

**Test Type:** Integration - HTTP/schema/service validation boundaries.

**Success:** Pass [ ] | Fail [ ]

### IT-3.3 Test Invalid or Repeated Submission Review

**Purpose and components:** Prevent invalid review requests from changing persisted decisions.

**Pre-conditions and test data:** M signed in; independent variants use a nonexistent integer submission ID, a pending row with an invalid decision, or an approved/rejected row receiving a second decision.

**Test Steps:** 1) POST the review route. 2) GET the redirect and compare database snapshots.

**Test Criteria (expected results):** 303 with appropriate missing-row, decision or pending-only feedback. No row, hours, reviewer or timestamp changes; no replacement record appears.

**Database / HTTP interactions:** Existing review endpoint with real lookup/state guards; post-request SELECT.

**Test Type:** Integration - persisted invalid-operation prevention.

**Success:** Pass [ ] | Fail [ ]

## 4. Approved progress, milestones and leaderboard

### IT-4.1 Test Approved Totals and Milestone Output

**Purpose and components:** Verify real aggregate queries feed progress, milestones and Award eligibility consistently.

**Pre-conditions and test data:** A has approved 4 and 0.5, pending 8, rejected 6; B has approved 20. Milestones have thresholds 4.5 and 10, inserted in reverse order. Independent variants give A no approved rows or provide no milestones.

**Test Steps:** 1) Read `VolunteerSubmissionService.verified_hours` and `AwardRepository.verified_hours` using real sessions. 2) GET A's `/app/progress` and `/app/awards`; compare totals and milestone context/rendering.

**Test Criteria (expected results):** All A totals are 4.5, or 0 with no approved rows; pending/rejected/B-owned hours are excluded. Milestones sort by threshold: at 4.5, the first is Complete/100% and the second incomplete/45%; at 0, both are incomplete/0%. Empty milestones render their empty state. Full below/at/above/cap arithmetic is covered by UT-2.3, not repeated here.

**Database / HTTP interactions:** Actual SUM/COALESCE/student-status filters, milestone-order SELECT and progress/Award GETs.

**Test Type:** Integration - SQL aggregation, calculation and template wiring.

**Success:** Pass [ ] | Fail [ ]

### IT-4.2 Test Multi-student Leaderboard Ordering and Dense Ranks

**Purpose and components:** Verify repository joins/order and service ranking together.

**Pre-conditions and test data:** Students Alice/Ben each have approved 10, Cara 4.5, Dan no submissions, Eve only rejected/pending submissions. M has approved 50. Insert users/activities in a deliberately different order.

**Test Steps:** 1) GET `/app/progress` as Ben and inspect the leaderboard table/context. 2) Read `ProgressRepository.leaderboard_totals` through a real session.

**Test Criteria (expected results):** Order is Alice, Ben, Cara, Dan, Eve; totals 10, 10, 4.5, 0, 0; dense ranks 1, 1, 2, 3, 3. Ben alone is current; M is excluded despite the higher total. Zero-hour students remain through the outer join.

**Database / HTTP interactions:** Actual outer join, approved-status join condition, grouping/order and progress GET.

**Test Type:** Integration - SQL selection/ordering plus ranking/rendering.

**Success:** Pass [ ] | Fail [ ]

## 5. Award management and availability

### IT-5.1 Test Award Creation, Editing and Availability

**Purpose and components:** Join administrator management, persistence and student catalogue filtering/eligibility.

**Pre-conditions and test data:** Real M/A sessions; A has approved 10; unique padded Award name/description. Independent creation variants: threshold 0.25/quantity 0/Active present, or threshold 10/quantity 2/Active omitted.

**Test Steps:** 1) POST `/admin/awards`; read its persisted row and both catalogues. 2) Edit the same ID, retaining its name, changing description, threshold to 25, stock to 3 and Active present. 3) Set threshold 10 with Active omitted; then restore Active. Read fresh state/views after each change.

**Test Criteria (expected results):** Actions return 303/feedback; normalized values persist on one ID. Zero stock and omitted Active are handled correctly; M sees every Award, A only active ones. Retaining its own name is allowed. A sees Locked at 25; deactivation hides the Award and reactivation restores it eligible at 10 with stock 3.

**Database / HTTP interactions:** Admin create/edit POSTs and committed INSERT/UPDATEs; fresh management/active-catalogue SELECTs.

**Test Type:** Integration - independent create-maintain-availability journeys.

**Success:** Pass [ ] | Fail [ ]

### IT-5.2 Test Invalid Award Creation and Editing

**Purpose and components:** Prevent invalid management actions from committing changes.

**Pre-conditions and test data:** M; existing V and another Award. Independent variants: create with whitespace name, duplicate name or threshold 0; update with another Award's name, quantity -1 or a nonexistent integer ID; update with malformed quantity. All other fields are valid.

**Test Steps:** 1) POST the relevant management route with one invalid value. 2) Inspect the immediate response, follow redirects only, and compare fresh Award rows/counts. Additional numeric boundaries remain in UT-5.3.

**Test Criteria (expected results):** Service failures return 303 with relevant feedback; malformed numbers return 422. No invalid row is created, valid existing fields remain unchanged and no missing ID is inserted.

**Database / HTTP interactions:** Real name/ID lookups, form/service validation and no-write SELECT verification.

**Test Type:** Integration - management failure boundaries.

**Success:** Pass [ ] | Fail [ ]

## 6. Redemption lifecycle and ownership

### IT-6.1 Test Request, Approval and Fulfillment Lifecycle

**Purpose and components:** Connect eligibility, student ownership, request persistence and administrator inventory processing.

**Pre-conditions and test data:** Real A/M sessions; A has approved exactly 10; active V threshold 10/quantity 1; no requests.

**Test Steps:** 1) As A, POST `/app/awards/{V.id}/redeem`; read fresh history/stock. 2) As M, POST `/admin/redemptions/{id}/process` with approved; inspect both actor views and database state. 3) POST fulfilled and inspect again.

**Test Criteria (expected results):** Each action returns 303/feedback. Request persists A/V ownership, Pending status, request time and null processing metadata; stock stays 1. Approval sets Approved, M/time and stock 0 while retaining a fulfillment action. Fulfillment sets Fulfilled, removes the actionable row and leaves stock 0. Student history reflects each stage; verified hours stay 10. Above-threshold comparison remains in UT-3.2.

**Database / HTTP interactions:** Redemption INSERT, processing/request/Award UPDATEs, real eligibility/pending lookups and joined queue/history reads.

**Test Type:** Integration - complete independent student/admin lifecycle with the last item.

**Success:** Pass [ ] | Fail [ ]

### IT-6.2 Test Ineligible or Unavailable Redemption

**Purpose and components:** Verify server-side request rules even when bypassing disabled/missing UI controls.

**Pre-conditions and test data:** Independent variants: A has 9.75 against threshold 10; A has only pending/rejected 10-hour submissions; Award inactive; nonexistent integer Award ID.

**Test Steps:** 1) POST the redemption route directly as A. 2) Follow its redirect and query requests/stock.

**Test Criteria (expected results):** 303 with insufficient-hours or unavailable-Award feedback; no request or inventory change. Pending/rejected hours cannot unlock redemption; hiding/locking UI controls is not the sole enforcement.

**Database / HTTP interactions:** Real aggregate/availability lookups and refused HTTP write; no-insert verification.

**Test Type:** Integration - service rules enforced through HTTP/database.

**Success:** Pass [ ] | Fail [ ]

### IT-6.3 Test Pending Duplicate Scope and Repeat Requests

**Purpose and components:** Verify actual `has_pending` SQL uses student, Award and status together.

**Pre-conditions and test data:** A/B each eligible; V plus another active Award. Independent variants seed A/V as pending, approved, rejected or fulfilled; a pending B/V row; or a pending A/other-Award row.

**Test Steps:** 1) POST A's V redemption route once. 2) Inspect feedback, scoped request counts, original rows and stock.

**Test Criteria (expected results):** Only an existing pending A/V row blocks creation; it remains the sole pending A/V request. Other statuses, other students and other Awards do not block it. Allowed variants add exactly one Pending row, preserve history and leave stock unchanged. This is sequential behavior, not concurrent duplicate safety.

**Database / HTTP interactions:** Actual scoped pending SELECT and conditional INSERT/commit through redemption HTTP handler.

**Test Type:** Integration - persisted duplicate/status filtering.

**Success:** Pass [ ] | Fail [ ]

### IT-6.4 Test Student History Ownership and Submitted-owner Spoofing

**Purpose and components:** Verify authenticated identity scopes submissions, requests and private history.

**Pre-conditions and test data:** A/B sessions, distinct private submission/history markers, approved totals 10, active V. A has no pending V request.

**Test Steps:** 1) As A, GET `/app/hours?student_id={B.id}` and `/app/awards?student_id={B.id}`. 2) POST valid hour and redemption forms adding `student_id={B.id}`. 3) Read both users' private history sections and persisted owners.

**Test Criteria (expected results):** Query/form extras cannot select B as owner; newly created rows belong to A. Each user's My submissions/My Redemptions sections show only that user's rows. Shared Award catalogue and public leaderboard data remain legitimately visible; assertions must be scoped to private history sections.

**Database / HTTP interactions:** Real cookie identity, ignored extra parameters, scoped SELECTs and owner assignment on INSERT.

**Test Type:** Integration - HTTP identity-to-database ownership.

**Success:** Pass [ ] | Fail [ ]

## 7. Rejection and processing guards

### IT-7.1 Test Rejection Without Stock Change

**Purpose and components:** Verify rejection updates request metadata but does not consume inventory.

**Pre-conditions and test data:** M/A; pending A/V request; stock 2; the zero-stock rejection variant remains in UT-4.2.

**Test Steps:** 1) POST the process route with `rejected`. 2) Read stock, request, administrator queue and A's history.

**Test Criteria (expected results):** 303 with rejection feedback; status Rejected and M/time persist; stock is unchanged. Rejected row leaves the actionable queue and remains visible in A's history.

**Database / HTTP interactions:** Real process UPDATE/commit and cross-session queue/history SELECTs.

**Test Type:** Integration - rejection persistence without inventory deduction.

**Success:** Pass [ ] | Fail [ ]

### IT-7.2 Test Stock Depleted Between Request and Approval

**Purpose and components:** Integrate redemption creation, administrator stock editing and processing-time validation.

**Pre-conditions and test data:** M/A; A approved 10; active V quantity 1; no request.

**Test Steps:** 1) As A, request V. 2) As M, POST a valid Award edit reducing quantity to 0. 3) Attempt to approve A's still-pending request. 4) Read state and actor views in fresh requests/sessions.

**Test Criteria (expected results):** Request starts Pending at stock 1. After editing to zero, approval instead persists Rejected with out-of-stock feedback and processor/time. Stock remains exactly 0; A sees Rejected and the row leaves the actionable queue. This models sequential depletion, not competing transactions.

**Database / HTTP interactions:** Student redemption INSERT, administrator Award UPDATE, processing UPDATE and history/stock reads.

**Test Type:** Integration - multiple real workflow components and current-stock validation.

**Success:** Pass [ ] | Fail [ ]

### IT-7.3 Test Invalid, Missing or Repeated Processing

**Purpose and components:** Prevent invalid actions from changing committed requests or stock.

**Pre-conditions and test data:** M; V stock 2. Independent status/decision variants: pending/fulfilled, approved/approved, approved/rejected, rejected/approved, fulfilled/fulfilled, pending/unknown; also a nonexistent integer request ID. Snapshot metadata/stock.

**Test Steps:** 1) POST the process route with the variant. 2) Follow its redirect and compare fresh database state.

**Test Criteria (expected results):** 303 with invalid-action or missing-request feedback. Status, processor/time and stock remain unchanged; no request is added and no second stock deduction occurs. Do not fabricate an orphan Award reference: SQLite foreign-key enforcement makes that a separate integrity concern.

**Database / HTTP interactions:** Real lookup/state guards through administrator POST; committed-state comparison without mock repositories.

**Test Type:** Integration - persisted invalid-operation and repeat-action protection.

**Success:** Pass [ ] | Fail [ ]

## Execution considerations and review

- Future pytest fixtures must establish the guarded test profile before collection imports and manage lifespan explicitly. Tests may run in any order; workflows chained within one case are local to that case only. No case consumes another case's accounts or rows.
- Use real cookies/password verification for authentication coverage. Do not print passwords, hashes, tokens or environment secrets; test SQL logging/captured output must not expose them.
- HTML responses contain shared catalogue/leaderboard content alongside private histories. Assert scoped table rows, template context and database ownership rather than whole-page substring absence. Flash messages are consumed when rendered, so check the first redirected GET.
- Use fresh verification sessions to observe commits; avoid stale SQLAlchemy identity-map results. Assert timestamp presence/ordering within sensible bounds rather than exact wall-clock equality. Capture IDs dynamically.
- SQLite must enforce foreign keys on every connection. File locking, internally committed writes and the fixed filename make serial fixtures safer than parallel workers. Do not assume model `gt`/`ge` declarations create database CHECK constraints.
- Known authorization-status and generic registration-message issues remain documented; planning does not repair or conceal them. SQLite passing results must never be described as proof of PostgreSQL concurrency safety.
- Later implementation will provide a separate CLI-selectable pytest integration suite and trace results to these IDs. No fixture code, tests, HTTP calls, database connections, screenshots or pass/fail outcomes are produced by this planning task.

**General Comments / Review Notes:**

______________________________________________________________________

**Reviewed by:** ____________________  
**Review date (DD/MM/YYYY):** ____________________
