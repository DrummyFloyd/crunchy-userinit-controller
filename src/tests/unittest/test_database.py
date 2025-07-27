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
