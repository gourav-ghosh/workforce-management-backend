# Workforce Management API Reference

This is the human-readable API reference for the Django REST Framework
backend. The live, generated documentation is also available at:

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI JSON/YAML: `/api/schema/`

The generated schema is useful for client generation, but several endpoints
are implemented with `APIView`; the generated schema may not include every
request/response field for those endpoints. This document is the authoritative
field list for Version 1.2.0.

## 1. Conventions

### Base URL

All application endpoints are below:

```text
https://api.example.com/api/v1/
```

Replace `api.example.com` with the production host configured in
`DJANGO_ALLOWED_HOSTS` and `PUBLIC_BASE_URL`.

### Resource identifiers and updates

Most CRUD paths use the numeric database primary key (`id`). Vehicle paths are
the exception: `{vehicle_id}` accepts either the numeric primary key or the
unique business code such as `VEH-01`. Tool and PPE workflow responses named
`tool_id` and `ppe_id` contain numeric primary keys, not business codes.

`PUT` behavior is endpoint-specific. Tools, PPE, Vehicles, and vehicle
bookings accept partial bodies on `PUT` as well as on `PATCH`. Projects also
accept partial bodies because their create-only identifiers are optional in the
write serializer. Worker and worker-performance `PUT` remain full updates; use
`PATCH` for partial changes. Required fields are enforced when creating a
resource.

### Authentication

Most endpoints require a JWT access token:

```http
Authorization: Bearer <access_token>
```

Roles:

- `ADMIN` — management endpoints under `/workers/`, `/projects/`, `/tools/`,
  `/ppe/`, `/vehicles/`, `/attendance/`, `/audit/`, `/dashboard/`, and worker
  performance.
- `WORKER` — `/api/v1/me/*` endpoints.
- `WORKER` + `is_supervisor=true` — may also use `/attendance/` for the
  projects they are assigned to. Supervisors are still workers and keep all
  `/me/*` access. `GET /me/` itself accepts any
  authenticated user; the remaining `/me/*` routes require a linked worker
  profile.
- Public — login, token refresh, password reset, self password reset, and
  health check.

The mobile app should keep the refresh token private and use the access token
for API requests. Access and refresh token lifetimes are configured in `.env`.

### Dates and date-times

- Date fields use `YYYY-MM-DD`, for example `2026-09-19`.
- Date-time fields use ISO 8601 with a timezone, for example
  `2026-09-19T09:00:00Z` or `2026-09-19T14:30:00+05:30`.
- The server stores date-times in UTC (`TIME_ZONE = "UTC"`).

### Pagination

Paginated list responses use this shape:

```json
{
  "count": 42,
  "next": "https://api.example.com/api/v1/workers/?page=2",
  "previous": null,
  "results": []
}
```

Common query parameters:

| Parameter | Purpose |
| --- | --- |
| `page` | One-based page number. Defaults to `1`. |
| `page_size` | Results per page. Defaults to `PAGE_SIZE` (20); maximum 100. |
| `search` | Case-insensitive text search over the module's configured fields. |
| `ordering` | Comma-separated fields. Prefix with `-` for descending order. |

A list endpoint without a pagination class returns a JSON array instead.

### Uploads

Image and document endpoints accept `multipart/form-data` unless noted
otherwise. The upload limit is `MAX_UPLOAD_SIZE_MB` (10 MB by default).
Allowed image types are JPEG, PNG, and WebP.

### Errors

Validation errors use standard DRF field errors:

```json
{
  "mobile_number": ["A user with this mobile number already exists."],
  "password": ["This password is too short."]
}
```

Non-field errors use:

```json
{
  "detail": "The request conflicts with the current state.",
  "code": "CONFLICT"
}
```

Common status codes:

| Status | Meaning |
| --- | --- |
| `200` | Successful read/update |
| `201` | Resource created |
| `204` | Deleted or logout completed; no response body |
| `400` | Invalid input |
| `401` | Missing/invalid authentication |
| `403` | Authenticated user lacks the required role |
| `404` | Resource not found or worker cannot access a scoped resource |
| `409` | Business-rule conflict, such as overlap, duplicate active assignment, or deletion blocked by history |

## 2. Authentication and current user

### `POST /auth/login/`

Public. Authenticates with the custom mobile-number login field.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `mobile_number` | string | Yes | Unique login mobile number |
| `password` | string | Yes | Account password |

Response:

```json
{
  "refresh": "<refresh-token>",
  "access": "<access-token>",
  "user": {
    "id": 1,
    "mobile_number": "+919000000001",
    "email": "admin@example.com",
    "role": "ADMIN",
    "worker_profile": null
  }
}
```

### `POST /auth/refresh/`

Public. Rotates a refresh token.

Request:

| Field | Type | Required |
| --- | --- | --- |
| `refresh` | string | Yes |

Response:

```json
{
  "access": "<new-access-token>"
}
```

Refresh-token rotation and blacklist settings are enabled in Django settings.

### `POST /auth/logout/`

Authenticated. Blacklists a refresh token.

Request body is optional:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `refresh` | string | No | Blacklist only this token. If omitted, all refresh tokens for the user are blacklisted. |

Response: `204 No Content`.

### `POST /auth/password-reset/`

Public. Requests a password-reset email.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `identifier` | string | Yes | Mobile number or email address |

Response is deliberately generic for every valid request:

```json
{
  "detail": "If the account exists, password reset instructions have been sent."
}
```

The endpoint is throttled at 10 requests per minute.

### `POST /auth/password-reset/confirm/`

Public. Completes a reset using the values sent by email.

Request:

| Field | Type | Required |
| --- | --- | --- |
| `uid` | string | Yes |
| `token` | string | Yes |
| `new_password` | string | Yes |

Response:

