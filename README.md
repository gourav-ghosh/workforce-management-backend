# Workforce Management Backend

Django REST Framework + PostgreSQL backend for the **Workforce Management Mobile
Application — Version 1.2**. Provides JWT authentication, role-based
authorization (Admin / Worker), worker, project, tool, PPE and vehicle
management with assignment history, image uploads, search/filtering,
dashboard aggregation, audit logs and OpenAPI documentation.

The mobile client lives in a completely separate repository
(`workforce-management-mobile`) and communicates only through this HTTP API.

---

## 1. Prerequisites

- Python 3.12+ (3.14 supported)
- PostgreSQL 15+ (or Docker for one-command setup)
- Docker & Docker Compose (optional but recommended)

## 2. Quick start with Docker (recommended)

```bash
cp .env.example .env          # adjust values if needed
docker compose up --build     # starts PostgreSQL + Django dev server
```

Then seed demo data:

```bash
docker compose exec web python manage.py seed_demo_data
```

API is available at `http://localhost:8000/api/v1/` and docs at
`http://localhost:8000/api/docs/`.

## 3. Local setup without Docker

### 3a. Using [uv](https://docs.astral.sh/uv/) (recommended for development)

`pyproject.toml` is the single source of truth and uses uv's PEP 621 /
dependency-group layout. The Docker image also installs via `uv sync`.

```bash
# install uv (skip if you already have it)
pip install uv
# or: pipx install uv

uv sync --group dev                 # creates .venv/ and installs deps
cp .env.example .env                # then edit DATABASE_URL etc.
uv run python manage.py migrate
uv run python manage.py seed_demo_data   # optional realistic demo data
uv run python manage.py runserver
```

Useful uv commands:

| Command | Purpose |
| --- | --- |
| `uv sync` | install runtime deps into `.venv` |
| `uv sync --group dev` | also install dev tools (ruff, coverage) |
| `uv add <pkg>` | add a runtime dependency and update `pyproject.toml` + `uv.lock` |
| `uv add --group dev <pkg>` | add a dev-only dependency |
| `uv remove <pkg>` | remove a dependency |
| `uv lock` | regenerate `uv.lock` |
| `uv run <command>` | run a command inside the project venv |
| `uv run ruff check .` / `uv run ruff format .` | lint / format |

Generate the lock file once (and re-run whenever you change
`pyproject.toml`):

```bash
uv lock
```

Commit `uv.lock` so CI / Docker builds are reproducible.

### 3b. Using pip + venv (legacy)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements/development.txt

cp .env.example .env               # then edit DATABASE_URL etc.
python manage.py migrate
python manage.py seed_demo_data    # optional realistic demo data
python manage.py runserver
```

### `.env` setup

Copy `.env.example` to `.env`. Key variables:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django secret (must be strong in production) |
| `DJANGO_DEBUG` | `True` only for development |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host list |
| `DATABASE_URL` | e.g. `postgres://user:pass@host:5432/dbname` |
| `CORS_ALLOWED_ORIGINS` | Origins allowed to call the API |
| `MEDIA_ROOT` / `MEDIA_URL` | Uploaded image storage |
| `MAX_UPLOAD_SIZE_MB` | Per-file upload cap |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | Access token TTL |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | Refresh token TTL |

`.env` is git-ignored; never commit real credentials.

## 4. Database migrations

```bash
python manage.py makemigrations   # after model changes (CI verifies none are missing)
python manage.py migrate
```

## 5. Seed data (development only)

```bash
python manage.py seed_demo_data
```

Creates an admin, 8 workers, 6 projects, 15 tools, 12 PPE items, 5 vehicles
and sample assignments including historical records.

Demo credentials — **development only, never use these in production**.
Login uses the **mobile number** (not the legacy `username`):

```
Admin    mobile 9000000000 / Admin@12345
Workers  mobile 9876543210 ... 9876543217 / Worker@12345
```

## 6. Running tests

```bash
# SQLite fallback (no Postgres needed)
python manage.py test tests -v 2

# Against PostgreSQL (recommended; matches CI)
DATABASE_URL=postgres://... python manage.py test tests -v 2
```

## 7. API documentation

- Human-readable reference: [`docs/API.md`](docs/API.md)
- Deployment guide: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI schema: `/api/schema/`
- Health check: `/api/health/`

## 8. API overview

Base path: `/api/v1/`

