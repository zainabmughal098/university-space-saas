"""Explicit, idempotent Nova development data setup; this is not authentication."""
import contextlib
import io
from pathlib import Path
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from app.database import get_engine
from app.models import Membership, MembershipRole, User, Workspace

WORKSPACE_ID = UUID("8824a866-a665-4f7a-a1de-dbe72bb8dd37")
DEMO_EMAIL = "admin@nova-university.demo"
DEMO_NAME = "Nova Admin"


class MissingDemoWorkspace(Exception):
    pass


def seed_demo_member(engine: Engine) -> str:
    """Commit only this demo identity and membership, or roll back all changes.

    Locking the target workspace serializes concurrent runs on PostgreSQL.
    Existing uniqueness constraints remain the final protection against duplicates.
    """
    with Session(engine) as session, session.begin():
        workspace = session.scalar(select(Workspace).where(
            Workspace.id == WORKSPACE_ID).with_for_update())
        if workspace is None:
            raise MissingDemoWorkspace()

        user = session.scalar(select(User).where(User.email == DEMO_EMAIL).with_for_update())
        user_created = user is None
        if user is None:
            user = User(email=DEMO_EMAIL, display_name=DEMO_NAME)
            session.add(user)
            session.flush()
        else:
            user.display_name = DEMO_NAME

        membership = session.scalar(select(Membership).where(
            Membership.user_id == user.id,
            Membership.workspace_id == WORKSPACE_ID,
        ).with_for_update())
        membership_created = membership is None
        if membership is None:
            membership = Membership(user_id=user.id, workspace_id=WORKSPACE_ID,
                                    role=MembershipRole.OWNER, is_active=True)
            session.add(membership)
        else:
            membership.is_active = True
            membership.role = MembershipRole.OWNER

    # The transaction has committed before reporting success.
    return (f"Nova demo user {'created' if user_created else 'reused'}; "
            f"membership {'created' if membership_created else 'reused'}; active owner ensured.")


def main() -> int:
    # Do not emit driver/configuration diagnostics, which may contain connection data.
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            engine = get_engine()
            try:
                result = seed_demo_member(engine)
            finally:
                engine.dispose()
    except MissingDemoWorkspace:
        print(f"Seed failed: Nova workspace {WORKSPACE_ID} does not exist. No data changed.")
        return 1
    except Exception:
        print("Seed failed; connection details suppressed. Check configuration and database state before retrying.")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