```json
{
  "detail": "Password has been reset."
}
```

### `POST /auth/password-reset/self/`

Public. Worker self-service reset for an account that still has its current
(default or admin-issued) password.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `mobile_number` | string | Yes | Worker login mobile number |
| `current_password` | string | Yes | Current/default password |
| `new_password` | string | Yes | New password |

Response:

```json
{
  "detail": "Password has been reset."
}
```

This is the route used by the mobile client. The similarly named
`/workers/self/reset-password/` text in an older view docstring is not a
separate route.

### `POST /auth/change-password/`

Authenticated. Changes the current user's password.

Request:

| Field | Type | Required |
| --- | --- | --- |
| `current_password` | string | Yes |
| `new_password` | string | Yes |

Response:

```json
{
  "detail": "Password changed."
}
```

### `GET /me/`

Authenticated. Returns the current user and, when present, the linked worker
profile.

Response fields:

```text
id, mobile_number, email, role, worker_profile
```

`worker_profile` contains:

```text
id, employee_id, full_name, phone_number, designation,
employment_status, is_supervisor, profile_photo
```

### `GET /me/summary/`

Worker role. Returns quick counts for the worker home screen:

```json
{
  "projects": 2,
  "tools": 3,
  "tools_damaged": 0,
  "ppe": 4,
  "vehicles": 1
}
```

### `GET /me/projects/`

Worker role. Returns active project assignments. Paginated.

Each result contains:

```text
id, assigned_at, project {
  id, project_number, project_name, client_name, location, status,
  start_date, expected_completion_date, description
}
```

### `GET /me/projects/{id}/`

Worker role. Returns project detail only when the requesting worker is
currently assigned to that project. The response uses the project detail
shape described under Projects, including `material_required`,
`ppe_required` and `measurement_after_bill_status` — a worker needs to see
what the project requires of them. A worker who is not assigned receives `409`
with code `PROJECT_NOT_ASSIGNED`.

### `GET /me/tools/`

Worker role. Returns active tool assignments as a JSON array.

Each result contains:

```text
id, issue_date, expected_return_date, issue_condition, remarks,
tool { id, tool_id, name, category, condition }
```

### `GET /me/tools/history/`

Worker role. Returns the worker's active and historical tool assignments.
Paginated. Each result includes nested `damages` and `media` arrays.

### `GET /me/tools/{assignment_id}/`

Worker role. Returns one of the requesting worker's tool assignments,
including damages and media. Assignments belonging to another worker return
`404` with code `ASSIGNMENT_NOT_FOUND`.

### `POST /me/tools/{assignment_id}/damage/`

Worker role. Reports damage against one of the worker's own assignments.
Multipart is supported.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `damage_description` | string | Yes | Damage description |
| `damage_condition` | string | Yes | `EXCELLENT`, `GOOD`, `FAIR`, `POOR`, or `DAMAGED` |
| `remarks` | string | No | Defaults to empty string |
| `photos` | image files | No | Repeatable multipart image field |

Response is a `ToolDamage` object with `id`, `tool`, `assignment`,
`damage_date`, `damage_description`, `damage_condition`, `repair_status`,
`remarks`, `media`, `created_at`.

### `GET /me/ppe/`

Worker role. Returns active PPE assignments as a JSON array.

Each result contains:

```text
id, issue_date, expected_return_date, issue_condition, remarks,
ppe { id, ppe_id, ppe_type, name, size }
```

### `GET /me/vehicles/`

Worker role. Returns open vehicle assignments where the worker is the
assigned worker or driver. Each result contains:

```text
id, assignment_type, role, start_datetime, end_datetime, purpose,
vehicle { id, vehicle_id, registration_number, vehicle_type, make_model }
```

`role` is `driver` when the worker is the assignment driver; otherwise it is
`worker`.

### `GET /me/performance/`

Worker role. Returns only performance records for the worker where
`is_visible_to_worker=true`. Records are returned as a JSON array.

## 3. Common list filters

| Resource | `search` fields | Additional filters | Ordering fields |
| --- | --- | --- | --- |
| Workers | `full_name`, `employee_id`, `phone_number` | `status`, `designation` | `full_name`, `employee_id`, `created_at` |
| Projects | `project_number`, `project_name`, `client_name`, `location` | `status`, `measurement_sheet_status`, `material_required`, `ppe_required` (detail only) | `project_number`, `project_name`, `status`, `created_at`, `start_date` |
| Tools | `tool_id`, `name`, `category`, assigned worker name | `status`, `category`, `assigned_worker` | `tool_id`, `name`, `availability_status`, `created_at` |
| PPE | `ppe_id`, `name`, `ppe_type`, assigned worker name | `status`, `ppe_type`, `assigned_worker` | `ppe_id`, `name`, `availability_status`, `created_at` |
| Vehicles | `vehicle_id`, `registration_number`, `make_model` | `status`, `vehicle_type` | `vehicle_id`, `registration_number`, `status`, `created_at` |

`assigned_worker` is a worker profile ID and only matches active assignments.

## 4. Workers

All worker-management endpoints require `ADMIN`.

### `GET /workers/`

Query parameters are the common worker filters above. Returns paginated
`WorkerListSerializer` objects:

```text
id, employee_id, full_name, designation, phone_number,
employment_status, is_supervisor, profile_photo_url
```

### `POST /workers/`

Creates the worker profile and linked login account.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `employee_id` | string | Yes | Unique employee ID |
| `full_name` | string | Yes | Worker name |
| `phone_number` | string | Yes | Profile phone number |
| `is_supervisor` | boolean | No | Defaults to `false`; allows marking attendance for their project team |
| `mobile_number` | string | Yes | Login identifier; must be unique |
| `password` | string | Yes | Initial login password |
| `designation` | string | No | |
| `employment_status` | string | No | `ACTIVE` or `INACTIVE`; defaults to `ACTIVE` |
| `emergency_contact_name` | string | No | |
| `emergency_contact_phone` | string | No | |
| `email` | string | No | Write-only; used for password reset |
| `profile_photo` | image file | No | Multipart upload |

