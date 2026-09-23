"""Read-only live checks. Never emit connection details or raw exceptions."""

import contextlib
import io
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.database import Base, get_engine
from app.models import Membership, MembershipRole, User, Workspace


def validate_academic_schema(connection) -> None:
    """Inspect an existing connection; usable by credential-free migration tests."""
    inspector = inspect(connection)
    unique_keys = {
        "departments": [("workspace_id", "id"), ("workspace_id", "code")],
        "faculty": [("workspace_id", "id"), ("workspace_id", "email")],
        "courses": [("workspace_id", "id"), ("workspace_id", "code")],
        "sections": [("workspace_id", "id"), ("workspace_id", "course_id", "name")],
    }
    parents = {
        "faculty": [("department_id", "departments")],
        "courses": [("department_id", "departments")],
        "sections": [("course_id", "courses")],
        "schedule_entries": [("room_id", "rooms"), ("section_id", "sections"), ("faculty_id", "faculty")],
    }
    for table, keys in unique_keys.items():
        actual = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table)}
        assert set(keys) <= actual
    for table in [*unique_keys, "schedule_entries"]:
        foreign_keys = inspector.get_foreign_keys(table)
        assert any(fk["constrained_columns"] == ["workspace_id"] and fk["referred_table"] == "workspaces"
                   and fk["referred_columns"] == ["id"] for fk in foreign_keys)
        for column, parent in parents.get(table, []):
            assert any(fk["constrained_columns"] == ["workspace_id", column] and fk["referred_table"] == parent
                       and fk["referred_columns"] == ["workspace_id", "id"] for fk in foreign_keys)
        expected_indexes = {tuple(column.name for column in index.columns) for index in Base.metadata.tables[table].indexes}
        actual_indexes = {tuple(index["column_names"]) for index in inspector.get_indexes(table)}
        assert expected_indexes <= actual_indexes
        if connection.dialect.name == "postgresql":
            for column in inspector.get_columns(table):
                if column["name"] in {"created_at", "starts_at", "ends_at"}:
                    assert column["type"].timezone
    for table, name, expression in [
        ("sections", "ck_sections_positive_student_count", "student_count>0"),
        ("schedule_entries", "ck_schedule_entries_positive_interval", "ends_at>starts_at"),
    ]:
        checks = {item["name"]: item["sqltext"] for item in inspector.get_check_constraints(table)}
        assert re.sub(r'[\s()"]', '', checks[name]) == expression


def validate() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.check(config)
    print("alembic check: PASS (no new upgrade operations)")
    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            head = ScriptDirectory.from_config(config).get_current_head()
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all() == [head]
            print(f"Migration revision: {head} (head)")
            context = MigrationContext.configure(connection, opts={"compare_server_default": True})
            assert not compare_metadata(context, Base.metadata)
            validate_academic_schema(connection)
            inspector = inspect(connection)
            for table in Base.metadata.sorted_tables:
                assert inspector.get_pk_constraint(table.name)["constrained_columns"] == list(table.primary_key.columns.keys())
                for column in inspector.get_columns(table.name):
                    assert column["nullable"] == table.c[column["name"]].nullable
            for table, columns in [("users", ["email"]), ("workspaces", ["slug"]),
                                   ("memberships", ["user_id", "workspace_id"])]:
                assert columns in [item["column_names"] for item in inspector.get_unique_constraints(table)]
            foreign_keys = inspector.get_foreign_keys("memberships")
            assert len(foreign_keys) == 2
            for column, target in [("user_id", "users"), ("workspace_id", "workspaces")]:
                assert any(fk["constrained_columns"] == [column] and fk["referred_table"] == target
                           and fk["referred_columns"] == ["id"] and fk["options"].get("ondelete") == "CASCADE"
                           for fk in foreign_keys)
            assert ["workspace_id"] in [item["column_names"] for item in inspector.get_indexes("memberships")]
            checks = inspector.get_check_constraints("memberships")
            role_check = next(item for item in checks if item["name"] == "ck_memberships_membership_role")
            assert set(re.findall(r"'([^']+)'", role_check["sqltext"])) == {role.value for role in MembershipRole}
            assert "role" in role_check["sqltext"]
            for parent, attribute in [(User, "user"), (Workspace, "workspace")]:
                relation = inspect(parent).relationships["memberships"]
                assert relation.uselist and relation.back_populates == attribute
                assert inspect(Membership).relationships[attribute].mapper.class_ is parent
            print("Models/schema/defaults, primary/foreign/unique keys, indexes, roles and relationships: PASS")
            rls = connection.execute(text(
                "SELECT relrowsecurity FROM pg_class JOIN pg_namespace ON pg_namespace.oid = relnamespace "
                "WHERE nspname = current_schema() AND relname = ANY(:tables)"
            ), {"tables": list(Base.metadata.tables)}).scalars().all()
            assert len(rls) == len(Base.metadata.tables) and not any(rls)
            print("RLS: remains disabled on all application tables")
    finally:
        engine.dispose()


if __name__ == "__main__":
    captured = io.StringIO()
    try:
        # Capture library diagnostics too: connection failures can include hosts/users.
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            validate()
    except Exception as error:
        print(f"Database validation failed ({type(error).__name__}); connection details suppressed.")
        sys.exit(1)
    # Emit only our known status lines, never arbitrary library diagnostics.
    for line in captured.getvalue().splitlines():
        if line.startswith(("alembic check: PASS", "Migration revision:", "Models/schema/defaults,", "RLS:")):
            print(line)
