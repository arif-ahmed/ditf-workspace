# Local dev, one app at a time

Run all commands from the workspace root (`ditf-workspace`) unless a step says otherwise. Nothing here edits a
submodule; settings come from environment variables or git-ignored files. To start everything at once instead:
`.\scripts\dev.ps1 up`.

Start order: **0 Database → 1 Public API → 2 Admin API → 3 Web portal / 4 Client portal → 5 Mobile app.**
Each app only needs the pieces before it that it talks to (see "Needs" under each).

## 0. Database (needed by both APIs)

Prerequisites: Docker Desktop running.

1. First time only: `docker compose -f docker-compose.dev.yml up -d`
   Later: `docker start ditf-pg`
2. Load the schema and demo data (repeatable): `.\scripts\seed\seed.ps1`
3. Check: `docker exec ditf-pg pg_isready -U ditf -d ditf` prints "accepting connections".

Connection string: `postgresql://ditf:ditf@localhost:5432/ditf`.

## Running and debugging the API from IntelliJ IDEA (recommended for the backend)

Open the **`dg-tms-api` folder** itself as the project (File > Open > `ditf-workspace\dg-tms-api`), not the workspace
root, so it is imported as the Maven project the API README describes. Set JDK 21 in File > Project Structure > SDK and
in Settings > Build Tools > Maven > Runner JRE. Then start the rest without the APIs:
`.\scripts\dev.ps1 up -NoApi`.

Four run configurations are already prepared in `dg-tms-api\.ideaunConfigurations` (git-ignored, local only):

| Configuration | Use |
|---|---|
| `Quarkus Dev` | public API on 9096 (debug port 5005) |
| `Quarkus Dev (admin)` | admin API on 9097 (debug port 5006, own log file); includes the admin token secret |
| `Attach Quarkus (Public)` | Remote JVM Debug to `localhost:5005` |
| `Attach Quarkus (Admin)` | Remote JVM Debug to `localhost:5006` |

To debug: press **Run** on `Quarkus Dev`, wait for `Listening on: http://0.0.0.0:9096`, then press **Debug** on
`Attach Quarkus (Public)` and set breakpoints. Do not use Debug on the Maven configuration itself: that debugs Maven.
Same for admin with the two admin configurations. Code changes reload on the next request.

`dg-tms-api\.env` (local, git-ignored) supplies the database settings and sends ticket storage to an unreachable
address. If the IDE does not pick up the Maven project, open the Maven tool window and add `pom.xml`.

Steps 1 and 2 below are the same thing from a terminal.

## 1. Public API (`dg-tms-api`, port 9096)

Needs: database. Prerequisites: JDK 21 (the `mvnw` wrapper downloads Maven).

1. Settings. Either use `dg-tms-api\.env` (already git-ignored locally) containing:
   ```
   QUARKUS_DATASOURCE_JDBC_URL=jdbc:postgresql://127.0.0.1:5432/ditf
   QUARKUS_DATASOURCE_USERNAME=ditf
   QUARKUS_DATASOURCE_PASSWORD=ditf
   ```
   or set the same variables in the terminal. The password is mandatory; the committed default is empty.
2. Optional, so a payment return comes back to your machine instead of production:
   ```powershell
   $env:APP_PUBLIC_BASE_URL = "http://localhost:9096"
   $env:APP_PAYMENT_RESULT_REDIRECT_URL = "http://localhost:4200/txn-status"
   ```
3. Do not let ticket PDFs reach the shared bucket whose credentials are committed in `application.properties`:
   `$env:STORAGE_ENDPOINT = "http://127.0.0.1:9"` (or point `STORAGE_*` at a local MinIO).
4. Run:
   ```powershell
   cd dg-tms-api
   .\mvnw.cmd quarkus:dev
   ```
5. Check: `http://localhost:9096/ticket-booking/health`. Dev UI: `http://localhost:9096/qdev`. The schema is applied
   at startup.