Response is a `WorkerDetailSerializer` object.

### `GET /workers/{id}/`

Returns worker detail plus:

```text
emergency_contact_name, emergency_contact_phone,
current_projects, assigned_tools, assigned_ppe,
vehicle_assignments, created_at, updated_at
```

`assigned_tools` and `assigned_ppe` contain only active assignments. The
`assignment_id` field is the assignment's primary key.

### `PUT /workers/{id}/`

Update. PUT is partial-compatible; use the same profile fields as create, but
do not send `mobile_number`, `password`, or `email`; account credentials cannot
be changed through the worker profile update endpoint.

### `PATCH /workers/{id}/`

Partial update using the same restrictions as `PUT`.

### `DELETE /workers/{id}/`

Deletes a worker only when no project, tool, PPE, or vehicle assignment history
exists. Otherwise returns `409` with code `RESOURCE_HAS_HISTORY`. Use
`employment_status=INACTIVE` for normal offboarding.

### `POST /workers/{id}/reset-password/`

Admin sets a worker's password.

Request:

| Field | Type | Required |
| --- | --- | --- |
| `new_password` | string | Yes |

Response:

```json
{
  "detail": "Password updated."
}
```

## 5. Projects

All project endpoints require `ADMIN` except the worker-scoped `/me/projects`
routes.

### `GET /projects/`

Uses the common project filters. List response fields:

```text
id, project_number, project_name, client_name, location, status,
measurement_sheet_status, start_date, expected_completion_date,
active_workers_count
```

### `POST /projects/`

Multipart is supported for `project_plan`.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `project_number` | string | Yes on create | Unique project number |
| `project_name` | string | Yes on create | |
| `client_name` | string | No | |
| `location` | string | No | |
| `description` | string | No | |
| `start_date` | date | No | |
| `expected_completion_date` | date | No | Must be on/after start date |
| `permit_no` | string | No | |
| `total_manpower` | integer | No | |
| `job` | string | No | |
| `material_required` | string | No | Free text; multi-line notes on materials the project needs |
| `ppe_required` | string | No | Free text; multi-line notes on required PPE |
| `measurement_after_bill_status` | string | No | Short free-text status, e.g. "Pending client approval" |
| `measurement_sheet_status` | string | No | `SUBMITTED` or `NOT_SUBMITTED` |
| `status` | string | No | `DRAFT`, `PLANNED`, `ACTIVE`, `COMPLETED`, `CANCELLED` |
| `project_plan` | document file | No | Multipart upload |
| `notes` | string | No | |

The three requirement fields are **optional and default to an empty string**, so
existing projects stay valid and can be left untouched. In a `PATCH`, omitting a
field leaves it unchanged; send `""` to clear it.

Response is `ProjectDetailSerializer`.

### `GET /projects/{id}/`

Returns list fields plus:

```text
description, permit_no, total_manpower, job,
material_required, ppe_required, measurement_after_bill_status, notes,
project_plan_url, assigned_workers, tools_assigned_count,
ppe_assigned_count, created_at, updated_at
```

The three requirement fields are detail-only — they are not in the
`GET /projects/` list payload, so listing stays lean.

### `PUT /projects/{id}/`

Update using the project fields above. `PUT` is partial-compatible; `PATCH` is
the explicit partial-update method.

### `PATCH /projects/{id}/`

Partial update using the project fields above.

### `DELETE /projects/{id}/`

Deletes the project only when no worker, tool, or vehicle assignment history
exists. Otherwise returns `409` with code `RESOURCE_HAS_HISTORY`.

### `GET /projects/{id}/workers/`

Returns active and historical project-worker assignment rows. Paginated.
Each row contains:

```text
id, worker { id, employee_id, full_name, designation },
assigned_at, unassigned_at, is_active
```

### `POST /projects/{id}/workers/`

Assigns a worker to the project.

Request:

| Field | Type | Required |
| --- | --- | --- |
| `worker_id` | integer | Yes |

Returns the new `ProjectWorkerSerializer` object with status `201`. A worker
who is already actively assigned returns `409` with code
`WORKER_ALREADY_ASSIGNED`.

### `DELETE /projects/{id}/workers/{worker_id}/`

Unassigns the worker. The service closes the active assignment and records
`unassigned_at`. Returns `204`; if there is no active assignment, returns `409`
with code `ASSIGNMENT_NOT_FOUND`.

## 6. Tools

All tool-management endpoints require `ADMIN`.

### `GET /tools/`

Uses the common tool filters. List response fields:

```text
id, tool_id, name, category, condition, availability_status, photo_url
```

### `POST /tools/`

Multipart is supported for `photo`.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `tool_id` | string | Yes on create | Unique business ID |
| `name` | string | Yes on create | |
| `category` | string | No | |
| `description` | string | No | |
| `photo` | image file | No | |
| `purchase_date` | date | No | |
| `condition` | string | No | `EXCELLENT`, `GOOD`, `FAIR`, `POOR`, `DAMAGED`; defaults to `GOOD` |
| `availability_status` | string | No | `AVAILABLE`, `ASSIGNED`, `DAMAGED`, `UNDER_MAINTENANCE`, `LOST`, `RETIRED`; defaults to `AVAILABLE` |
| `remarks` | string | No | |

Response is `ToolDetailSerializer` with status `201`.

### `GET /tools/{id}/`

Returns list fields plus:

```text
description, purchase_date, remarks, current_assignment,
open_damage_count, damages, media, created_at, updated_at
```

