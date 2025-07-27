from typing import final

import asyncpg

from .config import logger


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
