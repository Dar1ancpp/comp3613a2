# Student Awards A2 Postman collection

This Collection v2.1 export contains **25 ordered requests** in five folders. It
exercises all **15 REST operations** using the actual application and only the
repository-local `a2_postman.db` at **http://127.0.0.1:5001**. No pytest cases or
application changes are needed to run it.

## 1. Prepare the isolated server

Use a dedicated PowerShell terminal in the `comp3613a2` repository:

```powershell
$env:ENV = "postman"
# One time only, if .env.postman does not already exist:
python -B -m app.postman configure
python -B -m app.postman check
python -B -m app.postman init
python -B -m app.postman run
```

`configure` generates ignored private credentials and refuses to overwrite an
existing `.env.postman`. `check` validates the exact database target and logging
configuration without connecting. `init` creates missing tables and fixtures
without clearing existing records. The server holds an exclusive database lock
and binds only to `127.0.0.1:5001`; startup, request sessions and recovery use the
same guarded Postman engine. Do not use a development server for this collection.

Begin each complete run with the clean Postman fixtures: `postman_student` has
no submissions/redemptions, `postman_peer` has 10 approved hours, and the Bronze
and Silver milestones require 10 and 25 hours. No Awards are seeded. If the
database already contains workflow data from a previous attempt, follow the
guarded reset procedure below first. **Initialization alone does not reset it.**

## 2. Import and set private credentials

1. In Postman, import `student-awards-a2.postman_collection.json` and
   `student-awards-a2.postman_environment.example.json` from this directory.
2. Select the imported **Student Awards A2 - LOCAL Postman only** environment.
3. Leave `base_url` as `http://127.0.0.1:5001` and `profile` as `postman`.
4. In your local/private environment values, set `student_password` from
   `POSTMAN_STUDENT_PASSWORD` and `admin_password` from `POSTMAN_ADMIN_PASSWORD`
   in your ignored `.env.postman`. Keep the usernames `postman_student` and
   `postman_admin`. Do not share/publish these password values.

The committed environment has blank passwords. The `secret` type masks the UI;
it does not make an exported password safe to commit. Keep populated local CLI
environments under `*.local.postman_environment.json`, which Git ignores.

## 3. Run the complete collection

Open the collection's **Run** action and select every request in the saved
folder order. Use **one iteration**, no iteration-data file and no URL/variable
overrides. Disable saving response bodies and saving cookies after the run.
Run the whole collection from request **01**; later requests depend on earlier
IDs and role sessions, so running an isolated folder is insufficient.

The collection performs these journeys:

- **Authentication (2):** student and administrator login, safe public user
  details and HttpOnly cookie checks.
- **Volunteer Hours and Progress (5):** submit 10 hours, read the Pending queue,
  approve, read the student's persisted history, and check milestones and the
  tied leaderboard against the seeded peer.
- **Award Management (3):** create an inactive Award, update/activate the same
  record with one item in stock, and verify eligibility through the catalogue.
- **Redemption Processing (11):** request, reject a duplicate, verify unchanged
  hours/stock, inspect the queue, approve and verify one inventory deduction,
  fulfill and verify no further deduction, request again at zero stock, persist
  the automatic Rejected outcome, and read private history.
- **Authorization and Error Handling (4):** student/admin restriction (403),
  invalid hours (422), logout (204), and anonymous access after logout (401).

IDs are captured dynamically in collection variables. No database record IDs
are hard-coded. Award names get a unique run suffix. JWT cookies are captured
from `Set-Cookie` into separate **run-local** student/admin variables, never
saved into collection/environment variables. Every request disables the cookie
jar and redirects; the pre-request script replaces the Cookie header using the
request's explicit role. Anonymous requests send no role cookie.

The collection-level guard rejects any other base URL or profile before sending
requests, including writes. It stops the run and skips the request. An older
runtime without skip support first receives an inert loopback URL on port 1,
so a script failure cannot send the original request elsewhere. Use a current
Postman desktop Runner or CLI supporting `pm.execution.skipRequest()`.

The URL guard cannot independently discover a server's database. The mandatory
`app.postman check` / `app.postman run` commands establish the server profile and
exact database target. Do not replace that server with another process.

## 4. Interpret results

Successful HTTP outcomes are **200**, **201** and the empty **204** logout.
Intentional **401**, **403**, **409** and **422** responses pass when their
matching `pm.test` assertions succeed. Out-of-stock approval deliberately
returns **200** with `redemption.status = "rejected"`, preserving the application's
existing business rule. Requests do not spend verified hours or stock; only
approval deducts stock, and fulfillment does not deduct it again.