### `PUT /tools/{id}/`

Update using the tool fields above. `PUT` is partial-compatible; `PATCH` is the
explicit partial-update method.

### `PATCH /tools/{id}/`

Partial update using the tool fields above.

### `DELETE /tools/{id}/`

Deletes the tool only when neither assignment history nor damage history
exists; otherwise it returns `409` with code `RESOURCE_HAS_HISTORY`.

### `POST /tools/{id}/issue/`

Issues a tool to a worker. The tool must currently be `AVAILABLE`; otherwise
the endpoint returns `409` with code `TOOL_NOT_AVAILABLE`. Multipart is
supported.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `worker_id` | integer | Yes | |
| `project_id` | integer | No | Nullable |
| `issue_date` | date | No | Defaults to today |
| `expected_return_date` | date | No | Nullable |
| `issue_condition` | string | No | Tool condition choices; defaults to the tool's current condition |
| `remarks` | string | No | Defaults to empty |
| `photos` | image files | No | Repeatable multipart field |

The endpoint returns `201`. The `tool_id` value in this response is the numeric
tool primary key, not the business code. The business code is the `tool_id`
field returned by `GET /tools/{id}/`.

```json
{
  "assignment_id": 12,
  "tool_id": 3,
  "worker_id": 7,
  "project_id": null,
  "issue_date": "2026-09-19",
  "expected_return_date": null,
  "issue_condition": "GOOD",
  "status": "ACTIVE"
}
```

### `POST /tools/{id}/return/`

Records a return. Multipart is supported.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `return_condition` | string | Yes | Tool condition choices |
| `return_date` | date | No | Defaults to today |
| `remarks` | string | No | |
| `photos` | image files | No | Repeatable multipart field |

Response includes `assignment_id`, `status`, `return_date`,
`return_condition`, and `tool_availability_status`. Returning a tool without an
active assignment returns `409` with code `NO_ACTIVE_ASSIGNMENT`.

### `POST /tools/{id}/damage/`

Records a damage record. Multipart is supported.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `assignment_id` | integer | No | Nullable; when supplied it must belong to this tool |
| `damage_date` | date | No | Defaults to today |
| `damage_description` | string | Yes | |
| `damage_condition` | string | Yes | Tool condition choices |
| `repair_status` | string | No | `REPORTED`, `IN_PROGRESS`, `COMPLETED`; defaults to `REPORTED` |
| `remarks` | string | No | |
| `photos` | image files | No | Repeatable multipart field |

Response is a `ToolDamageReadSerializer` object with status `201`. The `tool`
and `assignment` values are numeric primary keys; `assignment` is nullable.

### `GET /tools/{id}/history/`

Paginated assignment history. Each row includes worker, project number,
issue/return dates and conditions, status, remarks, damages, and media.

### `GET /tools/{id}/media/`

Paginated media gallery.

### `POST /tools/{id}/media/`

Uploads one image.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `file` | image file | Yes | |
| `media_type` | string | No | `GENERAL`, `ISSUE`, `RETURN`, `DAMAGE`; defaults to `GENERAL` |

Response is a media object with `id`, `media_type`, `file_url`,
`assignment`, `damage`, and `created_at`.

### `POST /tools/{id}/set-status/`

Manually changes availability.

Request:

```json
{
  "availability_status": "UNDER_MAINTENANCE"
}
```

Allowed values are the tool availability choices. Returns:

```json
{
  "availability_status": "UNDER_MAINTENANCE"
}
```

### `POST /tools/{id}/repair/`

Repairs a damaged tool.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `condition` | string | No | Defaults to `GOOD` |
| `close_assignment` | boolean/string | No | Defaults to `true`; accepts `true`, `1`, `yes`, or `on` |
| `notes` | string | No | |

Response is the updated `ToolDetailSerializer` object.

### `GET /tools/stock/`

Admin-only aggregate counts, plus a category-wise breakdown:

```json
{
  "total": 15,
  "available": 8,
  "assigned": 4,
  "damaged": 1,
  "under_maintenance": 1,
  "lost": 0,
  "retired": 1,
  "groups": [
    {
      "key": "Hand Tools",
      "label": "Hand Tools",
      "total": 9,
      "AVAILABLE": 7,
      "ASSIGNED": 1,
      "DAMAGED": 1,
      "UNDER_MAINTENANCE": 0,
      "LOST": 0,
      "RETIRED": 0
    }
  ]
}
```

`groups` is sorted by descending `total`. Each entry carries `key` (the stored
category), `label` (free text passed through), `total`, and one key per
availability status. Tools with no category are reported under
`"Uncategorised"` rather than dropped, so the group totals always add up to
`total`. The status keys are the raw model choice values (`AVAILABLE`, ...),
matching `availability_status` on a tool — note the flat keys above are
lowercase.

## 7. PPE

All PPE-management endpoints require `ADMIN`.

### `GET /ppe/`

Uses the common PPE filters. List response fields:

```text
id, ppe_id, ppe_type, name, size, condition,
availability_status, expired, photo_url
```

Allowed PPE types are `HELMET`, `SHOES`, `GLOVES`, `JACKET`, `HARNESS`,
`GOGGLES`, `EAR_PROTECTION`, and `OTHER`.

### `POST /ppe/`

