# Student Awards User Acceptance Test Plan

**COMP3613 Assignment 2 | Version 1.1 | Status: Planning only - not executed**

Adapted from the lecturer's two-page **UAT Template.pdf**. The template's Test Case, Pre-conditions, Test Steps, Test Criteria and Success fields are retained as compact case blocks. Test Criteria are the expected success criteria; all result and acceptance fields remain blank until manual execution. There are **17 planned cases**. Combined journeys retain distinct success criteria; record any failed step separately in General Comments.

**Tester Name:** ____________________  
**Tester Position:** ____________________  
**Date of Test (DD/MM/YYYY):** ____________________  
**Browser/version:** ____________________  
**Application version/commit:** ____________________

## Scope and preparation

Cover the three student workflows: Submit Volunteer Hours, Track Progress and Milestones, and Redeem Awards; their supporting administrator functions; and relevant access controls. Testing is manual through the existing browser interface. API testing, automated testing, database manipulation and deployment are outside this plan.

At execution time, use only `http://127.0.0.1:5000` with the A2 development database `comp3613a2/a2_development.db`. Do not use the test database or Assignment 1 deployment. The application and seeded administrator account must be available. Do not initialize, reset or clear a database as part of UAT.

Choose a unique run label **R** (for example, `UAT20261026a`). Student **A**, **B** and **C** mean new accounts named `R_a`, `R_b` and `R_c`, with unique valid email addresses and privately held passwords. Create A in 1.1; create B/C through Register when preparing 3.2. Do not write passwords in this plan or screenshots. Use separate browser profiles/private windows for student and administrator sessions, or sign out before switching users.

Execute cases in numerical order and sign in/out as needed to establish each stated actor/session precondition. Later data preconditions depend on the stated earlier outcomes; if those outcomes are unmet, leave Success blank and record the blockage in General Comments. Use only run-labelled records. For every activity use organization `Campus Volunteers`, a valid past date, and supporting information `UAT activity for R`, unless the case deliberately varies a field. Refresh the relevant page after another user changes data.

Seeded milestones should be Bronze 10 hours, Silver 25 hours and Gold 50 hours. Confirm these thresholds before execution; if different, record the discrepancy before proceeding. Drawings contain illustrative data: the controlled values below determine expected results. Approved hours are cumulative eligibility, not a balance spent on Awards. Requests do not reserve stock; approval reduces it. Repeat requests are allowed once the earlier request is no longer pending.

## Wireframe references

- **W1:** [Log Volunteer Hours](../wireframes/log-volunteer-hours.png) - cases 2.1-2.3.
- **W2:** [Progress and Milestones](../wireframes/progress-and-milestones.png) - cases 3.1-3.2.
- **W3:** [Redeem Rewards](../wireframes/redeem-rewards.png) - cases 5.1-5.2 and student-side checks in 6.1-6.3.
- **W4:** [Administrator Approvals](../wireframes/admin-approvals.png) - cases 2.3 and 6.1-6.3.
- **W5:** [Add Prize](../wireframes/add-prize.png) - cases 4.1-4.3.

The current product calls prizes/rewards **Awards**. History tables, review details, edit/confirmation modals and fulfillment are accepted refinements documented in [the existing project report](../report.md), supplementing the drawings. Authentication cases reference existing Sign in/Register pages and role-specific navigation.

## 1. Authentication and authorization

### 1.1 Test Registration and Role-specific Login

**Pre-conditions:** A's username/email are unused; the local administrator exists; both browser profiles are signed out.

**Test Steps:** 1) Register A with valid details and observe the Sign in page. 2) Sign in as A and inspect Student navigation. 3) In the separate administrator profile, sign in and open Approvals and Awards.

**Test Criteria:** Registration redirects to `/login` with `Registration completed! Sign in now!`, without automatically signing A in. A's login opens `/app`, showing A's username, Progress, Log hours, Awards and Sign out, without administrator navigation. Administrator login opens `/admin`, showing the correct identity and working Approvals, Awards and Sign out navigation.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 1.2 Test Invalid Login

**Pre-conditions:** Tester is signed out; A exists.

**Test Steps:** 1) Attempt to sign in as A with an incorrect password. 2) Attempt a nonexistent username with a nonempty password.

**Test Criteria:** Each attempt shows incorrect-credentials feedback and leaves the tester at Sign in; no authenticated dashboard is accessible.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 1.3 Test Logout and Unauthenticated Access

**Pre-conditions:** A is signed in.

**Test Steps:** 1) Click Sign out. 2) Directly open `/app/hours`, `/app/progress`, `/app/awards`, `/admin/approvals` and `/admin/awards` using the address bar. 3) Sign in again when finished.

**Test Criteria:** Logout returns to Sign in; protected content/actions are unavailable while signed out, with an access/session message or sign-in prompt. No new records are created. HTTP status-code assertions belong to later API tests.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 1.4 Test Student Restrictions

**Pre-conditions:** A is signed in as a student.

**Test Steps:** 1) Inspect A's navigation. 2) Directly open `/admin`, `/admin/approvals` and `/admin/awards`.

