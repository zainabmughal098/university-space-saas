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
from sqlalchemy import inspect, text

from app.database import Base, get_engine
from app.models import Membership, MembershipRole, User, Workspace


def validate() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.check(config)
    print("alembic check: PASS (no new upgrade operations)")
    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all() == ["0001_initial_tenants"]
            print("Migration revision: 0001_initial_tenants (head)")
            context = MigrationContext.configure(connection, opts={"compare_server_default": True})
            assert not compare_metadata(context, Base.metadata)
            inspector = inspect(connection)
            for table in Base.metadata.sorted_tables:
                assert inspector.get_pk_constraint(table.name)["constrained_columns"] == ["id"]
                assert all(not column["nullable"] for column in inspector.get_columns(table.name))
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
                "WHERE nspname = current_schema() AND relname IN ('users', 'workspaces', 'memberships')"
            )).scalars().all()
            assert len(rls) == 3 and not any(rls)
            print("RLS: remains disabled on the three foundation tables")
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