Multipart is supported for `photo`.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ppe_id` | string | Yes on create | Unique business ID |
| `ppe_type` | string | Yes on create | Allowed PPE type |
| `name` | string | Yes on create | |
| `category` | string | No | |
| `size` | string | No | |
| `photo` | image file | No | |
| `purchase_date` | date | No | |
| `expiry_date` | date | No | Must be on/after purchase date |
| `condition` | string | No | PPE condition choices; defaults to `GOOD` |
| `availability_status` | string | No | `AVAILABLE`, `ASSIGNED`, `DAMAGED`, `EXPIRED`, `RETIRED`; defaults to `AVAILABLE` |
| `remarks` | string | No | |

Response is `PPEDetailSerializer` with status `201`.

### `GET /ppe/{id}/`

Returns list fields plus:

```text
category, purchase_date, expiry_date, remarks,
current_assignment, created_at, updated_at
```

### `PUT /ppe/{id}/`, `PATCH /ppe/{id}/`, `DELETE /ppe/{id}/`

`PUT` and `PATCH` update the same fields as create. Both are partial-compatible;
`PATCH` is the explicit partial-update method. Deletion is blocked when
assignment history exists and otherwise returns `204`. PPE media rows are not a
 deletion blocker.

### `POST /ppe/{id}/issue/`

Issues one PPE unit to a worker. The item must currently be `AVAILABLE`;
otherwise the endpoint returns `409` with code `PPE_NOT_AVAILABLE`. Multipart
is supported.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `worker_id` | integer | Yes | |
| `issue_date` | date | No | Defaults to today |
| `expected_return_date` | date | No | Nullable |
| `issue_condition` | string | No | PPE condition choices; defaults to the item's current condition |
| `remarks` | string | No | Defaults to empty |
| `photos` | image files | No | Repeatable multipart field |

The endpoint returns `201`. Response includes `assignment_id`, `ppe_id`,
`worker_id`, issue dates, condition, and `status`. The `ppe_id` value is the
numeric PPE primary key;
the business code is the `ppe_id` field returned by `GET /ppe/{id}/`.

### `POST /ppe/{id}/return/`

Request:

| Field | Type | Required |
| --- | --- | --- |
| `return_condition` | string | Yes |
| `return_date` | date | No |
| `remarks` | string | No |
| `photos` | image files | No |

Response includes `assignment_id`, `status`, `return_date`,
`return_condition`, and `ppe_availability_status`. Returning PPE without an
active assignment returns `409` with code `NO_ACTIVE_ASSIGNMENT`.

### `GET /ppe/{id}/history/`

Paginated assignment history with worker, issue/return dates and conditions,
status, and remarks.

### `GET /ppe/{id}/media/`, `POST /ppe/{id}/media/`

Media gallery and upload. Upload fields are `file` (required image) and
optional `media_type` (`GENERAL`, `ISSUE`, `RETURN`, `DAMAGE`).

### `POST /ppe/{id}/set-status/`

Request:

```json
{
  "availability_status": "DAMAGED"
}
```

Returns the new availability status.

### `GET /ppe/stock/`

Returns:

```json
{
  "total": 12,
  "available": 5,
  "assigned": 4,
  "expired": 1,
  "damaged": 1,
  "retired": 1,
  "condition_good": 8,
  "condition_fair": 2,
  "condition_poor": 1,
  "condition_damaged": 1,
  "groups": [
    {
      "key": "SHOES",
      "label": "Safety Shoes",
      "total": 20,
      "AVAILABLE": 12,
      "ASSIGNED": 6,
      "DAMAGED": 1,
      "EXPIRED": 0,
      "RETIRED": 1,
      "sub_groups": [
        {
          "key": "7",
          "label": "7",
          "total": 12,
          "AVAILABLE": 9,
          "ASSIGNED": 3,
          "DAMAGED": 0,
          "EXPIRED": 0,
          "RETIRED": 0
        },
        {
          "key": "8",
          "label": "8",
          "total": 5,
          "AVAILABLE": 4,
          "ASSIGNED": 1,
          "DAMAGED": 0,
          "EXPIRED": 0,
          "RETIRED": 0
        }
      ]
    }
  ],
  "size_groups": [
    {
      "key": "7",
      "label": "7",
      "total": 14,
      "AVAILABLE": 11,
      "ASSIGNED": 3,
      "DAMAGED": 0,
      "EXPIRED": 0,
      "RETIRED": 0
    }
  ],
  "category_groups": [
    {
      "key": "Site A",
      "label": "Site A",
      "total": 6,
      "AVAILABLE": 3,
      "ASSIGNED": 3,
      "DAMAGED": 0,
      "EXPIRED": 0,
      "RETIRED": 0
    }
  ]
}
```

| Field | Grouped by |
| --- | --- |
| `groups` | `ppe_type` — the main category (helmet, shoes, gloves, ...) |
| `groups[].sub_groups` | `size`, **nested inside each type** |
| `size_groups` | `size` — the overall size rollup across every type |
| `category_groups` | the optional free-text `category` |

Sizes are nested rather than listed beside the categories because a size
figure is only meaningful against a type: the question is "of the 20 safety
shoes, how many are size 7", not "how many size 7 items exist". A group only
carries `sub_groups` when items in it actually have a size recorded, and the
sub-group totals always add up to that group's `total`.

`size_groups` is kept as a fleet-wide rollup for reporting, and
`category_groups` is only meaningful when PPE items carry a free-text
category. Each list is sorted by descending `total`; items with a blank value
appear under `"Uncategorised"`, so everything reconciles with `total`.

## 8. Vehicles

All vehicle-management endpoints require `ADMIN`.

### `GET /vehicles/`

Uses the common vehicle filters. List response fields:

```text
id, vehicle_id, registration_number, vehicle_type, make_model,
status, photo_url
```

Vehicle types are `TRUCK`, `VAN`, `PICKUP`, `CAR`, `BUS`, `TRAILER`,
`DUMPER`, and `OTHER`.

### `POST /vehicles/`

Multipart is supported for `photo`.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `vehicle_id` | string | Yes on create | Unique business ID |
| `registration_number` | string | Yes on create | Stored uppercase |
| `vehicle_type` | string | Yes on create | Allowed vehicle type |
| `make_model` | string | No | |
| `photo` | image file | No | |
| `driver` | integer | No | Worker profile ID for the default driver |
| `capacity` | string | No | |
| `status` | string | No | `AVAILABLE`, `IN_USE`, `UNDER_MAINTENANCE`, `RETIRED`; defaults to `AVAILABLE` |
| `insurance_valid_until` | date | No | |
| `inspection_valid_until` | date | No | |
| `rc_validity` | date | No | |
| `fitness_validity` | date | No | |
| `pollution_validity` | date | No | |
| `safety_validity` | date | No | |
| `load_test_validity` | date | No | |
| `yearly_maintenance_charge` | decimal/string | No | Up to 12 digits, 2 decimal places |
| `remarks` | string | No | |

Response is `VehicleDetailSerializer` with status `201`.

### `GET /vehicles/{vehicle_id}/`

`vehicle_id` may be the numeric database ID or the business code such as
`VEH-01`. Returns list fields plus:

```text
capacity, driver, insurance_valid_until, inspection_valid_until,
rc_validity, fitness_validity, pollution_validity, safety_validity,
load_test_validity, yearly_maintenance_charge, remarks,
current_assignment, created_at, updated_at
```

### `PUT /vehicles/{vehicle_id}/`, `PATCH /vehicles/{vehicle_id}/`

Update using the vehicle fields above. `PUT` is partial-compatible; `PATCH` is
the explicit partial-update method.

### `DELETE /vehicles/{vehicle_id}/`

Deletes the vehicle only when no vehicle-assignment history exists; otherwise
it returns `409` with code `RESOURCE_HAS_HISTORY`. Vehicle bookings and media
are removed by the model cascade when deletion is allowed.

### `POST /vehicles/{vehicle_id}/assign/`

Creates an actual usage assignment and marks an `AVAILABLE` vehicle `IN_USE`.
The vehicle must not be `RETIRED` or `UNDER_MAINTENANCE`.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `assignment_type` | string | Yes | `PROJECT`, `WORKER_TRANSPORT`, `MATERIAL_TRANSPORT`, `GENERAL_USE`, `OTHER` |
| `project_id` | integer | No | Nullable |
| `worker_id` | integer | No | Nullable |
| `driver_id` | integer | No | Nullable |
| `start_datetime` | date-time | Yes | |
| `end_datetime` | date-time | No | Nullable for open-ended assignment |
| `purpose` | string | No | |
| `remarks` | string | No | |

Provide at least one of `project_id`, `worker_id`, or a non-empty `purpose`;
otherwise the service returns `409` with code `MISSING_ASSIGNMENT_CONTEXT`. The
service also rejects overlapping assignments with `409` and code
`VEHICLE_OVERLAP`. Response includes `assignment_id`, `vehicle_id`,
`assignment_type`, datetimes, and `vehicle_status`.

### `POST /vehicles/{vehicle_id}/unassign/`

Closes the selected open assignment, or the current open assignment when
`assignment_id` is omitted. `end_datetime` defaults to the current server time
and must be after the assignment start. The vehicle becomes `AVAILABLE` when no
other open assignment has started.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `assignment_id` | integer | No | If omitted, the current open assignment is selected |
| `end_datetime` | date-time | No | Defaults to now |

Response is `200` and includes `assignment_id`, `end_datetime`, and
`vehicle_status`. The service returns `409` with code `NO_ACTIVE_ASSIGNMENT`
when no matching open assignment exists, and `409` with code
`INVALID_DATE_RANGE` when the supplied end is not after the start.

### `GET /vehicles/{vehicle_id}/history/`

Paginated assignment history with project, worker, driver, purpose,
datetimes, duration, and remarks.

### `GET /vehicles/{vehicle_id}/media/`, `POST /vehicles/{vehicle_id}/media/`

Media gallery and upload. Vehicle upload request contains required `file`
(image). The response contains `id`, `file_url`, and `created_at`.

### `POST /vehicles/{vehicle_id}/set-status/`

Request:

```json
{
  "status": "UNDER_MAINTENANCE"
}
```

Allowed values are the vehicle status choices. Returns the new status.

### `GET /vehicles/{vehicle_id}/bookings/`

Returns bookings for **only this vehicle** as a JSON array. `vehicle_id` may be
the numeric database ID or a business code such as `VEH-01`.

Query parameters:

| Parameter | Type | Description |
| --- | --- | --- |
| `start_after` | ISO date-time | Include bookings starting at or after this value |
| `end_before` | ISO date-time | Include bookings ending at or before this value |
| `status` | string | `SCHEDULED`, `CONFIRMED`, `CANCELLED`, or `COMPLETED` |

### `POST /vehicles/{vehicle_id}/bookings/`

Creates a future reservation. The URL vehicle is always the booking's vehicle;
there is no vehicle ID in the JSON body. `vehicle_id` may be a numeric ID or a
business code.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `driver` | integer | No | Nullable worker profile ID |
| `project` | integer | No | Nullable project ID |
| `worker` | integer | No | Nullable worker profile ID |
| `booking_type` | string | Yes | `PROJECT`, `WORKER_TRANSPORT`, `MATERIAL_TRANSPORT`, `GENERAL_USE`, or `OTHER` |
| `start_datetime` | date-time | Yes | Must be in the future |
| `end_datetime` | date-time | Yes | Must be after `start_datetime` |
| `status` | string | No | Defaults to `SCHEDULED` |
| `purpose` | string | No | Defaults to an empty string |
| `notes` | string | No | Defaults to an empty string |

A past start time returns `400` with a `start_datetime` field error. Overlapping
non-cancelled bookings for the same vehicle return `409` with code
`BOOKING_OVERLAP`. Response is `VehicleBookingReadSerializer` with status
`201` and these fields:

```text
id, vehicle, booked_by, booked_by_name, driver, driver_name,
project, project_number, worker, worker_name, booking_type,
start_datetime, end_datetime, status, purpose, notes,
created_at, updated_at
```

`vehicle`, `booked_by`, `driver`, `project`, and `worker` are numeric IDs (or
`null` where optional).

### `GET /vehicles/{vehicle_id}/bookings/{booking_id}/`

Returns one booking only when its vehicle matches the URL vehicle. The URL
`vehicle_id` may be numeric or a business code; `booking_id` is numeric.

### `PUT /vehicles/{vehicle_id}/bookings/{booking_id}/`

Partial-compatible update using the booking fields above. The implementation
passes `partial=True` for both `PUT` and `PATCH`, so a request may change only
`status`, `purpose`, or `notes`. Changing `start_datetime` to a past value
returns `400`; changing the time window to overlap another non-cancelled
booking returns `409`.

### `PATCH /vehicles/{vehicle_id}/bookings/{booking_id}/`

Partial update using the same booking fields and validation rules as `PUT`.
Returns `200` with the updated `VehicleBookingReadSerializer` object.

### `DELETE /vehicles/{vehicle_id}/bookings/{booking_id}/`

Physically deletes the booking and records a `VEHICLE_BOOKING_CANCELLED` audit
entry. Returns `204`.

### `GET /vehicles/bookings/`

Fleet-wide upcoming booking feed for the admin calendar. Returns a JSON array
containing bookings whose `start_datetime` is now or later. Cancelled bookings
are always excluded. It supports `start_after`, `end_before`, and `status`
filters; `status` is an exact choice filter.

### `GET /vehicles/stock/`

Returns status and vehicle-type counts, plus a vehicle-type breakdown:

```json
{
  "total": 5,
  "available": 2,
  "in_use": 2,
  "under_maintenance": 1,
  "retired": 0,
  "truck": 1,
  "van": 1,
  "pickup": 1,
  "car": 0,
  "bus": 0,
  "trailer": 1,
  "dumper": 0,
  "other": 0,
  "groups": [
    {
      "key": "TRUCK",
      "label": "Truck",
      "total": 1,
      "AVAILABLE": 1,
      "IN_USE": 0,
      "UNDER_MAINTENANCE": 0,
      "RETIRED": 0
    }
  ]
}
```

Vehicles have no free-text category, so `vehicle_type` plays that role. The
`groups` shape matches the tools stock endpoint: one key per `status` choice
(`AVAILABLE`, `IN_USE`, `UNDER_MAINTENANCE`, `RETIRED`), sorted by descending
`total`.

## 9. Audit and dashboard

### `GET /audit/`

Admin-only, paginated. Query parameters:

| Parameter | Description |
| --- | --- |
| `action` | Exact audit action |
| `entity_type` | Exact entity type |
| `entity_id` | Exact entity ID |
| `entity` | Either an entity ID or `entity_type#entity_id`, for example `Tool#12` |
| `actor` | Actor user ID |
| `date_from` | Inclusive created-date lower bound (`YYYY-MM-DD`) |
| `date_to` | Inclusive created-date upper bound (`YYYY-MM-DD`) |
| `ordering` | Defaults to `-created_at` |

