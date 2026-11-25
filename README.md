# DITF Workspace

Workspace repository that holds the DG TMS component repositories as git submodules.

## Submodules

| Path | Repository | Description |
| --- | --- | --- |
| `dg-tms-api` | [DG-Infotech/dg-tms-api](https://github.com/DG-Infotech/dg-tms-api) | Backend API |
| `dg-tms-client-portal` | [DG-Infotech/dg-tms-client-portal](https://github.com/DG-Infotech/dg-tms-client-portal) | Client portal |
| `dg-tms-mobile-app` | [DG-Infotech/dg-tms-mobile-app](https://github.com/DG-Infotech/dg-tms-mobile-app) | Mobile app |
| `dg-tms-web-portal` | [DG-Infotech/dg-tms-web-portal](https://github.com/DG-Infotech/dg-tms-web-portal) | Web portal |

## Getting started

Clone this repository including its submodules:

```bash
git clone --recurse-submodules https://github.com/arif-ahmed/ditf-workspace.git
cd ditf-workspace
```

Or, from a plain clone:

```bash
git submodule update --init
```

## Quick start

Prerequisites: Git, Docker Desktop (running), JDK 21 (the API wrapper `mvnw` downloads Maven), Node 22.12+ (web apps), PowerShell. Flutter 3.50 only for the mobile app.

### A. First time only (fresh clone)

Creates the database container, the schema and the demo data. Do this once per machine.

```powershell
# 1. Clone with submodules (or, from a plain clone: git submodule update --init)
git clone --recurse-submodules https://github.com/arif-ahmed/ditf-workspace.git
cd ditf-workspace

# 2. Create the database container, then apply the schema and load the seed data
docker compose -f docker-compose.dev.yml up -d
.\scripts\seed\seed.ps1

# 3. Install web app dependencies (once, and again after package.json changes)
cd dg-tms-web-portal;    npm install; cd ..
cd dg-tms-client-portal; npm install; cd ..
```

Then continue with section B to run the apps.

### B. Every day (database already created)

One command does all of the steps below (database, both APIs, both web apps, each in its own window), with dev-only settings and no change to any submodule: `.\scripts\dev.ps1 up` (also `status`, `down`). Add `-MockPayments` to also run a fake DGePay/S3 so booking, payment and ticket PDFs work end to end. **Start with [docs/local-dev.md](docs/local-dev.md)**: ports, test accounts, test scenarios for the web portal, client portal and mobile app, how to read the encrypted payloads (`scripts\aes.ps1`) and troubleshooting. Put personal overrides in `scripts\dev.local.env` (`KEY=VALUE` lines, kept out of git with `.git/info/exclude`). Ticket storage is pointed at an unreachable address on purpose: the API ships real S3 credentials, and a local run must not write to that bucket.

The manual steps:

The database and its data live in a Docker volume, so they survive restarts and reboots. You do not seed again, and you do not run `compose up` again. Make sure Docker Desktop is running, then:

```powershell
# 1. Start the database container (it is only stopped, not gone)
docker start ditf-pg

# 2. Public API (booking page, port 9096)
cd dg-tms-api
$env:QUARKUS_DATASOURCE_PASSWORD = "ditf"
.\mvnw.cmd quarkus:dev

# 3. Admin API (back office and mobile app, port 9097), in a second terminal
cd dg-tms-api
$env:QUARKUS_DATASOURCE_PASSWORD = "ditf"
$env:ADMIN_TOKEN_SECRET = "dev-only-secret-at-least-32-characters-long"
$env:QUARKUS_HTTP_PORT = "9097"   # the admin build has no port of its own; without this it clashes with the public API on 9096
.\mvnw.cmd quarkus:dev "-Dapp.module=admin" "-Ddebug=5006"

# 4. Web apps, each in its own terminal
cd dg-tms-web-portal;    npm start   # http://localhost:4200  public booking page
cd dg-tms-client-portal; npm start   # http://localhost:5000  admin portal (4300 is only the Docker/nginx port)
```

Log in to the admin portal with phone `1900003001`, PIN `1234`. The seeded logins and test tickets are listed under [Seed data](#seed-data). The mobile app (`dg-tms-mobile-app`) runs with `flutter run --dart-define-from-file=env/dev.json`; log in as an agent (`1900001001`) or a ticket scanner (`1900002001`).

Stop for the day: Ctrl+C the running apps; `docker stop ditf-pg` is optional.

### C. Only when needed

| Situation | What to do |
| --- | --- |
| Pulled changes that touch the schema (`db/schema.sql`, `db/change.sql`) | Nothing. The API applies them at startup. |
| Seed data changed (`scripts/seed/seed.sql`) or you want fresh dates | `.\scripts\seed\seed.ps1`. It replaces only its own rows (ids starting `5eed5eed`) and keeps your own data. |
| The "today" dashboard looks empty after a few days | Same: `.\scripts\seed\seed.ps1`. Seed dates are relative to the moment it runs. |
| Data is badly broken, or you want a clean slate | `docker compose -f docker-compose.dev.yml down -v` (deletes the data), then `docker compose -f docker-compose.dev.yml up -d` and `.\scripts\seed\seed.ps1`. |
| Submodules show as changed or empty after a pull | `git submodule update --init` |
| `package.json` changed in a web app | `npm install` in that app. |

### Troubleshooting

- **`container name "/ditf-pg" is already in use`** when running `compose up`: a `ditf-pg` container from an earlier setup already exists. Do not create it again. Run `docker start ditf-pg`, then `.\scripts\seed\seed.ps1`. To switch to this workspace's compose file instead, `docker rm ditf-pg` first (its old data stays in its old Docker volume).
- **Connection refused on port 5432**: the container is stopped (`docker start ditf-pg`), or another PostgreSQL on the machine owns port 5432.
- **Admin API refuses to start**: `ADMIN_TOKEN_SECRET` must be set to 32+ characters in that terminal.
- **Connection string** for a database client: `postgresql://ditf:ditf@localhost:5432/ditf?sslmode=disable` (dev-only credentials).

## Local development (API)

The backend (`dg-tms-api`) runs locally against a Dockerized PostgreSQL 17 database.

### Database

Start PostgreSQL from the repository root:

```bash
docker compose -f docker-compose.dev.yml up -d
```

Wait for the database to accept connections:

```bash
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml logs -f postgres
```

Or check readiness directly:

```bash
docker exec ditf-pg pg_isready -U ditf -d ditf
```

### Backend

Run the API in Quarkus dev mode:

```bash
cd dg-tms-api
$env:QUARKUS_DATASOURCE_JDBC_URL = "jdbc:postgresql://localhost:5432/ditf"
$env:QUARKUS_DATASOURCE_USERNAME = "ditf"
$env:QUARKUS_DATASOURCE_PASSWORD = "ditf"
.\mvnw.cmd quarkus:dev
```

The API listens on `http://localhost:9096`.

With `db.schema.apply=true`, the API applies the schema at startup: `db/schema.sql`, then `db/change.sql`. Both files are idempotent and run under a lock, so a fresh database volume needs no manual schema step.

### Seed data

`scripts/seed/seed.sql` fills every table so all pages and GET endpoints have data (about 400 bookings, 40 users, batches, stalls, QR cards, scans). With the database container running:

```powershell
.\scripts\seed\seed.ps1
```

It waits for PostgreSQL, applies `dg-tms-api/src/main/resources/db/schema.sql` if the tables are missing (so the API doesn't need to run first), then loads the data in one transaction. It is repeatable: it only replaces rows whose id starts with `5eed5eed` (the data itself looks like real data, with 32-hex ids, Bangladeshi names and payment references; nothing says "seed"). Dev databases only. Without PowerShell, pipe the files yourself: `docker exec -i ditf-pg psql -U ditf -d ditf -v ON_ERROR_STOP=1 < scripts/seed/seed.sql` (after the schema exists).

- Logins (PIN `1234`): admin `1900003001`, admin staff `1900005001`..`003`, QR staff `1900006001`, QR scanner `1900007001`, ticket generator `1900008001`, ticket scanner `1900002001`, agent `1900001001`..`010`. Merchant staff (`190000400N`) have no PIN.
- Public pages: `find-ticket` with phone `01711000001` and booking number `7700000001` (paid, unscanned); `01711000004` / `7700000004` is already scanned (`TICKET_ALREADY_USED`); `7700000002` is pending, `7700000003` failed, `7700000005` never paid. Gate barcodes follow `2` + 11 digits (`200000100001` is booking 1).
- Edge cases included: a deactivated user for every role (`190000R099`, they can't log in), agent `1900001010` with a zero balance (a sale must fail with "Insufficient balance"), bus-only, child-only and combined bookings, percent and flat coupons, a payment retried with two checkout ids, paid bookings whose PDF isn't generated yet, soft-deleted bookings, bus tickets scanned apart from the fair ticket, an unused/deactivated referral code, an inactive stall, collector and QR card, and the QR card numbered `50000000004` already at its daily scan limit.
- Seeded ticket links are placeholders (`example.invalid`). Real payments and S3 are not reachable locally, but `.\scripts\dev.ps1 up -MockPayments` plus `.\scripts\mock-pay.ps1` simulate them (fake DGePay, S3 and PDF hosting). The full local guide, with test scenarios per app, is [docs/local-dev.md](docs/local-dev.md).

### Build

```bash
cd dg-tms-api
.\mvnw.cmd package
```

### Debug

- Quarkus Dev UI: <http://localhost:9096/qdev>
- `quarkus:dev` watches sources and hot-reloads on changes.

### If running from IntelliJ IDEA

The API is a Quarkus app with no `main()` class, so you run it through the Maven goal `quarkus:dev`. Needs JDK 21 (File > Project Structure > SDK, and Settings > Build Tools > Maven > Runner JRE) and the `ditf-pg` container running (`docker start ditf-pg`).

**1. Give the API the database password.** `application.properties` ships with `quarkus.datasource.password=` empty, so a bare IDE run fails with `The server requested SCRAM-based authentication, but no password was provided`. Do not edit `application.properties`. Create a `.env` file in `dg-tms-api/` (Quarkus dev mode reads it however you launch it):

```properties
QUARKUS_DATASOURCE_JDBC_URL=jdbc:postgresql://127.0.0.1:5432/ditf
QUARKUS_DATASOURCE_USERNAME=ditf
QUARKUS_DATASOURCE_PASSWORD=ditf
```

Use `127.0.0.1`, not `localhost`: `localhost` can resolve to IPv6 `::1`, where another PostgreSQL on the machine may be listening. Keep `.env` out of git: add it to `.git/info/exclude` (local only, never pushed). The values are dev-only credentials.

**2. Create the run configuration.** Run > Edit Configurations > `+` > Maven:

| Field | Value |
| --- | --- |
| Name | `Quarkus Dev` |
| Command line | `quarkus:dev` |
| Working directory | `dg-tms-api` |

For the admin API make a second one named `Quarkus Dev (admin)`, with command line `quarkus:dev -Dapp.module=admin -Ddebug=5006` and environment variables `ADMIN_TOKEN_SECRET` (32+ characters, e.g. `dev-only-secret-at-least-32-characters-long`) and `QUARKUS_HTTP_PORT=9097`. The admin build does not pick 9097 by itself, so without the port it clashes with the public API.

**3. Run it.** Click Run on `Quarkus Dev`. It is ready when the console shows `Listening on: http://0.0.0.0:9096`; check `http://localhost:9096/ticket-booking/health`. Press `Space` in the console to restart. Code changes reload on the next request, no restart needed.

**4. Debug it.** Do not use the Debug button on the Maven configuration: that debugs Maven, not your app. Instead, Quarkus dev mode opens a debug port, **5005**, while it runs:

1. Run `Quarkus Dev` as in step 3.
2. Run > Edit Configurations > `+` > **Remote JVM Debug**, host `localhost`, port `5005`, name `Attach Quarkus`.
3. Click Debug on `Attach Quarkus`. Set breakpoints and call the API.

If both API builds run at once, the second one finds 5005 taken; start it with `-Ddebug=5006` and attach to that port.

**Troubleshooting**

| Symptom | Fix |
| --- | --- |
| `no password was provided` | The `.env` file is missing, or the run's working directory is not `dg-tms-api`. |
| `Connection refused` on 5432 | Container stopped (`docker start ditf-pg`), or something else owns port 5432. |
| `password authentication failed` | The app reached a different PostgreSQL. Use `127.0.0.1` in `.env`. |
| Admin build exits at startup | `ADMIN_TOKEN_SECRET` is not set, or is under 32 characters. |
| `release version 21 not supported` | The Maven Runner JRE is not JDK 21. |

## Working on a submodule

After cloning, enter the submodule you want to work on and run the usual git commands there:

```bash
cd dg-tms-api
git status
git pull
```

To move a submodule to the latest commit on its remote branch:

```bash
git submodule update --init --remote dg-tms-api
```

To make a submodule track a different branch:

```bash
git submodule set-branch --branch <branch> dg-tms-api
git submodule update --remote dg-tms-api
```
