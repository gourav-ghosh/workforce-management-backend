# Workforce Management Backend

Django REST Framework + PostgreSQL backend for the **Workforce Management Mobile
Application — Version 1**. Provides JWT authentication, role-based
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

Demo credentials — **development only, never use these in production**:

```
Admin    admin    / Admin@12345
Workers  worker1..worker8 / Worker@12345
```

## 6. Running tests

```bash
# SQLite fallback (no Postgres needed)
python manage.py test tests -v 2

# Against PostgreSQL (recommended; matches CI)
DATABASE_URL=postgres://... python manage.py test tests -v 2
```

## 7. API documentation

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

Target: any generic VPS (no provider lock-in).

```bash
cp .env.example .env      # set strong DJANGO_SECRET_KEY, DJANGO_DEBUG=False,
                          # DJANGO_ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS,
                          # POSTGRES_* credentials
docker compose -f docker-compose.prod.yml up -d --build
```

Architecture: **Nginx → Gunicorn → Django → PostgreSQL**, with persistent
named volumes for the database (`pgdata_prod`), uploaded media
(`media_prod`) and collected static files (`static_prod`). Migrations run
automatically on container start (entrypoint).

Checklist:

1. Server requirements: 1 vCPU / 1 GB RAM minimum, Docker installed.
2. DNS pointed at the server; put TLS on top of Nginx (e.g. certbot or a
   load balancer terminating HTTPS). `SECURE_SSL_REDIRECT=True` expects it.
3. `docker compose -f docker-compose.prod.yml exec web python manage.py
   createsuperuser` if Django-admin access is required.
4. Health: `curl http://server/api/health/` → `{"status": "ok"}`.
5. Restart: `docker compose -f docker-compose.prod.yml restart`.
6. Update: `git pull && docker compose -f docker-compose.prod.yml up -d --build`.

### Backup notes

PostgreSQL data lives in the `pgdata_prod` volume. Schedule dumps:

```bash
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup_$(date +%F).sql
```

Also back up the `media_prod` volume (uploaded photos/documents).

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
deployment/       nginx config
requirements/     base / development / production pins
```
