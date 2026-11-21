# Local dev and testing guide

Run the whole DITF ticketing stack on one machine and test every client against the backend: **web portal** (visitors),
**client portal** (admin back office) and **mobile app** (agents and gate staff). Run commands from the workspace root
(`ditf-workspace`). Nothing here edits a submodule: settings come from environment variables and git-ignored files.
Each submodule's own README stays the reference for its internals; this guide is the glue between them.

## 1. The picture

```
 Web portal  :4200 ──────────────▶ Public API :9096 ─┐
 (visitors: book, pay, find ticket)                    ├──▶ PostgreSQL :5432 (container ditf-pg)
 Client portal :5000 ─┐                                │
 Mobile app ──────────┴─────────▶ Admin API  :9097 ───┘     both APIs are the same code (dg-tms-api);
 (admin, agents, gate staff)                                  the admin one starts with -Dapp.module=admin

 Public API ──▶ DGePay (payments)   ──▶ S3 (ticket PDFs)      not reachable locally -> mocks, see section 5
```

| App | Folder | Port | Talks to | Needs |
|---|---|---|---|---|
| Database | `docker-compose.dev.yml` | 5432 | | Docker Desktop |
| Public API | `dg-tms-api` | 9096 | DB, DGePay, S3 | JDK 21 |
| Admin API | `dg-tms-api` (`app.module=admin`) | 9097 | DB | JDK 21, `ADMIN_TOKEN_SECRET` |
| Web portal | `dg-tms-web-portal` | 4200 | public API | Node 22.12+ |
| Client portal | `dg-tms-client-portal` | 5000 | admin API | Node 22.12+ |
| Mobile app | `dg-tms-mobile-app` | | admin API | Flutter 3.50 |

The clients' API addresses are already set for local use (`environment.development.ts`, `env/dev.json`), and their AES
key equals the API's `platform_secret_key`. Nothing to configure for the web apps.

## 2. One-time setup

1. `git submodule update --init` (or clone with `--recurse-submodules`).
2. Install: Docker Desktop (running), JDK 21, Node 22.12+, PowerShell. Flutter 3.50 only for the mobile app (not
   installed on this machine yet). Python 3 with `pip install cryptography` only for the payment mocks.
3. Database: `docker compose -f docker-compose.dev.yml up -d`, then `.\scripts\seed\seed.ps1` (repeatable).
   Check: `docker exec ditf-pg pg_isready -U ditf -d ditf`. Connection string: `postgresql://ditf:ditf@localhost:5432/ditf`.
4. `cd dg-tms-web-portal; npm install` and `cd dg-tms-client-portal; npm install` (`dev.ps1` also does this if missing).
5. API settings file for IntelliJ and terminal runs, `dg-tms-api\.env` (git-ignored; `dev.ps1` passes the same values itself):
   ```
   QUARKUS_DATASOURCE_JDBC_URL=jdbc:postgresql://127.0.0.1:5432/ditf
   QUARKUS_DATASOURCE_USERNAME=ditf
   QUARKUS_DATASOURCE_PASSWORD=ditf
   STORAGE_ENDPOINT=http://127.0.0.1:9
   ```
   The password is required (the committed default is empty). Use `127.0.0.1`, not `localhost`. `STORAGE_ENDPOINT` points
   at a dead address on purpose: `application.properties` ships real S3 credentials, and a local run must not write
   ticket PDFs to that shared bucket.
6. Mobile app only: `cd dg-tms-mobile-app; copy env\dev.example.json env\dev.json` (git-ignored; works as is).

## 3. Starting everything

```powershell
.\scripts\dev.ps1 up                  # database + both APIs + both web apps, one window each
.\scripts\dev.ps1 up -MockPayments    # same, plus fake DGePay/S3/media: payments and ticket PDFs work (section 5)
.\scripts\dev.ps1 up -NoApi           # without the APIs: run those from IntelliJ (section 4)
.\scripts\dev.ps1 status              # which ports are listening
.\scripts\dev.ps1 down                # stop the apps (-Db also stops the database)
```

