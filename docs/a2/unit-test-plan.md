# Student Awards Unit Test Plan

**COMP3613 Assignment 2 | Version 1.1 | Status: Planning only - not executed**

This plan addresses the assignment's requirement for testing modules in isolation, with later implementation in pytest. It follows the case-block style and Pre-conditions, Test Criteria and Success terminology of the approved [UAT plan](uat-plan.md). There are **19 planned cases**; parameterized inputs within a case are separate invocations of the same rule, not additional plan IDs. All result fields remain blank.

## Scope and preparation

Test the existing volunteer-submission, progress and Award services independently. Use in-memory SQLModel objects, repository mocks or small fakes; never construct a real Session, engine or HTTP client. These unit tests require neither the development nor the future integration-test database, running server, seeded users or environment secrets. Do not import `app.main` or `app.database` in the future unit-test fixtures.

Common inputs: student ID `101`, administrator ID `900`, activity date `2026-10-20`, activity `Beach Cleanup`, organization `Campus Volunteers`, supporting information `Confirmed by organizer`. All hours/thresholds use `Decimal` values. Default Award: ID `201`, name `Campus Voucher`, required hours `10`, quantity `2`, active `True`. Default submission/redemption IDs are `301`/`401`, initially `pending`. Each invocation receives fresh objects and mocks; cases do not depend on previous cases or UAT data.

Mock persistence methods to return the supplied object without saving it. For rejection paths, check that no create/save method is called and existing objects remain unchanged. Where clocks matter, replace the `datetime` name in the specific service module with a controlled clock returning a fixed timestamp. Do not depend on wall-clock equality.

## Code references and unit boundaries

- [VolunteerSubmissionService](../../app/services/volunteer_submission_service.py): `submit`, `review`.
- [ProgressService](../../app/services/progress_service.py): `get_student_progress`.
- [AwardService](../../app/services/award_service.py): `get_student_awards`, `request_redemption`, `create_award`, `update_award`, `process_redemption`; numeric rules are shared through `_validate_award_values`.
- Integration-only aggregate references: [VolunteerSubmissionRepository.approved_hours_total](../../app/repositories/volunteer_submission.py) and [AwardRepository.verified_hours](../../app/repositories/award.py).

Approval/rejection/fulfillment cases test business transitions with a supplied administrator ID. They do not establish administrator authorization: routers enforce that using `AdminDep`. Authentication, authorization, rendered pages, persistence, SQL row filtering/ordering, unique/foreign-key constraints and transaction concurrency require later integration/API tests or UAT. Read-only dashboard composition and simple list-forwarding methods are outside this focused business-rule suite.

Approved-only filtering/summation is verified with real rows in integration case IT-4.1; no wrapper-delegation or mocked SQL-shape cases are retained here. Missing processing/update IDs are covered by IT-7.3/IT-5.2. Orphan references are checked through foreign-key enforcement in IT-1.1 rather than fabricating invalid persisted relationships.

## 1. Volunteer-hour submission and review

### UT-1.1 Test Valid Submission and Defaults

**Function/service:** `VolunteerSubmissionService.submit`.

**Purpose:** Accept positive whole/fractional hours and normalize text.

**Pre-conditions and test inputs:** Common activity; hours `4`, `4.5` and `0.01` in separate invocations; padded activity/organization; supporting information padded or blank.

**Mocked dependencies:** `VolunteerSubmissionRepository.create`, returning its argument.

**Test Criteria (expected result):** One created object has the supplied student/date/hours, trimmed text, status `pending`, a submission timestamp and null review metadata; blank supporting information becomes an empty string. The returned object is the repository result. The service accepts any positive decimal; browser quarter-hour restrictions are not a service rule.

**Test Type:** Unit - service with mocked persistence, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-1.2 Test Invalid Submission Values

**Function/service:** `VolunteerSubmissionService.submit`.

**Purpose:** Reject missing meaningful text and nonpositive hours.

**Pre-conditions and test inputs:** Otherwise-valid activity; vary activity name or organization to empty/whitespace, or hours to `0`/`-0.25`, one invalid value at a time.

**Mocked dependencies:** Volunteer-submission repository.

**Test Criteria (expected result):** `ValueError` identifies required activity/organization or positive hours as appropriate; `create` is never called.

**Test Type:** Unit - service validation, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-1.3 Test Approve and Reject Pending Hours

**Function/service:** `VolunteerSubmissionService.review`.

**Purpose:** Apply valid decisions and record review metadata.

**Pre-conditions and test inputs:** Pending submission; decisions `approved`, `rejected`, and padded/mixed-case equivalents; administrator ID `900`.