| Area | Endpoints |
| --- | --- |
| Auth | `POST auth/login`, `auth/refresh`, `auth/logout`, `auth/password-reset`, `auth/password-reset/confirm`, `auth/change-password` |
| Current user | `GET me/`, `me/summary`, `me/projects`, `me/tools`, `me/ppe`, `me/vehicles` (worker-scoped) |
| Dashboard | `GET dashboard/` (admin) |
| Workers | CRUD under `workers/` + `POST workers/{id}/reset-password` |
| Projects | CRUD under `projects/` + `GET/POST projects/{id}/workers`, `DELETE projects/{id}/workers/{worker_id}` |
| Tools | CRUD under `tools/` + `assign`, `return`, `damage`, `history`, `media`, `set-status` |
| PPE | CRUD under `ppe/` + `assign`, `return`, `history`, `media`, `set-status` |
| Vehicles | CRUD under `vehicles/` + `assign`, `unassign`, `history`, `media`, `set-status` |
| Audit | `GET audit/` (admin, filterable) |

List endpoints support `?search=`, module-specific filters (`status=`,
`category=` …), ordering and page pagination (`page`, `page_size`).

Business rules enforced server-side:

- A tool/PPE item cannot have two simultaneous active assignments
  (unique partial constraint + row locking).
- Vehicle assignments cannot overlap in time.
- Workers can only ever read their own profile/assignments via `/me/*`.
- Assignment history rows are immutable; reassignment creates new records.
- Deletion is blocked when assignment history exists.

## 9. Production deployment

Target: any generic VPS (no provider lock-in). For the complete Hostinger/Ubuntu
walkthrough, including DNS, host Nginx, TLS, backups, and restores, see
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

The production stack is:

```text
VPS Nginx (HTTPS) -> bundled Nginx (127.0.0.1:8080) -> Gunicorn/Django -> PostgreSQL
```

Use the host-Nginx override when TLS terminates on the VPS:

```bash
cp .env.example .env      # set strong DJANGO_SECRET_KEY, DJANGO_DEBUG=False,
                          # DJANGO_ALLOWED_HOSTS, PUBLIC_BASE_URL,
                          # CORS_ALLOWED_ORIGINS, POSTGRES_* credentials
chmod 600 .env

docker compose \
  -f docker-compose.prod.yml \
  -f deployment/docker-compose.prod-host-nginx.yml \
  up -d --build
```

The bundled Nginx is published only on loopback; Django and PostgreSQL are not
exposed to the internet. Persistent named volumes store the database
(`pgdata_prod`), uploaded media (`media_prod`), and static files
(`static_prod`). The entrypoint waits for PostgreSQL, applies migrations, and
collects static files before Gunicorn starts.

Create the first administrator inside the web container:

```bash
docker compose -f docker-compose.prod.yml -f deployment/docker-compose.prod-host-nginx.yml \
  exec web python manage.py createsuperuser \
  --mobile_number <mobile>
```

The command prompts for the password interactively. The custom user manager
assigns the `ADMIN` application role, so this account can use both `/admin/`
and ADMIN-only API endpoints. Set an email address afterwards if the
account-based password-reset flow is needed. API authorization depends on
`User.role == "ADMIN"`, not only on Django `is_staff`/`is_superuser`.

Verify the deployment:

```bash
curl -i http://127.0.0.1:8080/api/health/
curl -I https://api.example.com/api/health/
```

Both should reach the health endpoint; the public request should use HTTPS.
For updates, run `git pull` and repeat the two-file `docker compose ... up -d
--build` command. Use the same Compose file pair for `logs`, `restart`, `ps`,
and management commands.

### Backup notes

Back up both PostgreSQL and uploaded media. A database-only backup is
incomplete because photos and documents live in the `media_prod` volume; keep
copies off the VPS and test restores regularly. Exact `pg_dump`, media archive,
and restore commands are documented in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## 10. Project layout

```
config/           settings split (base/dev/prod), root urls
apps/
  accounts/       User model, JWT auth, /me endpoints
  workers/        WorkerProfile + management API
  projects/       Project, ProjectWorker assignments
  tools/          Tool, ToolAssignment/Damage/Media + workflows
  ppe/            PPE, PPEAssignment/Media + workflows
  transportation/ Vehicle, VehicleAssignment/Media + workflows
  audit/          AuditLog + query API
  dashboard/      Aggregated dashboard endpoint
  common/         Shared models/pagination/errors/permissions/validators
tests/            Full backend test suite
deployment/       host Nginx template and Compose override
docs/             API reference and production deployment guide
requirements/     base / development / production pins
```
