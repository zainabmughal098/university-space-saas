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

`/dashboard`, `/spaces`, `/academic`, and `/schedule` are functional. `/find-room` and
`/reservations` are intentional future-feature placeholders. `/` redirects to
the dashboard. Booking and availability-search UIs remain deferred.

## Schedule management (Phase 4D)

`/schedule` lists official classes chronologically, resolving course/section,
faculty/department, and room/campus/building/floor names from existing list APIs.
Each list is loaded once (including all pages) per refresh. Summary counts show
all entries, active entries, and active entries starting after the last refresh.
Filters cover start date, room, faculty, section, course, and active status. The
start-date filter uses the workspace timezone and matches the date the entry starts;
it is not an overlap-with-day search. Summary counts remain unfiltered.

Create and edit use named selectors and local date/time inputs. New entries offer
active sections, faculty, and rooms; editing also preserves the current inactive
references. PATCH supports all existing editable fields, including active status.
Deactivation and reactivation use the existing endpoints; no hard delete is offered.
Successful changes refresh relationship data and entries. Errors retain form input.
No automatic room assignment, recurrence, or conflict override is implemented.

The backend previously did not expose workspace timezone metadata. A read-only
`GET /api/workspaces/{workspace_id}` now returns existing workspace fields including
`default_timezone`. Schedule uses that value, not the development display label or
browser timezone. Missing/invalid timezone metadata blocks schedule management.
There is no timezone-editing UI in this phase.

`@js-temporal/polyfill` converts workspace-local inputs to UTC ISO timestamps with
`Z` for FastAPI. Display includes the workspace timezone and each instant's UTC
offset. Nonexistent local times during forward clock changes are rejected.
Repeated times require an explicit earlier/later choice for each endpoint. Existing
unchanged timestamps preserve their exact instants by default, including fractional
seconds; an explicit occurrence choice can change them. Intervals remain half-open,
`[start, end)`, with strictly positive duration and adjacent entries allowed.

The backend remains authoritative for capacity and conflicts. A pre-submit capacity
warning shows student count versus room capacity without bypassing server checks.
HTTP 409 details distinguish room, faculty, section, and approved reservation
conflicts and show their named resources and local intervals. Capacity errors show
the selected sizes. There is no JavaScript scheduling engine.

Workspace changes clear forms, filters, and data and abort/ignore prior requests.
Authentication is still deferred; knowing a workspace UUID does not establish
permission. Large lists still load all pages and changes from other sessions require
Refresh data. A cancelled browser request cannot undo a write already accepted by
FastAPI. Automated tests use mocked APIs and disposable backend databases only.

## Academic management (Phase 4C)

Open `/academic` after selecting a development workspace. Eight summary cards show
total and active departments, faculty, courses, and sections. Four resource tabs
use the same table and inline create/edit pattern as Spaces. All records support
create, edit, deactivate, and reactivate; there are no delete controls.

Faculty and courses belong to departments; sections belong to courses. Selectors
show names/codes, and section course labels include department context. Creation
offers active parent records only. Editing also includes the currently assigned
parent if inactive, so an existing relationship can be retained. An active course
may still have an inactive department; its context explicitly marks that department.
Missing active parents disable creation with setup guidance.

Forms send only backend-supported fields. Faculty email receives basic format
validation; section student counts must be positive 32-bit integers. Backend errors
are displayed without clearing entered values. Successful changes reload all four
lists so counts, labels, and parent selectors stay current. Deactivation does not
cascade. Use Refresh data for changes made in another session.

Workspace changes discard unsaved forms and old data, abort outstanding requests,
and load the new workspace. Aborting cannot undo a write already accepted by the
server. Authentication and membership authorization remain pending; the selector
does not establish permission. Lists load all API pages for now, and a failed list
blocks management until retry succeeds rather than showing incomplete parents.
Tests mock API calls; no live records are created or modified by automated checks.

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
- `src/features`: dashboard, Spaces/Academic/Schedule UIs, and resource/form definitions.
- `src/app`: route entry points, root layout, global CSS.

Run `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build`.
Client tests use Node, tsx, jsdom, and React Testing Library, mock fetch, and never
contact the development database. They exercise forms, hierarchy, validation,
workspace switching, errors, active state changes, and facility assignments.
Local CORS permits only localhost/127.0.0.1 on port 3000, GET/POST/PATCH/DELETE, and no browser
credentials. Deployments need their own reviewed origin configuration. CORS is
not authentication and does not restrict non-browser clients.

See the [root README](../README.md) for setup and validation commands.