**Mocked dependencies:** Repository `get_by_id`/`save`; module clock.

**Test Criteria (expected result):** Decision is normalized; status becomes approved/rejected; reviewer ID and fixed review timestamp are set. `save` receives the changed submission once, and its result is returned; activity details/hours are unchanged.

**Test Type:** Unit - service state transition, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-1.4 Test Invalid Review or Previously Reviewed Submission

**Function/service:** `VolunteerSubmissionService.review`.

**Purpose:** Prevent unsupported decisions and repeat review.

**Pre-conditions and test inputs:** Separate variants: invalid decision `pending` or empty; valid decision with missing submission; valid decision for already `approved` or `rejected` submission.

**Mocked dependencies:** Repository lookup/save.

**Test Criteria (expected result):** Appropriate `ValueError` reports invalid decision, missing submission or pending-only review. No save or object mutation occurs; invalid decisions are rejected before lookup.

**Test Type:** Unit - service rejection paths, not integration.

**Success:** Pass [ ] | Fail [ ]

## 2. Progress, milestones and leaderboard

### UT-2.1 Test Dense Ranking and Current Student

**Function/service:** `ProgressService.get_student_progress`.

**Purpose:** Assign consecutive ranks to distinct totals and identify the current student.

**Pre-conditions and test inputs:** Already ordered rows `(101, Alice, 10)`, `(102, Ben, 10)`, `(103, Cara, 4.5)`, `(104, Dan, 0)`; current student `102`; no milestones.

**Mocked dependencies:** `ProgressRepository.leaderboard_totals` and `list_milestones`.

**Test Criteria (expected result):** Ranks are `1, 1, 2, 3`; only Ben has `is_current=True`; current hours/rank are `10`/`1`; row order is preserved. Repository SQL ordering, tie-name sorting and administrator exclusion are integration concerns, not behavior performed by this service.

**Test Type:** Unit - ranking transformation over fake ordered rows, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-2.2 Test Empty Progress and Missing Current Student

**Function/service:** `ProgressService.get_student_progress`.

**Purpose:** Handle empty collections and an absent current-student row.

**Pre-conditions and test inputs:** Empty leaderboard, or only another student's row; current ID `101`. Exercise an empty milestone list and a valid 10-hour milestone.

**Mocked dependencies:** Progress repository read methods.

**Test Criteria (expected result):** Current verified hours default to `0` and rank to `None`; no returned row is current. Empty lists are handled without failure; an existing milestone is incomplete at 0% when the current student is absent.

**Test Type:** Unit - empty/default service results, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-2.3 Test Milestone Boundaries, Rounding and Cap

**Function/service:** `ProgressService.get_student_progress`.

**Purpose:** Calculate completion and display percentages accurately.

**Pre-conditions and test inputs:** One current-student row; threshold `10` with totals `0`, `9.75`, `10`, `10.25`; also total `1` with threshold `3`. Milestones have valid positive thresholds.

**Mocked dependencies:** Progress repository returning the controlled total and milestone.

**Test Criteria (expected result):** Percentages are respectively `0`, `97.5`, `100`, `100`, and `33.3`; completion is false below the threshold and true at/above it. Name, description and threshold are preserved. No percentage exceeds 100.

**Test Type:** Unit - derived milestone calculations, not integration.

**Success:** Pass [ ] | Fail [ ]

## 3. Award catalogue and redemption requests

### UT-3.1 Test Catalogue Eligibility and Pending Flags

**Function/service:** `AwardService.get_student_awards`.

**Purpose:** Present correct eligibility without confusing it with request status.

**Pre-conditions and test inputs:** Verified total `10`; active Awards with thresholds `4`, `10`, `25`; pending flag true for the 10-hour Award only. Include a separate empty-catalogue variant.

**Mocked dependencies:** Award repository `verified_hours`, `list_active`, `has_pending`, `list_student_redemptions`.

**Test Criteria (expected result):** Eligibility is true/true/false; pending flags match the corresponding student/Award lookup. Returned hours and history match repository results; empty catalogue returns an empty Award list. Actual inactive-row filtering remains the repository's integration responsibility.

**Test Type:** Unit - service composition and threshold comparisons, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-3.2 Test Valid Redemption Request Without Stock Reservation

**Function/service:** `AwardService.request_redemption`.

**Purpose:** Accept eligible requests at/above the threshold without spending hours or stock.

**Pre-conditions and test inputs:** Active Award, threshold `10`, quantity `1`; verified total `10` or `10.25`; no pending request. A prior nonpending request may be represented by `has_pending=False`.

