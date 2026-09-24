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
All application reads and writes go through FastAPI, which owns database access.

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

`/dashboard` and `/spaces` are functional. `/academic`, `/schedule`, `/find-room`, and
`/reservations` are intentional future-feature placeholders. `/` redirects to
the dashboard. Booking and academic management UIs remain deferred.

## Spaces management (Phase 4B)

Select a workspace and open `/spaces`. Summary counts cover campuses, buildings,
floors, rooms, active rooms, room types, and facilities. Resource buttons switch
between six lists; create/edit opens one inline panel with cancel/save actions.
Tables scroll horizontally on smaller screens and forms use labeled controls.

Configure campuses, then buildings, floors, room types, and rooms. Parent selectors
show names/codes and the campus/building/floor hierarchy, never UUID inputs.
Missing parents disable creation with guidance. Inactive parents remain selectable
because the infrastructure API allows them; their labels identify inactive status.
Use Refresh data after changes made in another browser/session.

Campuses, buildings, floors, and rooms support deactivate and reactivate. These
actions do not cascade. There are no hard-delete controls. Room types and facilities
support create/edit only, matching their API capabilities. Empty optional address
or description fields are submitted as null; capacities must be positive integers,
and floor numbers can be zero or negative. Backend validation remains authoritative.

Rooms display capacity, type, floor/building/campus context, and status. The
Facilities action opens the room's assigned facilities, with a named selector to
assign existing facilities and Remove controls to unlink them. Removing a link
does not delete the facility. New facilities are created in the Facilities tab.

Successful record changes refetch all six lists, refreshing summaries and parent
options. Facility changes reload that room's assignments. Errors preserve form
input; failed loads have retry controls. If a write's network outcome is unknown,
refresh before retrying to check whether the server applied it. Changing workspaces
clears forms and old data and aborts outstanding requests; aborting a request cannot
undo a write already accepted by the server. Unsaved edits are discarded on tab or
workspace changes. Authentication remains deferred; this is development tooling.

Spaces loads all paginated lists for modest datasets; server-side search and UI
pagination remain future improvements. A failed prerequisite list blocks management
until retry succeeds, so parent selectors never silently use partial data.

## Organization and checks

- `src/components`: shell, workspace context/selector, shared state components.
- `src/lib`: typed centralized API client and backend response types.
- `src/features`: dashboard, Spaces UI, and reusable resource/form definitions.
- `src/app`: route entry points, root layout, global CSS.

Run `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build`.
Client tests use Node, tsx, jsdom, and React Testing Library, mock fetch, and never
contact the development database. They exercise forms, hierarchy, validation,
workspace switching, errors, active state changes, and facility assignments.
Local CORS permits only localhost/127.0.0.1 on port 3000, GET/POST/PATCH/DELETE, and no browser
credentials. Deployments need their own reviewed origin configuration. CORS is
not authentication and does not restrict non-browser clients.

See the [root README](../README.md) for setup and validation commands.
