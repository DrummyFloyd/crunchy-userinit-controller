from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .config import K8S_API_NS, PGBOUNCER_ROLE
from .database import DatabaseManager
from .models import PgUserSecret


@dataclass(frozen=True)
class Fix:
    """Opt-in fix enabled per user by an annotation on the PostgresCluster.

    apply() is idempotent and returns whether it changed something.
    """

    name: str
    # "cluster": connection to the postgres database, "database": to the user's one
    scope: Literal["cluster", "database"]
    apply: Callable[[DatabaseManager, PgUserSecret], Awaitable[bool]]
    # GrantApplied event message, posted when apply() changed something
    event: Callable[[PgUserSecret], str]

    @property
    def annotation(self) -> str:
        return f"{K8S_API_NS}/{self.name}"


FIXES = (
    Fix(
        "pgbouncer-connect",
        "cluster",
        lambda db, s: db.grant_pgbouncer_connect(s.dbname),
        lambda s: f"CONNECT on database {s.dbname} to {PGBOUNCER_ROLE}",
    ),
    Fix(
        "public-schema",
        "database",
        lambda db, s: db.grant_public_schema(s.role_name),
        lambda s: f"ALL on schema public of database {s.dbname} to {s.role_name}",
    ),
)