Ready when `status` shows UP and `http://localhost:9096/ticket-booking/health` and `http://localhost:9097/ticket-booking/health`
answer. The first API start downloads Maven and compiles, so give it a minute. Personal overrides go in
`scripts\dev.local.env` (`KEY=VALUE` per line, git-ignored), for example `SCANNER_KEYS=gate-1:<openssl rand -hex 24>` to
switch on the public gate-scan endpoint, or `PAYMENT_RECONCILE_INTERVAL=off` to silence the background payment checker.

Without `-MockPayments`, **initiate-payment cannot work** (no DGePay credentials): the web portal shows
`SOMETHING_WENT_WRONG`. Everything else works.

The mobile app is not started by the script: `cd dg-tms-mobile-app; flutter pub get;
flutter run --dart-define-from-file=env/dev.json`. Emulator: `BASE_URL` `http://10.0.2.2:9097/` (already in
`dev.example.json`). Physical phone: set `BASE_URL` to `http://<PC LAN IP>:9097/`, same Wi-Fi, and allow port 9097 in
Windows Firewall. Run `dart run build_runner build` only after changing freezed/json models.

## 4. Running and debugging the API from IntelliJ IDEA

Open the **`dg-tms-api` folder** as the project (File > Open > `ditf-workspace\dg-tms-api`), JDK 21 in Project Structure
and in Settings > Build Tools > Maven > Runner JRE. Start the rest with `.\scripts\dev.ps1 up -NoApi`. Four run
configurations are in `dg-tms-api\.idea\runConfigurations` (git-ignored, local only):

| Configuration | Use |
|---|---|
| `Quarkus Dev` | public API on 9096 (debug port 5005) |
| `Quarkus Dev (admin)` | admin API on 9097 (debug port 5006, log file `logs/admin.log`, admin token secret set) |
| `Attach Quarkus (Public)` / `(Admin)` | Remote JVM Debug to `localhost:5005` / `5006` |

Run `Quarkus Dev`, wait for `Listening on: http://0.0.0.0:9096`, then press Debug on `Attach Quarkus (Public)`. Do not
press Debug on the Maven configuration itself: that debugs Maven. Code changes reload on the next request.
A bare terminal run is `cd dg-tms-api; .\mvnw.cmd quarkus:dev`; the admin one adds
`"-Dapp.module=admin" "-Ddebug=5006"` and env `ADMIN_TOKEN_SECRET` (32+ characters), `QUARKUS_HTTP_PORT=9097`,
`QUARKUS_LOG_FILE_PATH=logs/admin.log`.

## 5. Payments and ticket PDFs locally

Real DGePay and S3 are not reachable. `dev.ps1 up -MockPayments` starts the test suite's fake gateway
(`dg-tms-api/src/test/e2e/mock_dgepay.py`: fake DGePay on 18080 with the real AES/HMAC checks, fake S3 on 18090) plus
`scripts/mock_media.py` (18091, serves the saved PDFs) and points the public API at them. Restart the public API after
switching modes, because settings are read at startup.

Run only the shared pieces (no apps) with `.\scripts\dev.ps1 infra`: database, mock gateway, mock checkout page
(`scripts/mock_checkout.py`, 18081: the API talks to this; it forwards to the gateway on 18080 and swaps the
`checkout.mock` link for a page with Pay / Fail buttons), mock S3 and media. It prints the env vars to put in the
IntelliJ run configs (`DGEPAY_BASE_URL` must be `http://127.0.0.1:18081/payment_gateway`). Restart the API after changes.
**`dg-tms-api/.env` wins over what you expect**: Quarkus reads it, so its `DGEPAY_BASE_URL` must be the 18081 one and it
should also set `APP_PAYMENT_RESULT_REDIRECT_URL=http://localhost:4200/txn-status` (else the callback redirects to production).

Full test, as the visitor:

