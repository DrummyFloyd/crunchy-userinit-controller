import sys
from pathlib import Path

import pytest

# Add src directory to path so we can import userinit
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the database module
from userinit.database import DatabaseManager


@pytest.mark.unit
class TestDatabaseManager:
    """Test the DatabaseManager class."""

    @pytest.mark.asyncio
    async def test_change_owner_same_owner(self, mock_asyncpg_connection):
        # Test when current owner is the same as the new owner
        mock_asyncpg_connection.fetchval.return_value = "test_user"

        db_manager = DatabaseManager(mock_asyncpg_connection)
        await db_manager.change_owner("test_db", "test_user")

        mock_asyncpg_connection.fetchval.assert_called_once()
        mock_asyncpg_connection.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_change_owner_different_owner(self, mock_asyncpg_connection):
        # Test when current owner is different from new owner
        mock_asyncpg_connection.fetchval.return_value = "old_user"

        db_manager = DatabaseManager(mock_asyncpg_connection)
        await db_manager.change_owner("test_db", "new_user")

        mock_asyncpg_connection.fetchval.assert_called_once()
        mock_asyncpg_connection.execute.assert_called_once_with(
            'ALTER DATABASE "test_db" OWNER TO "new_user"'
        )

    @pytest.mark.asyncio
    async def test_change_owner_database_error(self, mock_asyncpg_connection):
        # Test when database operation fails
        mock_asyncpg_connection.fetchval.return_value = "old_user"
        mock_asyncpg_connection.execute.side_effect = Exception("DB Error")

        db_manager = DatabaseManager(mock_asyncpg_connection)

        with pytest.raises(Exception, match="DB Error"):
            await db_manager.change_owner("test_db", "new_user")

    @pytest.mark.asyncio
    async def test_grant_pgbouncer_connect_no_role(self, mock_asyncpg_connection):
        # PgBouncer not enabled: the role does not exist
        mock_asyncpg_connection.fetchval.return_value = None

        db_manager = DatabaseManager(mock_asyncpg_connection)
        await db_manager.grant_pgbouncer_connect("test_db")

        mock_asyncpg_connection.fetchval.assert_called_once()
        mock_asyncpg_connection.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_grant_pgbouncer_connect_already_granted(
        self, mock_asyncpg_connection
    ):
        # Role exists and can already connect (default PUBLIC CONNECT)
        mock_asyncpg_connection.fetchval.side_effect = [1, True]

        db_manager = DatabaseManager(mock_asyncpg_connection)
        await db_manager.grant_pgbouncer_connect("test_db")

        mock_asyncpg_connection.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_grant_pgbouncer_connect_revoked(self, mock_asyncpg_connection):
        # Role exists but CONNECT was revoked from PUBLIC
        mock_asyncpg_connection.fetchval.side_effect = [1, False]

        db_manager = DatabaseManager(mock_asyncpg_connection)
        await db_manager.grant_pgbouncer_connect("test_db")

        mock_asyncpg_connection.execute.assert_called_once_with(
            'GRANT CONNECT ON DATABASE "test_db" TO "_crunchypgbouncer"'
        )

    @pytest.mark.asyncio
    async def test_grant_public_schema_already_granted(self, mock_asyncpg_connection):
        # PostgreSQL 15+: the owner already has CREATE through pg_database_owner
        mock_asyncpg_connection.fetchval.return_value = True

        db_manager = DatabaseManager(mock_asyncpg_connection)
        await db_manager.grant_public_schema("test_user")

        mock_asyncpg_connection.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_grant_public_schema_missing(self, mock_asyncpg_connection):
        # Database created before PostgreSQL 15
        mock_asyncpg_connection.fetchval.return_value = False

        db_manager = DatabaseManager(mock_asyncpg_connection)
        await db_manager.grant_public_schema("test_user")

        mock_asyncpg_connection.execute.assert_called_once_with(
            'GRANT ALL ON SCHEMA public TO "test_user"'
        )
