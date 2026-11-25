# API tests

Black-box tests of the public API (:9096) and admin API (:9097) against the **local dev stack**. Nothing in a submodule is
touched: the AES key is read (read-only) from `dg-tms-api/.../application.properties`, and the endpoint list for the
coverage table is scanned from the API source.

```powershell
.\scripts\test.ps1 -Up -Open      # start the stack if needed, run every case in order, open reports\api\latest.html
.\scripts\test.ps1 -Only 04       # one case file;  -FailFast stops at the first failing case
.\scripts\test.ps1 -Fast          # ~20 s: skips the case that waits ~2 min for the payment reconciliation timer (full run ~2.5 min)
```

Needs the stack from `.\scripts\dev.ps1 up -MockPayments` (the payment cases use the fake DGePay/S3), the seed data
(`scripts\seed\seed.ps1`, run by dev.ps1), and `pip install cryptography jinja2`. The runner refuses non-local URLs.
Exit code is 0 only if every case passes.

Output (git-ignored, in `reports\api\`): `latest.html`, `report-<timestamp>.html` (self-contained, shareable), `results.json`.
The report shows totals, pass rate, environment and submodule SHAs, every assertion with expected/actual on failure,
each request and decrypted response (PINs/tokens masked), the slowest calls, and which API endpoints the run did / did not hit.

## What is covered
Every endpoint declared in the API source (44/44; the report lists any that stop being hit) with edge cases: auth/roles, validation,
concurrency (parallel IPN/callback, parallel gate scans, wallet), payment retries and gateway faults, lockouts, scoping per role.
Background jobs (report table, discovered from the source): ticket batch generation + resume, payment `ReconciliationJob`
(runs on its real timer: dev defaults 120 s tick, 180 s minimum age; skipped if `PAYMENT_RECONCILE_INTERVAL=off` in `scripts/dev.local.env`),
`DbSetup` partition upkeep. **Not covered:** `AttemptLimiter`'s periodic cleanup (the lockout behaviour itself is tested; the cleanup is not observable via the API).
Also covered: app-version filter (406), duplicate booking request ids, undecryptable bodies, tampered admin tokens, bus seat pricing and the bus PDF,
dashboard numbers cross-checked against SQL, DB invariants (schema version, unique barcodes, partition pruning), and the **public gate scan with real
device keys** (needs `SCANNER_KEYS=gate-1:<24+ chars>,gate-2:<24+ chars>` in `scripts/dev.local.env` and the public API started with it; those cases SKIP otherwise).
**Known issue (reported, does not fail the run):** the server does not enforce `max_ticket_quantity` / `max_seat_count`; it accepts 11 adults and 5 seats.
Mark a case like that with `@case(..., known_issue="why")`: it shows as KNOWN while it fails and flags itself when the defect is fixed.
Job states the API cannot produce (failed or interrupted batch) are forced by editing `background_job` rows in the dev database.

## Layout
`client.py` HTTP + AES + DB/mock helpers · `helpers.py` shared steps (pay a booking, scan codes) · `runner.py` runs cases in file order, builds the report · `report/template.html`
· `cases/NN_*.py` the cases.

## Adding a case
```python
from client import adm
from runner import case

@case("What it proves")
def my_case(t):
    t.need("admin_token")                        # SKIP (not FAIL) if an earlier case did not provide it
    r = adm("GET", "/coupons", token=t.ctx["admin_token"])
    t.check("lists coupons", r.status == 200, r.json)   # third argument is shown only when the check fails
```
Cases run in file-name order and share `t.ctx`. The suite is rerunnable: it creates its own records (random phone numbers,
`AUTOTEST` names) and never edits seed rows; it does leave those records in the dev database.
Login and ticket-lookup lockouts are keyed by phone, so cases that provoke them must use throwaway users/phones (see `07_users_and_roles.py`), never seeded accounts.