Expect **25 requests and 77 passing assertions**, with no failed assertions or
script errors. A skipped request, missing ID, failed login or network error is
not successful completion. Investigate failures before resetting/rerunning;
preserve only sanitized evidence. This collection covers representative API
journeys; the finalized pytest suite retains detailed boundary/transition cases.

## 5. Repeat a run safely

Stop the Postman server with **Ctrl+C** first. From the repository root in the
same Postman-profile terminal, verify the exact target before a deliberate reset:

```powershell
$env:ENV = "postman"
python -B -m app.postman check
$postmanTarget = Join-Path (Resolve-Path .).Path "a2_postman.db"
python -B -m app.postman reset --confirm-database $postmanTarget --dry-run
# Only after the dry-run confirms the dedicated Postman target:
python -B -m app.postman reset --confirm-database $postmanTarget
python -B -m app.postman run
```

Reset clears only this dedicated Postman schema and restores its fixture data.
It requires the exact absolute `a2_postman.db` path, guarded settings/engine,
known schema and exclusive lock. It rejects development/test/remote targets and
linked files. Never substitute `a2_development.db`, `a2_test.db`, a PostgreSQL
URL or another repository. Never delete a lock while its server is running.

Run the complete collection once again. Request 01 clears old IDs and local
cookies. A partial run also requires a reset before restarting, because the
milestone expectations intentionally assume the clean fixture baseline.

## Optional local CLI execution

The desktop Runner needs no CLI login. For CLI execution, while the guarded
server is running, prepare an ignored local environment without printing secrets:

```powershell
$env:ENV = "postman"
@'
import json
from pathlib import Path
from app.postman import select_profile, require_settings
select_profile()
settings = require_settings()
template = Path("postman/student-awards-a2.postman_environment.example.json")
environment = json.loads(template.read_text(encoding="utf-8"))
private = {
    "student_password": settings.postman_student_password.get_secret_value(),
    "admin_password": settings.postman_admin_password.get_secret_value(),
}
for entry in environment["values"]:
    if entry["key"] in private:
        entry["value"] = private[entry["key"]]
Path("postman/student-awards-a2.local.postman_environment.json").write_text(
    json.dumps(environment), encoding="utf-8"
)
'@ | python -B -
postman collection run postman/student-awards-a2.postman_collection.json -e postman/student-awards-a2.local.postman_environment.json --no-report-events --ignore-redirects --bail
Remove-Item -LiteralPath "postman/student-awards-a2.local.postman_environment.json"
```

Cloud publishing is unnecessary. Keep `--no-report-events`; do not export cookie
jars or verbose/raw reports containing sessions. The installed CLI may display
a login/publishing notice even when the local collection succeeds; use the
request/assertion summary and exit code to assess the local run.

## Verification recorded on 27 October 2026

The exported collection ran against the actual guarded Postman server: **25
requests, 77 assertions, zero failures, exit code 0**. No database reset was
needed; initialization confirmed the clean fixture baseline. The server was
stopped after verification.

Both JSON artifacts parsed successfully; saved JavaScript syntax was checked
for all 27 scripts, and a comparison against the application's OpenAPI schema
confirmed coverage of **15/15 REST operations**. The Postman CLI accepted and
executed the v2.1 export. A separate deliberate guard check used the same CLI
command with `--env-var base_url=http://127.0.0.1:5999`: it failed the safety
assertion as intended, sent **zero HTTP requests**, and exited with code 1.

Application code, the existing 24 unit/32 integration tests and finalized test
plans were unchanged. No pytest execution was needed for these collection-only
artifacts. UAT has since been completed through Playwright-assisted visible
Microsoft Edge interactions: all **17 cases were reviewed and approved PASS**,
with **38 official screenshots**. The authoritative records are the
[finalized UAT report](../docs/a2/uat-execution-report.html) and
[review summary](../docs/a2/uat-review-summary.md). Personal tester details,
the official acceptance decision and signature remain for the student to
complete. An [A2 report draft](../docs/a2/final-report-draft.md) has been
prepared for student review; the final PDF has not been generated.

References: [Postman runtime cookie/redirect settings](https://github.com/postmanlabs/postman-runtime/blob/develop/docs/protocol-profile-behavior.md)
and [Postman request-skipping API](https://learning.postman.com/latest-v-12/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-execution).