Response fields:

```text
id, actor, actor_username, action, entity_type, entity_id,
metadata, created_at
```

### `GET /dashboard/`

Admin-only organisation summary:

```json
{
  "workers": { "total": 20, "active": 18 },
  "projects": { "total": 6, "active": 3 },
  "tools": { "available": 8, "assigned": 4, "attention": 2 },
  "ppe": { "issued": 12, "attention": 3 },
  "vehicles": { "available": 2, "in_use": 2 }
}
```

## 10. Worker performance

All endpoints under this section require `ADMIN`.

### `GET /workers/{worker_id}/performance/`

Paginated records for one worker.

Query parameter:

| Parameter | Description |
| --- | --- |
| `ordering` | Defaults to `-period_end,-id` |

### `POST /workers/{worker_id}/performance/`

Creates an evaluation for the URL worker.

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `period_start` | date | Yes | |
| `period_end` | date | Yes | Must be on/after `period_start` |
| `attendance_time` | integer 1-5 | No | Nullable |
| `ppe_replacement_duration` | integer 1-5 | No | Nullable |
| `job_training_attendance` | integer 1-5 | No | Nullable |
| `job_time` | integer 1-5 | No | Nullable |
| `advance_loan_repayment` | integer 1-5 | No | Nullable |
| `notes` | string | No | |
| `is_visible_to_worker` | boolean | No | Defaults to `false` |

