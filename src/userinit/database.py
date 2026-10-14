from typing import final

import asyncpg

from .config import PGBOUNCER_ROLE, logger


@final
class DatabaseManager:
    """Handles PostgreSQL database operations"""

    def __init__(self, connection: asyncpg.Connection):
        self.connection = connection

    async def change_owner(self, database_name: str, role_name: str) -> None:
        """
        Change the owner of a PostgreSQL database using asyncpg with improved input validation.

        Parameters:
        - database_name (str): The name of the database.
        - role_name (str): The name of the new owner role.

        All exceptions are delegated to the caller.
        """
        check_owner_sql = """
        SELECT pg_roles.rolname
        FROM pg_database
        JOIN pg_roles ON pg_database.datdba = pg_roles.oid
        WHERE pg_database.datname = $1;
        """

        # Unfortunately there is no way to use prepared statements for DDL operations like this
        alter_sql = f'ALTER DATABASE "{database_name}" OWNER TO "{role_name}"'

        current_owner = await self.connection.fetchval(check_owner_sql, database_name)

        if current_owner == role_name:
            logger.info(
                f"current owner of {database_name} is {current_owner}. nothing to do."
            )
            return
        else:
            logger.info(
                f"changing owner of db={database_name} from old_owner={current_owner} to new_owner={role_name} with '{alter_sql}'"
            )
            _ = await self.connection.execute(alter_sql)

        logger.info(
            f"database owner changed successfully: db={database_name} new_owner={role_name} old_owner={current_owner}"
        )

    async def grant_pgbouncer_connect(self, database_name: str) -> bool:
        """
        Grant CONNECT on the database to the PgBouncer auth user.

        PgBouncer runs its auth_query inside the target database, so it fails
        when an app revokes CONNECT from PUBLIC (e.g. the Nextcloud installer).
        No-op when PgBouncer is not enabled (role missing) or already granted.
        Returns whether the GRANT was run.

        All exceptions are delegated to the caller.
        """
        has_role = await self.connection.fetchval(
            "SELECT 1 FROM pg_roles WHERE rolname = $1;", PGBOUNCER_ROLE
        )
        if not has_role:
            logger.info(f"role {PGBOUNCER_ROLE} not found. nothing to do.")
            return False

        can_connect = await self.connection.fetchval(
            "SELECT has_database_privilege($1, $2, 'CONNECT');",
            PGBOUNCER_ROLE,
            database_name,
        )
        if can_connect:
            logger.info(
                f"{PGBOUNCER_ROLE} can already connect to {database_name}. nothing to do."
            )
            return False

        _ = await self.connection.execute(
            f'GRANT CONNECT ON DATABASE "{database_name}" TO "{PGBOUNCER_ROLE}"'
        )
        logger.info(
            f"connect granted successfully: db={database_name} role={PGBOUNCER_ROLE}"
        )
        return True

    async def grant_public_schema(self, role_name: str) -> bool:
        """
        Grant ALL on the public schema to the role.

        Since PostgreSQL 15 the database owner already has it through
        pg_database_owner, but not on databases created by an older version.
        Must run on a connection to the target database.
        Returns whether the GRANT was run.

        All exceptions are delegated to the caller.
        """
        can_create = await self.connection.fetchval(
            "SELECT has_schema_privilege($1, 'public', 'CREATE');", role_name
        )
        if can_create:
            logger.info(
                f"{role_name} can already create in schema public. nothing to do."
            )
            return False

        _ = await self.connection.execute(
            f'GRANT ALL ON SCHEMA public TO "{role_name}"'
        )
        logger.info(f"public schema granted successfully: role={role_name}")
        return True