**Mocked dependencies:** Award repository lookup, verified total, pending check and `create_redemption`.

**Test Criteria (expected result):** Creates one pending redemption for student `101`/Award `201`, with request timestamp and null processing metadata; returns repository result. Quantity remains 1; no processing/save operation reduces inventory. The student/Award pair is passed to `has_pending`; SQL recognition of prior statuses needs integration testing.

**Test Type:** Unit - request business rules with fake persistence, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-3.3 Test Missing, Inactive or Ineligible Award

**Function/service:** `AwardService.request_redemption`.

**Purpose:** Refuse unavailable Awards and insufficient verified hours.

**Pre-conditions and test inputs:** Separate variants: lookup returns `None`; inactive Award; active 10-hour Award with total `9.75`.

**Mocked dependencies:** Award repository read/create methods.

**Test Criteria (expected result):** `ValueError` reports unavailable Award or insufficient hours, as appropriate. No redemption is created and Award stock is unchanged.

**Test Type:** Unit - service rejection paths, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-3.4 Test Duplicate Pending Request Rejection

**Function/service:** `AwardService.request_redemption`.

**Purpose:** Prevent creation when the repository reports an existing pending request.

**Pre-conditions and test inputs:** Active eligible Award; `has_pending(101, 201)` returns true.

**Mocked dependencies:** Award repository lookup/total/pending/create methods.

**Test Criteria (expected result):** Raises the pending-request `ValueError`; `create_redemption` is not called and inventory is unchanged. This checks the sequential service guard, not concurrent duplicate prevention.

**Test Type:** Unit - duplicate guard with mocked lookup, not integration.

**Success:** Pass [ ] | Fail [ ]

## 4. Administrator redemption processing

### UT-4.1 Test Approval and Last-item Boundary

**Function/service:** `AwardService.process_redemption`.

**Purpose:** Approve pending requests and deduct exactly one item.

**Pre-conditions and test inputs:** Pending redemption; stock `2` or `1`; decision `approved`, including a padded/mixed-case variant; administrator `900`.

**Mocked dependencies:** Award repository redemption/Award lookups and `save_processing`; module clock.

**Test Criteria (expected result):** Status becomes approved; stock becomes 1 or 0; processor/fixed timestamp are recorded. Saves redemption and Award together once; returns `Redemption approved.`.

**Test Type:** Unit - state/inventory mutation, not transaction integration.

**Success:** Pass [ ] | Fail [ ]

### UT-4.2 Test Rejection Without Inventory Change

**Function/service:** `AwardService.process_redemption`.

**Purpose:** Reject a pending request without consuming stock.

**Pre-conditions and test inputs:** Pending redemption; stock `2` or `0`; decision `rejected`.

**Mocked dependencies:** Award repository lookups/save; module clock.

**Test Criteria (expected result):** Status becomes rejected; stock is unchanged; processor/time are set. Saves once and returns `Redemption rejected.`.

**Test Type:** Unit - rejection transition, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-4.3 Test Stock Exhausted Before Approval

**Function/service:** `AwardService.process_redemption`.

**Purpose:** Reject approval when current stock is zero.

**Pre-conditions and test inputs:** Existing pending request made earlier while stock was available; Award lookup now returns quantity `0`; decision `approved`.

**Mocked dependencies:** Award repository lookups/save; module clock.

**Test Criteria (expected result):** Request becomes rejected rather than approved; inventory remains exactly 0; processor/time are set and saved once. Returns `Request rejected because the Award is out of stock.`. This models current stock at processing time without replaying creation or database changes.

**Test Type:** Unit - stock-exhaustion branch, not concurrency integration.

**Success:** Pass [ ] | Fail [ ]

### UT-4.4 Test Fulfillment Without Second Stock Deduction

**Function/service:** `AwardService.process_redemption`.

**Purpose:** Complete an approved request without consuming another item.

**Pre-conditions and test inputs:** Approved redemption; quantity `1`; decision `fulfilled`.

**Mocked dependencies:** Award repository lookups/save; module clock.

**Test Criteria (expected result):** Status becomes fulfilled; processor/time are updated; quantity stays 1. Calls `save_processing` with the redemption only and returns `Redemption marked as fulfilled.`.

**Test Type:** Unit - fulfillment state transition, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-4.5 Test Invalid Processing Transitions

**Function/service:** `AwardService.process_redemption`.

**Purpose:** Prevent unsupported actions and repeat processing.

