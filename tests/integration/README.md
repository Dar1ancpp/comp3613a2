# A2 integration-test infrastructure

Run from the `comp3613a2` root in a fresh process:

```powershell
python -B -m pytest tests/integration/test_startup_database_isolation.py -v
```

The integration-only `conftest.py` selects `ENV=test` before application imports.
It rejects an incompatible inherited `ENV`/database override, early application
configuration imports, unexpected engines, linked database files, external
network connections and parallel workers. Only the exact repository-local
`a2_test.db` target is permitted. No development server or Render access is used.
On Windows, only the standard library's internal loopback socket-pair operation
is permitted for asyncio startup; application HTTP/network connections remain
blocked. TestClient HTTP requests stay in process.

Every case owns a fresh disposable schema. Setup and teardown drop only guarded
test tables; teardown also removes committed fixture data. Lifespan creates the
tables. The database file remains local and Git-ignored after cleanup.

Fixtures for later cases: `client` runs real lifespan with redirects disabled;
`db_session` provides a real setup session; `session_factory()` opens independent
verification sessions; `test_engine` exposes the guarded application engine.
Commit intended setup data explicitly and let the fixtures close sessions and
clear the schema. Add actor/data factories only when their cases are implemented.

Runs are serial and use an exclusive repository-root `.a2_integration.lock`. The
lock inherits the repository's access permissions rather than depending on a
pytest cache directory that may be private to another Windows account. Disabling
pytest's cache provider does not disable the integration database lock.

For a complete run without accessing pytest's optional cache:

```powershell
python -B -m pytest -p no:cacheprovider tests/integration -v --tb=short
```

If a crash leaves this lock behind, first verify no integration pytest process is
running; only then remove that lock file. The harness never deletes another run's
lock automatically. Unit-only runs do not load these integration fixtures.
