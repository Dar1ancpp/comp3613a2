# Authentication and Authorization HTTP Status Defects

**COMP3613 Assignment 2 | IT-2.4 and IT-2.5 | Resolved and verified after approval**

The new tests enforce the requested intended status codes: **401** for missing,
invalid or expired authentication, and **403** for a signed-in student denied
administrator permissions. The test plans are unchanged; their earlier known-issue
note is not used to accept HTTP 200 as correct. No tests are marked xfail or skipped.

## Baseline commands and actual results (before correction)

```powershell
python -B -m pytest tests/integration/test_authentication_and_authorization.py -v --tb=short
python -B -m pytest tests/integration -v --tb=short
```

- New group: **0 passed, 5 failed, 0 skipped**.
- All implemented integration tests: **9 passed, 5 failed, 0 skipped**.
- Each run reported one existing Starlette/httpx deprecation warning.
- Ruff format and lint checks passed for `tests/integration`.

Only the guarded local `a2_test.db` was used for database connections and schema
cleanup. Requests used the actual application, real JWT cookies, real password
hashing and independent fixture data; authentication was not mocked.

## Defect 1: Unauthorized handler returns HTTP 200

**Location:** [app/main.py](../../app/main.py), `unauthorized_redirect_handler`.

The dependency correctly raises 401 for missing, tampered and expired cookies.
The handler renders `401.html` without specifying `status_code`, so the final
response is HTTP 200. The same happens after successful logout removes the cookie.

**Failed assertion:** `assert observed == expected`, where the four IT-2.4 variants
expect 401 for each of:

- GET `/app/hours`
- GET `/app/progress`
- GET `/app/awards`
- POST `/app/hours` with otherwise-valid submission data

All observed statuses were **200**, not 401.

**Minimal proposed fix:** Keep the existing template and add
`status_code=status.HTTP_401_UNAUTHORIZED` to its `TemplateResponse`. Forward the
exception's existing headers (including `WWW-Authenticate`) so the handler retains
the authentication challenge supplied by the dependency.

## Defect 2: Administrator dependency raises 401 instead of 403

**Location:** [app/dependencies/auth.py](../../app/dependencies/auth.py),
`is_admin_dep` / `AdminDep`.

The student is successfully authenticated through a real login. The administrator
dependency rejects that student with 401, which then reaches the defective handler
above and becomes HTTP 200. Correcting only the handler would produce 401 here;
the permission dependency must also raise 403.

**Failed assertion:** `assert observed == expected`, where IT-2.5 expects 403 for:

- GET `/admin`, `/admin/approvals` and `/admin/awards`.
- POST `/admin/awards` and `/admin/awards/{id}` to create/edit an Award.
- POST `/admin/submissions/{id}/review` with both approved and rejected decisions.
- POST `/admin/redemptions/{id}/process` with both approved and rejected decisions.

All nine observed statuses were **200**, not 403.

**Minimal proposed fix:** Change the insufficient-permission exception in
`is_admin_dep` to `status.HTTP_403_FORBIDDEN`. FastAPI's existing default handling
will return 403; no new endpoint, authentication mechanism or template is necessary.

## Other checks completed before the failing assertions

The tests deliberately check records and protected content before asserting statuses.
They established that:

- Logout redirected to Sign in, expired the cookie and removed it from the client.
- Protected student content was withheld for all four unauthenticated variants.
- Administrator views withheld protected Award and student-review information.
- Unauthorized submission, review, Award and redemption actions changed no domain
  rows, processing metadata, user password hashes or inventory.

These successful intermediate checks are not counted as separate passing tests:
the five new executions remain failed because their HTTP contracts are incorrect.
Thus the observed defects concern response status semantics; the exercised access
checks did prevent the attempted reads/writes.

At baseline, application source, finalized plans and previous tests were unchanged.
The original failures and proposed corrections above are retained as evidence.

## Approved correction and verification

Only these application changes were made:

- `app/main.py`: the existing `401.html` response explicitly returns
  `status.HTTP_401_UNAUTHORIZED` and forwards `getattr(exc, "headers", None)`,
  preserving authentication headers and the existing browser error page.
- `app/dependencies/auth.py`: `is_admin_dep` now raises
  `status.HTTP_403_FORBIDDEN` for an authenticated nonadministrator. Missing or
  invalid authentication still fails earlier in `get_current_user` with 401.
  FastAPI's existing default 403 handling retains that status without a new handler.

No test assertions, test plans or unrelated application behavior were changed.
Verification commands:

```powershell
python -B -m pytest tests/integration/test_authentication_and_authorization.py -v --tb=short
python -B -m pytest tests/integration -v --tb=short
python -B -m pytest tests/unit -v
```

Actual results after correction:

- IT-2.4/IT-2.5: **5 passed, 0 failed, 0 skipped**.
- Complete implemented integration suite: **14 passed, 0 failed, 0 skipped**.
- Complete unit suite: **65 passed, 0 failed, 0 skipped**.
- Strict assertions now observe **401** for missing, invalid, expired and
  logged-out authentication, and **403** for authenticated student attempts on
  administrator views and actions. Data and inventory protection checks still pass.
- Each integration run reports one existing Starlette/httpx deprecation warning;
  the unit run reports 13 existing `datetime.utcnow()` deprecation warnings.
- Ruff formatting/lint checks pass for all test files. Checks on the two edited
  application files still report the same three pre-existing lint findings
  (`I001`, `BLE001`, `RUF100`) and pre-existing formatting differences. Baseline
  comparison found no new lint findings; unrelated cleanup was intentionally avoided.

Only the guarded A2 test database was connected to for integration verification.
No additional integration cases or API endpoints were implemented.