**Test Criteria:** Administrator navigation is absent; direct access is denied without displaying review, processing or Award-management controls or other students' private submission details.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

## 2. Volunteer-hour submission and review

### 2.1 Test Valid Whole and Fractional Hour Submissions

**Pre-conditions:** A is signed in with zero submissions and verified hours.

**Test Steps:** 1) Open Log hours; submit `R Beach Cleanup`, 4 hours, with the common activity details. 2) Submit `R Peer Tutoring`, 4.5 hours. 3) Refresh the page; open Progress.

**Test Criteria:** Each submission has success feedback and exactly one My submissions row with correct activity, organization, date, hours and Pending status. Values display as `4` and `4.5`. Both persist after refresh; verified hours remain zero while pending.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 2.2 Test Invalid Hour Submission

**Pre-conditions:** A is signed in; note the existing submission count.

**Test Steps:** 1) Attempt to submit while omitting each required field in turn: activity, organization, hours and date; restore other fields between attempts. 2) With other fields valid, try hours `0`, then `-1`. 3) Refresh My submissions.

**Test Criteria:** Every invalid attempt is blocked with browser validation or application feedback. No additional history row appears; existing records are unchanged. Supporting information is optional and is not a required-field failure.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 2.3 Test Administrator Approval and Rejection of Hours

**Pre-conditions:** Both 2.1 submissions remain Pending; administrator is signed in separately.

**Test Steps:** 1) In Approvals, View details for A's `R Beach Cleanup`; check the submitted information and Approve. 2) Refresh A's history/Progress. 3) View and Reject A's `R Peer Tutoring`; refresh both actor views.

**Test Criteria:** Review details match student, activity, organization, date, hours and supporting information. Each decision shows feedback and removes its row from the pending queue. A sees Approved for 4 hours and Rejected for 4.5 hours. Verified hours become 4 after approval and stay 4 after rejection; the pending/rejected 4.5 hours never contribute. Reviewed rows have no further review actions.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

## 3. Progress, milestones and leaderboard

### 3.1 Test Milestone Threshold and Approved-only Progress

**Pre-conditions:** A has 4 approved hours after 2.3; milestones match the preparation values.

**Test Steps:** 1) As A, submit `R Library Service` for 5.75 hours. Check Progress while pending, then have the administrator approve it and refresh. 2) Submit `R Event Support` for 0.25 hours; approve it and refresh Progress again.

**Test Criteria:** Pending hours do not affect progress. The first approval produces 9.75 verified hours with Bronze incomplete at `9.75 / 10`; the second produces exactly 10 and Bronze Complete. Silver and Gold remain incomplete at `10 / 25` and `10 / 50`; progress bars reflect those totals and never exceed their displayed bounds. Rejected hours remain excluded.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 3.2 Test Leaderboard Ordering and Tied Ranks

**Pre-conditions:** A has 10 approved hours. Register fresh B/C through the UI. As B submit one run-labelled 10-hour activity; as C submit one 4.5-hour activity; have the administrator approve both.

**Test Steps:** 1) Open Progress as A, B and C. 2) Compare verified totals, order and rank across the full leaderboard, including any existing students.

**Test Criteria:** A/B each show 10 hours and share a rank; C shows 4.5 and ranks below them. Rows sort by decreasing approved-hour totals, then ascending username for ties. Dense rank starts at 1 and equals one plus the number of distinct higher totals, without gaps after ties. Students with no approved hours appear with 0; administrators are excluded. The current user is identified as You. Absolute ranks account for all existing students rather than assuming A/B are first.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

## 4. Award management

### 4.1 Test Add Awards

**Pre-conditions:** Administrator is signed in; these run-labelled Award names are unused.

**Test Steps:** 1) Open Awards, click Add Award and create `R Voucher`: description `Campus cafe voucher`, required hours 10, quantity 2, Active selected. 2) Similarly create `R Hoodie`: 25 hours, quantity 2, active; and `R Empty`: 10 hours, quantity 0, active. 3) Refresh the catalogue and view Awards as A.

**Test Criteria:** Each creation shows feedback and one persistent catalogue row with the specified values. All three active Awards appear in A's catalogue; zero inventory is accepted as a valid quantity.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 4.2 Test Award Validation and Duplicate Names

**Pre-conditions:** 4.1 is complete; note catalogue values and count.

**Test Steps:** 1) In Add Award, try a blank name, required hours 0, and quantity -1 in separate otherwise-valid attempts. 2) Try creating another Award named `R Voucher`. 3) In Edit for `R Voucher`, attempt required hours 0, then cancel/reopen and attempt quantity -1. 4) Refresh the catalogue.

**Test Criteria:** Each attempt is prevented with validation or duplicate-name feedback; no extra Award is created and existing Award values remain unchanged.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 4.3 Test Award Editing, Stock and Availability

**Pre-conditions:** `R Voucher` is active, quantity 2, with no requests; A has 10 approved hours.

