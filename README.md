# University Space

A planned multi-tenant B2B SaaS application for university scheduling and space
management. Any university will be able to create its own private workspace and
configure its infrastructure; the application is not tied to a specific university.

## Current status

The Phase 0 applications now include an initial PostgreSQL database foundation:
SQLAlchemy models for users, university workspaces, and memberships, with Alembic
migrations. Phase 2A's physical infrastructure schema is migrated and verified.
Phase 2B provides workspace-scoped infrastructure APIs, with no new migration.
Phase 3A's `0003_academic_scheduling` migration has been applied and validated.
Phase 3B provides workspace-scoped academic and schedule-entry APIs.
Phase 3C adds deterministic schedule conflict/capacity validation and room availability.
Phase 3D adds room reservation requests, approval/rejection/cancellation, and shared
room occupancy checks. Migration `0004_room_reservations` has been applied and validated.
Phase 4A adds a workspace dashboard with real API data and navigation placeholders.
Phase 4B adds Spaces management: campuses, buildings, floors, room types, facilities,
rooms, and room-facility assignments. See [Spaces usage](frontend/README.md).
Phase 4C adds Academic management for departments, faculty, courses, and sections,
with workspace-scoped forms and human-readable parent selectors.
Phase 4D adds chronological schedule management, workspace-local time entry,
relationship filters, and backend conflict/capacity feedback.
Authentication, database-enforced read isolation (RLS),
imports, analytics, optimization, and AI are not implemented.

## Repository and architecture

```text
frontend/   Next.js presentation layer and its npm dependencies
backend/    FastAPI API and its isolated Python dependencies
docs/       Architecture notes and future design decisions
infra/      Future local service and deployment configuration
```

The frontend and backend run independently. The frontend will call the API;
the backend will own authorization, business rules, and database access. The
PostgreSQL database is backend-only. Process health does not require a database.
Supabase-hosted PostgreSQL is the primary development database; a local PostgreSQL
installation is not required.
See [architecture notes](docs/architecture.md).

## Prerequisites

- Node.js 24 and npm 11 (the versions used for this setup)
- Python 3.14 (on Windows, use the `py -3.14` launcher)

On the setup machine, `python` resolves to a Microsoft Store alias, so use `py`
to create the environment and the explicit virtual-environment interpreter after
that. The installed Python emits a `Could not find platform independent libraries`
warning; the API import and actual HTTP startup checks still pass. Repairing the
system Python installation is outside this repository setup.

## Frontend

From the repository root:

```powershell
cd frontend
npm ci
# If absent, copy .env.example to .env.local; see frontend/README.md.
npm run dev
```

Open http://localhost:3000. Checks and production build:

```powershell
npm run lint
npm run typecheck
npm run build
```

## Backend

From the repository root, using PowerShell:

```powershell
cd backend
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The API runs at http://127.0.0.1:8000. Process health is available at `/health`,
and interactive API documentation at `/docs`. The frontend dashboard reads this API.
Local CORS allows GET/POST/PATCH/DELETE from localhost/127.0.0.1 on port 3000 only.
See [frontend setup and workspace selection](frontend/README.md).

Basic import check, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -c "from app.main import app; assert app.title == 'University Space API'"
```

`pyproject.toml` declares direct backend dependencies. `requirements.lock` captures
the exact resolved runtime dependencies used for validation; update both when
intentionally changing dependencies. The application runs directly from `backend/`.

## Environment and generated files

The frontend and backend each include a `.env.example` with placeholders only.
Database access requires `DATABASE_URL` in `backend/.env` or the process environment.
No real secrets are included. See [backend database setup](backend/README.md).
Never put secrets in a `NEXT_PUBLIC_` variable: those values are browser-visible.

Git ignores local environment files, node modules, virtual environments, caches,
and build outputs. Dependency manifests and lock files should be versioned.
