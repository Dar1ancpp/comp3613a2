# Isolated Postman environment

This profile uses only repository-local `a2_postman.db`. Development continues to
use `a2_development.db`; pytest integration fixtures continue to use `a2_test.db`.
No REST endpoints or Postman collection are provided by this setup stage.

Run these commands from the `comp3613a2` repository in a dedicated PowerShell
terminal. If it has an incompatible inherited `ENV`, explicitly select Postman:

```powershell
$env:ENV = "postman"
python -B -m app.postman configure
python -B -m app.postman check
python -B -m app.postman init
python -B -m app.postman run
```

`configure` is a one-time command. It creates the ignored `.env.postman` with a
random signing key and random local account passwords, and refuses to overwrite
an existing file. The committed `.env.postman.example` contains no usable secrets.
No fallback to development or pytest environment files is allowed. Inherited
database overrides are validated, not silently discarded.

`check` inspects settings and the engine without connecting. `init` creates missing
tables and inserts missing fixtures without dropping, clearing or overwriting data.
Run `init` again while the server is stopped to safely ensure prerequisites exist.

The server binds only to **http://127.0.0.1:5001**, without reload or access logging.
The configuration console is disabled. `Ctrl+C` stops the server and releases its
database lock. Normal `manage.py run` also refuses Postman host/port/reload overrides.

## Dedicated fixtures

- `postman_student`: student with no initial submissions or redemptions.
- `postman_peer`: student with one approved 10-hour baseline submission.
- `postman_admin`: administrator and baseline reviewer.
- `Postman Bronze` / `Postman Silver`: milestone thresholds 10 / 25.
- No Awards or redemptions are seeded; later collection requests can create them.

Student/peer passwords come from `POSTMAN_STUDENT_PASSWORD`; the administrator
password comes from `POSTMAN_ADMIN_PASSWORD` in the ignored `.env.postman`.
Read them locally when configuring Postman; do not commit, screenshot or log them.
Existing fixture accounts are verified and never silently reset or overwritten.
Initialization preserves any workflow records created in earlier runs.

## Explicit reset for a future clean collection run

Stop the Postman server first. Reset is optional and destructive **only to the
dedicated Postman data**. It requires the exact absolute path, an exclusive lock,
a validated Postman engine and a schema containing only known application tables.

First inspect the planned operation without changing records:

```powershell
python -B -m app.postman reset --confirm-database "C:\Users\daria\Desktop\UWI\COMP3613\Assignments\A2\comp3613a2\a2_postman.db" --dry-run
```

To deliberately clear the Postman tables and restore the baseline, use the same
command **without `--dry-run`**. No reset is part of normal initialization or startup.
The general `drop_all` helper refuses Postman resets, and the general demo seed
command refuses to introduce its default accounts into this profile.

Startup, request sessions, CLI sessions and recovery share the guarded engine.
Connection creation, pool checkout and SQL execution recheck the exact target,
profile and regular/unlinked database files (including SQLite sidecars). Remote
databases, development/test files, symlinks and hardlinks are refused. SQL echo is
off, SQL parameters are hidden and database error logging omits exception values.

Initialization/reset and the server lifespan share `.a2_postman.lock`. A second
server or preparation command refuses to proceed while that lock exists. If a
process crashes, verify it is no longer running before manually removing its stale
lock; commands never remove another process's lock automatically.

Keep `.env.postman`, database files and the lock out of Git. The example profile
and this guide are safe to commit. Use a separate fresh terminal for pytest; its
existing fixtures intentionally reject an inherited `ENV=postman`.