**Pre-conditions and test inputs:** Status/decision pairs: pending/fulfilled, approved/approved, approved/rejected, rejected/approved, fulfilled/fulfilled, pending/unknown. Valid referenced Award exists.

**Mocked dependencies:** Award repository lookups/save.

**Test Criteria (expected result):** Raises `ValueError` for an action invalid for the current status. No save occurs; redemption status/metadata and quantity remain unchanged.

**Test Type:** Unit - state-machine rejection paths, not integration.

**Success:** Pass [ ] | Fail [ ]

## 5. Award management and validation

### UT-5.1 Test Valid Award Creation and Zero Stock

**Function/service:** `AwardService.create_award`.

**Purpose:** Normalize Award details and accept valid inventory boundaries.

**Pre-conditions and test inputs:** Padded unique name; padded or blank description; required hours `0.25`; quantity `0` or `2`; active true/false variants.

**Mocked dependencies:** Award repository `get_by_name` returns `None`; `save_award` returns its argument.

**Test Criteria (expected result):** Saves one Award with trimmed name/description, blank description converted to `None`, and exact threshold, inventory and active flag. Name lookup uses trimmed text; returns the saved Award. Zero stock is valid.

**Test Type:** Unit - creation rules without persistence, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-5.2 Test Valid Award Update and Unchanged Own Name

**Function/service:** `AwardService.update_award`.

**Purpose:** Update all managed fields while allowing the same Award to retain its name.

**Pre-conditions and test inputs:** Existing Award; valid padded name/description, threshold `25`, quantity `0`, active false. Variants: retain own name, with duplicate lookup returning the same ID; rename to an unused name, lookup returning `None`.

**Mocked dependencies:** Award repository `get_award`, `get_by_name`, `save_award`.

**Test Criteria (expected result):** Saves the existing Award once with normalized text and supplied threshold/stock/active state; no replacement entity is created. Keeping its own name is accepted; repository result is returned.

**Test Type:** Unit - update/availability rules, not integration.

**Success:** Pass [ ] | Fail [ ]

### UT-5.3 Test Invalid Award Management Inputs

**Function/service:** `AwardService.create_award`; separately, `update_award`, exercising `_validate_award_values` through the public methods.

**Purpose:** Reject invalid names, thresholds and inventory without mutation or saving.

**Pre-conditions and test inputs:** Vary one field at a time: empty/whitespace name; padded duplicate name; threshold `0`/`-0.25`; quantity `-1`. Other values are valid. For update, the target exists; duplicate-name lookup returns a different Award ID. Numeric variants use a permitted name.

**Mocked dependencies:** Award repository lookups and `save_award`, with fresh objects for each operation/variant.

**Test Criteria (expected result):** Raises the matching required-name, duplicate-name, positive-hours or nonnegative-quantity `ValueError`. No save occurs and existing fields remain unchanged. Check trimmed duplicate lookup names. Do not duplicate public numeric cases with private-helper tests; database uniqueness is an integration concern.

**Test Type:** Unit - parameterized service validation, not integration.

**Success:** Pass [ ] | Fail [ ]

## Implementation considerations and later coverage

- Use repository-spec mocks or small purpose-built fakes. Keep real business logic in the method under test; do not reproduce it in a fake. Verify observable results and writes, not every incidental read or call order.
- Approved-only summation lives in two repository aggregate methods. Integration case IT-4.1 supplies actual approved/pending/rejected rows for multiple students and verifies totals, including no approved rows. Mock-returned totals in the retained service units do not prove SQL exclusions.
- `ProgressService` trusts repository ordering and valid positive milestone thresholds. Feed ordered rows; do not invent sorting, administrator filtering or zero-threshold recovery in the service. Invalid milestone persistence/model validation belongs outside this service plan.
- SQLModel table field declarations are not proof of database CHECK constraints or automatic validation on every construction path. Assert explicit service rules here; check persistence constraints separately. Request parsing, missing HTTP fields and browser numeric steps are also outside these units.
- Module-local clocks and mutable records require careful fixture setup. Return fresh SQLModel objects per variant; patch the service's imported clock, not unrelated global time.
- Service stock checks and pending-request guards are sequential. Unit mocks cannot establish atomic commits, rollback, concurrent inventory safety, SQL uniqueness, or repeat-request status filtering. Reserve those guarantees for isolated database integration tests.
- All variants will eventually be runnable through pytest with readable parameter IDs; no test implementation, execution, screenshots or results are included at this planning stage.

**General Comments / Review Notes:**

______________________________________________________________________

**Reviewed by:** ____________________  
**Review date (DD/MM/YYYY):** ____________________
