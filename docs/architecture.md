# Architecture

The repository contains a Next.js frontend and an independent FastAPI backend.
The frontend owns presentation. The backend will own authorization, validation,
tenant isolation, and scheduling decisions. PostgreSQL will be accessible only
through the backend. Database models and migrations have not been introduced.

The planned tenant boundary is one university workspace. Future tenant-owned
records will carry a workspace ID, with application scoping, tenant-aware foreign
keys, and PostgreSQL row-level security. None of these controls is implemented yet.

The backend will grow as a modular monolith. Feature modules and supporting
directories will be introduced when they contain actual code.

Before feature development, finalize authentication/session handling, workspace
roles, reservation approval policy, campus timezone handling, and database setup.
The default scheduling proposal uses timestamped occurrences and half-open time
intervals. These remain design decisions, not current functionality.

Future LLM integration may interpret requests; the database and scheduling engine
will remain authoritative for availability and scheduling decisions.