1. `.\scripts\dev.ps1 infra`, then `.\scripts\dev.ps1 status`: DB, mock DGePay 18080, mock checkout 18081 and mock media 18091 are UP.
2. Start the public API (:9096) from IntelliJ with the printed env, then `cd dg-tms-web-portal; npm start` (:4200).
3. Book on `http://localhost:4200` and press pay. The browser lands on `http://localhost:18081/pay/<id>`.
4. Press **Pay**: the API settles the payment and the browser returns to `http://localhost:4200/txn-status`, which waits
   for the ticket and shows the download links (PDF from `http://127.0.0.1:18091/...`).
5. Press **Fail** on another booking: `/txn-status` shows the failed state and the booking can be paid again.
6. Check: `/find-ticket` (phone + ticket number) finds the booking; the API log has no `ERROR`.

Without the browser, `.\scripts\mock-pay.ps1` (or `-Fail`, `-Booking <number>`) does the same as the buttons.

What stays different from production: DGePay's server-to-server IPN is never sent (the callback alone settles the
payment, which is enough); the PDFs are kept in `%TEMP%\ditf-mock-uploads`.

## 6. Test data

Seeded by `seed.ps1`; every seeded id starts with `5eed5eed`. All PINs are `1234`.

| Who | Login | Use |
|---|---|---|
| Admin | `01900003001` | client portal (everything) |
| Admin staff | `01900005001`..`003` | client portal, limited |
| Agent | `01900001001`..`010` | mobile: sell tickets. `01900001010` has zero balance ("Insufficient balance." test) |
| Ticket scanner | `01900002001` | mobile: gate scan |
| QR staff / scanner / ticket generator | `01900006001` / `01900007001` / `01900008001` | client portal and mobile roles |

Public bookings (web portal `/find-ticket`, phone + ticket number):

| Phone | Ticket number | State |
|---|---|---|
| `01711000001` | `7700000001` | paid, not scanned (the happy path) |
| `01711000004` | `7700000004` | paid, already scanned: the API answers `TICKET_ALREADY_USED` |
| `01711000002` | `7700000002` | pending |
| `01711000003` / `01711000005` | `7700000003` / `7700000005` | failed / never paid |

Checked against the running API: the first row returns the booking and its links; the second returns `TICKET_ALREADY_USED`;
a phone that does not belong to the booking returns `TICKET_NOT_FOUND`.

Seeded ticket links are placeholders (`https://example.invalid/...`), so Download on a seeded booking opens a dead page.
Only a booking you pay yourself with `-MockPayments` has a real PDF.

## 7. Test scenarios (what to click, what you should see)

**A. Web portal, visitor** (public API; payment steps need `-MockPayments`)
1. `http://localhost:4200`: prices and bus routes load (needs the seeded `booking_configs`).
2. Fill the form (phone `01XXXXXXXXX`, 11 digits), try coupon `DgePay10` and a referral code, submit. The server
   re-prices the booking itself; the amount the page sends is ignored.
3. Pay: `mock-pay.ps1`, then `/txn-status` as in section 5. Expected: status becomes paid, download links appear.
4. `/find-ticket` with the phone and the new ticket number (shown on the status page). Expected: the same links.
   With the seed values from section 6 you get the paid booking; wrong values return an error, and repeated wrong
   guesses are rate limited by the API.
5. Failure path: `mock-pay.ps1 -Fail`. Expected: the booking ends as failed (`txn_status` 4). The API accepts a new
   payment on the same booking (a new attempt id); whether the page offers a retry button is not documented, so check.

**B. Client portal, admin** (admin API on 9097, nothing else needed)
1. `http://localhost:5000`, log in `01900003001` / `1234`.
2. Dashboard figures load; the bookings list shows the seeded and your new bookings.
3. Agents: top up agent `01900001001` and watch the ledger (`user-transaction-ledger`) and the balance change.
4. Ticket search finds a ticket by number; the scan history shows scans.
5. Bulk ticket batch: starts a background job; the page polls `background-job/{id}` until it ends.
A 401 sends you back to `/login`, a 403 shows "not allowed".

