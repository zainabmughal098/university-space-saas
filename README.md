# University Space

A planned multi-tenant B2B SaaS application for university scheduling and space
management. Any university will be able to create its own private workspace and
configure its infrastructure; the application is not tied to a specific university.

## Current status

The Phase 0 applications now include an initial PostgreSQL database foundation:
SQLAlchemy models for users, university workspaces, and memberships, with Alembic
migrations. Authentication, enforced tenant isolation (including RLS), scheduling,
reservations, imports, analytics, optimization, and AI are not implemented.

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
and interactive API documentation at `/docs`. No frontend/API integration is
wired yet, so cross-origin middleware is not needed in this phase.

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