Response is `PerformanceRecordSerializer`.

### `GET /workers/{worker_id}/performance/{record_id}/`

Returns one record for the URL worker.

### `PUT /workers/{worker_id}/performance/{record_id}/`

Full update using the write fields above. Both `period_start` and `period_end`
are required. Score fields accept `null` or an integer from `1` through `5`.
The read response also contains `worker_detail`, `evaluator`,
`evaluator_name`, `overall_score`, `created_at`, and `updated_at`.

### `PATCH /workers/{worker_id}/performance/{record_id}/`

Partial update using the write fields above.

### `DELETE /workers/{worker_id}/performance/{record_id}/`

Deletes the record. Returns `204`.

## 11. Attendance

All endpoints require `ADMIN`, or a worker whose profile has
`is_supervisor=true`.

- A **supervisor** may only see and mark attendance for the **projects they are
  currently assigned to**, and only for workers assigned to that project. They
  must always supply a `project`.
- An **admin** may mark attendance for **any** employee, whether or not they
  are assigned to a project, and may omit `project` for a company-wide entry.

Uniqueness follows the shape of the entry:

- With a project: one record per worker + project + date.
- Without a project: one record per worker + date, so a company-wide entry
  cannot be duplicated for the same day.

Punch-out is optional, so a day can be opened and closed separately.

