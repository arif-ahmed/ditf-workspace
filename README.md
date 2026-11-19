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

### Build

```bash
cd dg-tms-api
.\mvnw.cmd package
```

### Debug

- Quarkus Dev UI: <http://localhost:9096/qdev>
- `quarkus:dev` watches sources and hot-reloads on changes.

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