**C. Mobile app, agent and gate** (admin API on 9097)
1. Log in as agent `01900001001`. The balance shows.
2. Sell a ticket. One call prices it, debits the balance and stores the booking as paid. The agent `01900001010` must be
   refused with "Insufficient balance."
3. Log in as scanner `01900002001`, scan a gate barcode (`2` + 11 digits; `200000100001` is booking 1). A second scan of
   the same barcode must be refused.
4. Cross-check: the sale appears in the client portal's bookings list and in the agent's ledger; a ticket just scanned
   on the phone is "already scanned" in the web portal's find-ticket.

## 8. Seeing the data (it is encrypted)

The request bodies and most response `data` fields are AES-128-ECB with the API's `platform_secret_key`.

```powershell
.\scripts\aes.ps1 d "<request body from DevTools>"                      # to readable JSON
.\scripts\aes.ps1 d '{"success":1,"error":[],"data":"<...>"}'           # a whole response works too
.\scripts\aes.ps1 e '{"booking_master_id":"<id>","payment_method":"bkash"}'   # to replay a call with curl/Postman
```

Errors are plain `{"success":0,"error":["CODE"]}`. **`SOMETHING_WENT_WRONG` always means an unexpected exception:** open
`dg-tms-api\logs\application.log` (admin API: `logs\admin.log`) and search for `Unexpected error`; the stack trace names
the cause. A database look: `docker exec ditf-pg psql -U ditf -d ditf -c "select booking_number, txn_status, txn_id from booking_master order by created_date desc limit 5"`
(`txn_status`: 1 pending, 2 processing, 3 paid, 4 failed).

## 9. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `no password was provided` | `QUARKUS_DATASOURCE_PASSWORD` not set, or `dg-tms-api\.env` not found (run from `dg-tms-api`). |
| `Connection refused` on 5432 | Container stopped (`docker start ditf-pg`), or another PostgreSQL owns the port. |
| `password authentication failed` | The app reached a different PostgreSQL. Use `127.0.0.1` in `.env`. |
| Admin API exits at startup | `ADMIN_TOKEN_SECRET` missing or shorter than 32 characters. |
| Admin API: "port 9096 already in use" | `QUARKUS_HTTP_PORT=9097` not set for that run. |
| Client portal login or network errors | The admin API (9097) is not running; the portal does not use 9096. |
| Web portal `SOMETHING_WENT_WRONG` on pay | No DGePay credentials (log: `HMAC failed` / `Empty key`). Use `-MockPayments`, then restart the public API. |
| `PAYMENT_GATEWAY_ERROR` on pay | The gateway rejected or could not be reached; the log has `DGePay /initiate_payment failed ...`. With the mock: are 18080 and 18081 running, and is `DGEPAY_BASE_URL` the 18081 one? |
| Find Ticket button does nothing | The form is invalid and the page shows no message: phone must be exactly 11 digits and the second field filled. |
| Download opens `example.invalid` | Seeded placeholder link. Pay a booking with `-MockPayments` to get a real one. |
| `/txn-status` waits for 2 minutes | PDF not made: the API cannot reach storage (check `-MockPayments` and `STORAGE_ENDPOINT`). The booking is still paid. |
| `mock-pay.ps1`: "mock never saw checkout" | That attempt predates the mock or the API ran without `-MockPayments`. Start a new payment. |
| A pending booking after a failed pay | A payment attempt is recorded before the gateway call; a failure that is not a gateway error does not undo it. Pay again on the same booking, or ignore it. |
| Mobile: configuration error screen | An empty value in `env\dev.json`. |
| Mobile cannot reach the API | Emulator: `10.0.2.2`. Phone: the PC's LAN IP, not `localhost`, plus the firewall rule. |
| `release version 21 not supported` | Maven Runner JRE is not JDK 21. |

Reset: `.\scripts\seed\seed.ps1` restores the seeded rows and fresh dates (it keeps your own data). Clean slate:
`docker compose -f docker-compose.dev.yml down -v`, then `up -d` and `seed.ps1`.
