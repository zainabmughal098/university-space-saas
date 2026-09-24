# Frontend

Next.js with TypeScript, App Router, ESLint, and a src/ directory.
Phase 4A provides a responsive workspace dashboard. System fonts and plain CSS
keep builds independent of font downloads; no UI dependencies were added.

## Run locally

Start FastAPI in a separate terminal from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

From `frontend/`, install dependencies with `npm ci`. If `.env.local` does not
exist, copy `.env.example` to `.env.local`. Configure the public, non-secret value:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Run `npm run dev`, then open http://localhost:3000/dashboard. Restart Next.js
after changing environment configuration; production public values are baked in
at build time. Never put PostgreSQL URLs, passwords, or Supabase keys here.
All application reads go from the browser to FastAPI, which owns database access.

## Workspace selection and data

Enter an existing workspace UUID in the development selector. The optional name
is a display label you supply, not a name verified by the backend (there is no
workspace metadata endpoint). Selection is held in React context across navigation
and resets on browser reload. There are no hardcoded university IDs or names.
Authentication and membership authorization remain pending: choosing a UUID is
not proof of permission. This is a development interface, not an access boundary.

The dashboard shows campuses, buildings, total/active rooms, departments, faculty,
courses, and sections; totals include inactive records unless labeled active.
It also shows the next five active classes and five most recent reservations with
their statuses. Activity uses actual room/section UUIDs from API responses.
All displayed activity times explicitly use UTC, not browser local time.
Refresh data to update counts and the reference time for upcoming classes.

List APIs are fetched in 200-record pages until exhausted. This prevents first-page
undercounting; counts are read-time observations, not a transactional snapshot.
For large datasets, server aggregates/date filtering will be a future improvement.
Each card/section handles loading, empty data, errors, and retry independently.
Workspace changes unmount the previous dashboard and abort its requests.

`/dashboard` is functional. `/spaces`, `/academic`, `/schedule`, `/find-room`, and
`/reservations` are intentional future-feature placeholders. `/` redirects to
the dashboard. No management or booking writes are implemented.

## Organization and checks

- `src/components`: shell, workspace context/selector, shared state components.
- `src/lib`: typed centralized API client and backend response types.
- `src/features`: dashboard data loading and display.
- `src/app`: route entry points, root layout, global CSS.

Run `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build`.
Client tests mock fetch and never contact the development database.
Local CORS permits only localhost/127.0.0.1 on port 3000, GET reads, and no browser
credentials. Deployments need their own reviewed origin configuration. CORS is
not authentication and does not restrict non-browser clients.

See the [root README](../README.md) for setup and validation commands.