### Working date window

`date` must be **today or one of the two preceding days** in
`ATTENDANCE_TIMEZONE`. This is a daily log, not a retro-entry system:

| Code | Status | Cause |
| --- | --- | --- |
| `ATTENDANCE_FUTURE_DATE` | `409` | `date` is after today |
| `ATTENDANCE_TOO_OLD` | `409` | `date` is more than `ATTENDANCE_MAX_BACKDATE_DAYS` days back |

### `GET /attendance/`

Paginated, admin sees everything; a supervisor sees only their own projects.
Admin company-wide entries (`project = null`) are visible to admins only.
Ordering defaults to `-date,worker_id`.

Query parameters:

| Parameter | Description |
| --- | --- |
| `worker` | Worker profile ID |
| `project` | Project ID |
| `date` | Exact working date (`YYYY-MM-DD`) |
| `date_from` | Inclusive lower bound |
| `date_to` | Inclusive upper bound |
| `is_open` | `true` returns records with no punch-out yet |
| `ordering` | Comma-separated: `date`, `punch_in`, `worker_id`, `project_id` |

Response fields:

```text
id, worker, worker_detail { id, employee_id, full_name, designation },
project, project_detail { id, project_number, project_name },
date, punch_in, punch_out, work_hours, is_late, late_by_minutes, is_open,
notes, recorded_by, recorded_by_name, created_at, updated_at
```

`is_late`, `late_by_minutes`, `work_hours` and `is_open` are **derived, never
stored**, so changing `ATTENDANCE_START_TIME` re-classifies existing records
immediately.

- `is_late` is true when `punch_in` is **after** the shift start.
- `late_by_minutes` is whole minutes late, otherwise `0`.
- `work_hours` is `(punch_out - punch_in)` in hours to 2 decimals, or `null`
  while the day is still open.
- Punching in exactly at the shift start is **not** late.

### `POST /attendance/`

Request:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `worker` | integer | Yes | Worker profile ID. An admin may mark anyone; a supervisor's worker must be on the chosen project |
| `project` | integer | Admin: no. Supervisor: yes | Project ID. Omit or send `null` for a company-wide entry |
| `date` | date | Yes | Working date; today or up to 2 days back |
| `punch_in` | date-time | Yes | ISO 8601 with an offset, on the working date |
| `punch_out` | date-time | No | Must be after `punch_in`; omit to leave the day open. Also on the working date |
| `notes` | string | No | |

`punch_in` and `punch_out` must fall on the same calendar day as `date` **in
`ATTENDANCE_TIMEZONE`**, otherwise the request is rejected with `400`. Both the
late flag and the worked hours are derived from `date`, so a timestamp from
another day would report nonsense (marking yesterday with today's clock time
would read as ~25 hours late). When backdating, send timestamps for the day
being backdated, not for today.

Returns `201` with the read shape above. Errors:

| Code | Status | Cause |
| --- | --- | --- |
| `PROJECT_REQUIRED` | `409` | A supervisor tried to mark attendance with no project |
| `SUPERVISOR_OUT_OF_SCOPE` | `409` | Supervisor is not assigned to that project |
| `WORKER_NOT_ON_PROJECT` | `409` | Worker has never been assigned to that project |
| `ATTENDANCE_ALREADY_RECORDED` | `409` | A record already exists for that worker + project + date (or worker + date when no project) |
| `ATTENDANCE_FUTURE_DATE` | `409` | `date` is after today |
| `ATTENDANCE_TOO_OLD` | `409` | `date` is outside the backdate window |
| field error on `punch_in` / `punch_out` | `400` | The timestamp is not on the working date |

### `GET /attendance/{id}/`

Returns one record. A supervisor asking for a record outside their projects
gets `404` with code `ATTENDANCE_NOT_FOUND`.

### `PUT /attendance/{id}/`, `PATCH /attendance/{id}/`

Updates the record. `PUT` is a full update, `PATCH` is partial. Scope and
assignment are re-checked, so a supervisor cannot move a record onto a project
they do not supervise.

Omitting `project` in a `PATCH` leaves it unchanged. Sending `project: null`
explicitly clears it and turns the record into a company-wide entry; that is
admin-only, and a supervisor gets `409` with code `PROJECT_REQUIRED`.

### `DELETE /attendance/{id}/`

**Admin only** — a supervisor gets `403`. Returns `204`.

### Late threshold configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ATTENDANCE_START_TIME` | `08:00` | Shift start, compared in the attendance timezone |
| `ATTENDANCE_TIMEZONE` | `Asia/Kolkata` | Timezone the threshold and the date window are interpreted in |
| `ATTENDANCE_MAX_BACKDATE_DAYS` | `2` | How many days back attendance may be marked |

Date-times are stored in UTC. The late comparison is done in
`ATTENDANCE_TIMEZONE`, so 08:30 IST (03:00 UTC) is correctly late against an
08:00 IST shift. Setting the threshold against server time would mark almost
everyone late.

## 12. Health and generated schema

### `GET /api/health/`

Public. Returns:

```json
{
  "status": "ok"
}
```

### Generated schema

The schema views are mounted outside `/api/v1/`:

```text
GET /api/schema/
GET /api/docs/
GET /api/redoc/
```

When changing an endpoint, verify the generated schema with:

```bash
python manage.py spectacular --file /tmp/workforce-schema.yml --validate
```

The command reports `drf_spectacular` warnings/errors for `APIView` endpoints
because those views do not declare serializers for schema inference. The
command can still write the schema, but the field lists in this document remain
authoritative until those views are decorated with explicit `@extend_schema`
metadata.