**Test Steps:** 1) Open Edit and check prefilled values. Save name `R Campus Voucher`, description `Updated campus voucher`, threshold 25 and quantity 3. 2) Refresh A's catalogue. 3) Set threshold back to 10 and clear Active; save and refresh A's catalogue. 4) Restore Active, save and refresh again.

**Test Criteria:** Edited values persist in management and student views; at threshold 25 A sees Locked. Deactivation shows Inactive to the administrator and hides the Award from A. Reactivation restores the same renamed Award with threshold 10, quantity 3 and Redeem available to A. Subsequent cases use `R Campus Voucher`.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

## 5. Award redemption

### 5.1 Test Eligibility, Confirmation and Duplicate Prevention

**Pre-conditions:** 3.2 and 4.3 are complete; A/B have 10 verified hours, C has 4.5; voucher quantity is 3 and A has no requests.

**Test Steps:** 1) Compare voucher/hoodie actions as A and C. 2) As A, Redeem the voucher, inspect its modal and Cancel; inspect history. 3) Reopen and Confirm request, then refresh. 4) Navigate away/back and attempt another request if offered.

**Test Criteria:** A can redeem the 10-hour voucher but not the 25-hour hoodie; C sees both Locked. Cancel adds nothing. Confirm shows success and one Pending voucher history row with requested date. The action becomes Pending rather than Redeem, preventing a second pending request through the UI. Stock remains 3 and A's verified hours remain 10. Direct-request enforcement is covered separately by integration/API testing.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 5.2 Test Student History Separation

**Pre-conditions:** A's voucher request remains Pending; B has no redemptions and has 10 verified hours.

**Test Steps:** 1) As B, inspect Log hours and Awards histories. 2) Request `R Campus Voucher` as B. 3) Refresh both A's and B's histories in their separate sessions.

**Test Criteria:** B sees B's activity and request, not A's activities or request; A sees only A's private histories. Each has one own pending voucher request. The public leaderboard remains shared; stock remains 3 because neither request is approved.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

## 6. Redemption processing

### 6.1 Test Redemption Approval and Fulfillment

**Pre-conditions:** A/B have separate pending voucher requests after 5.1/5.2; quantity is 3.

**Test Steps:** 1) As administrator, identify A's voucher request by student name and Approve. 2) Refresh A's history, Approvals and stock. 3) Mark A's approved request as fulfilled; refresh again.

**Test Criteria:** Approval shows feedback, A sees Approved and stock decreases exactly once to 2; B's request stays Pending. A's approved row offers Mark as fulfilled. Fulfillment shows Fulfilled in A's history, removes A's row from the actionable queue and offers no further processing. Stock stays 2 and A retains 10 verified hours.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 6.2 Test Repeat Request and Administrator Rejection

**Pre-conditions:** A's first voucher request is Fulfilled; quantity remains 2.

**Test Steps:** 1) As A, request the voucher again and confirm. 2) As administrator, Reject A's new pending request. 3) Refresh A's history and the administrator queue/catalogue.

**Test Criteria:** A can create a new pending request after fulfillment. Rejection changes only the new request to Rejected, preserves the earlier Fulfilled row, removes the rejected request from the actionable queue, and leaves quantity 2. A can again see Redeem after rejection; verified hours remain 10.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

### 6.3 Test Out-of-stock Redemption Processing

**Pre-conditions:** `R Empty` is active with threshold 10 and was created with quantity 0 in 4.1; A has 10 verified hours and no request for it. The administrator can edit its stock.

**Test Steps:** 1) As administrator, Edit `R Empty`, set quantity to 1 and Save changes. 2) As A, refresh Awards, confirm quantity 1, request `R Empty` and confirm. 3) As administrator, verify A's request is Pending, then Edit the Award, reduce quantity to 0 and save. 4) Return to Approvals, locate A's pending request and click Approve. 5) Refresh A's history, Approvals and Award stock.

**Test Criteria:** A's request is created as Pending while quantity is 1; requesting does not reserve or reduce stock. After the administrator reduces quantity to 0, attempting approval rejects the pending request with out-of-stock feedback. A sees Rejected, inventory remains exactly 0 and the request leaves the actionable queue. Inventory never becomes negative.

**Success (indicate with a tick):** Pass [ ] | Fail [ ]

## Recording and acceptance (complete only after execution)

For each executed case, tick Pass only when all Test Criteria are observed; otherwise tick Fail and record the case ID, actual result, expected result, evidence reference and any retest outcome in General Comments. Leave unexecuted/blocked cases unticked. Capture relevant screens without passwords, tokens or unrelated personal data. Navigation checks already performed are not results for this plan.

Retain the run-labelled data for evidence; use a new run label and fresh student accounts for a repeat run rather than deleting existing records. An overall acceptance decision may be made only after all planned cases are executed, failures are resolved/retested, and the tester confirms the workflows meet the criteria. Do not pre-fill acceptance or signature.

**General Comments:**

______________________________________________________________________

______________________________________________________________________

**Accepted | Rejected:** ____________________

**Signature:** ____________________