Not available locally: real payments (needs DGePay `DGEPAY_CLIENT_ID`, `DGEPAY_CLIENT_SECRET`, `DGEPAY_API_KEY`).
Gate-scan endpoint stays off until `SCANNER_KEYS=gate-1:<openssl rand -hex 24>` is set.

## 2. Admin API (`dg-tms-api`, port 9097)

Needs: database. Same code as step 1 with `-Dapp.module=admin`. Use a second terminal.

1. Settings as in step 1, plus:
   ```powershell
   $env:ADMIN_TOKEN_SECRET = "dev-only-secret-at-least-32-characters-long"   # 32+ characters, or it refuses to start
   $env:QUARKUS_HTTP_PORT = "9097"                                           # otherwise it clashes with 9096
   $env:QUARKUS_LOG_FILE_PATH = "logs/admin.log"                             # keep the two APIs' logs apart
   ```
2. Run:
   ```powershell
   cd dg-tms-api
   .\mvnw.cmd quarkus:dev "-Dapp.module=admin" "-Ddebug=5006"
   ```
3. Check: `http://localhost:9097/ticket-booking/health`.

## 3. Web portal (`dg-tms-web-portal`, public booking page, port 4200)

Needs: public API (step 1). Prerequisites: Node 22.12+.

1. Once, and after `package.json` changes: `cd dg-tms-web-portal; npm install`
2. Run: `npm start`
3. Open `http://localhost:4200`. It already calls `http://localhost:9096` (`environment.development.ts`); the AES key in
   `app-config.ts` matches the API. Nothing to configure.
4. Demo lookups on `/find-ticket`: phone `01711000001`, booking number `7700000001`.

## 4. Client portal (`dg-tms-client-portal`, admin back office, port 5000)

Needs: admin API (step 2). Prerequisites: Node 22.12+.

1. Once: `cd dg-tms-client-portal; npm install`
2. Run: `npm start` (it serves on **5000**; 4300 is only the Docker/nginx port).
3. Open `http://localhost:5000`. It already calls `http://localhost:9097`. Nothing to configure.
4. Log in: phone `01900003001`, PIN `1234` (admin).

## 5. Mobile app (`dg-tms-mobile-app`, Flutter)

Needs: admin API (step 2). Prerequisites: Flutter 3.50 / Dart 3.14 (not installed on this machine yet), Android
Studio with an emulator, or a USB phone.

1. `cd dg-tms-mobile-app; flutter pub get`
2. Settings: `env\dev.json` (git-ignored, already present). Defaults point to `http://10.0.2.2:9097/`, which is the
   Android emulator's address for this machine. For a physical phone set `BASE_URL` to `http://<this PC's LAN IP>:9097/`
   (same Wi-Fi, and Windows Firewall must allow port 9097).
3. Start an emulator or connect a phone: `flutter devices` should list it.
4. Run: `flutter run --dart-define-from-file=env/dev.json`
5. Log in as an agent (`01900001001`, PIN `1234`) or a ticket scanner (`01900002001`, PIN `1234`).
6. Only after changing freezed/json models: `dart run build_runner build`.

## Quick troubleshooting

| Symptom | Cause / fix |
|---|---|
| `no password was provided` | `QUARKUS_DATASOURCE_PASSWORD` not set (or `.env` not found; run from `dg-tms-api`). |
| `Connection refused` on 5432 | Container stopped (`docker start ditf-pg`) or another PostgreSQL owns the port. |
| Admin API exits at startup | `ADMIN_TOKEN_SECRET` missing or under 32 characters. |
| Admin API: "port 9096 already in use" | `QUARKUS_HTTP_PORT=9097` not set for that terminal. |
| Client portal shows login errors / network errors | Admin API (9097) is not running; the portal does not use 9096. |
| Mobile app shows a configuration error screen | An empty value in `env/dev.json`. |
| Mobile app cannot reach the API | Emulator: `10.0.2.2`. Phone: LAN IP, not `localhost`. |
