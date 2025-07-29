import base64
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import kopf
import pytest

# Add src directory to path so we can import userinit
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the main userinit handler
from userinit.userinit import on_deprecated_labels, on_pguser_secret_created


@pytest.mark.unit
class TestPgUserSecretHandler:
    """Test the main Kopf event handler."""

    @pytest.mark.asyncio
    @patch("userinit.userinit.ConnectionManager.open_cluster_connection")
    @patch("userinit.userinit.DatabaseManager")
    async def test_on_pguser_secret_created_success(
        self, mock_db_manager_class, mock_open_conn, valid_secret_body
    ):
        # Test successful execution of the handler
        mock_conn = AsyncMock()
        mock_open_conn.return_value = mock_conn

        mock_db_manager = AsyncMock()
        mock_db_manager_class.return_value = mock_db_manager

        await on_pguser_secret_created(body=valid_secret_body, patch=valid_secret_body)

        mock_open_conn.assert_called_once_with("test-ns", "test-cluster", "postgres")
        mock_db_manager_class.assert_called_once_with(mock_conn)
        mock_db_manager.change_owner.assert_called_once_with("testdb", "testuser")
        mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_pguser_secret_created_missing_superuser_label(
        self, valid_secret_body
    ):
        # Test when superuser label is missing
        del valid_secret_body.metadata.labels[
            "crunchy-userinit.drummyfloyd.github.com/superuser"
        ]

        with pytest.raises(kopf.TemporaryError, match="superuser label not found"):
            await on_pguser_secret_created(
                body=valid_secret_body, patch=valid_secret_body
            )

    @pytest.mark.asyncio
    async def test_on_pguser_secret_created_missing_dbname(self, valid_secret_body):
        # Test when dbname is missing from secret data
        del valid_secret_body.data["dbname"]

        with pytest.raises(kopf.TemporaryError, match="Could not parse dbname"):
            await on_pguser_secret_created(
                body=valid_secret_body, patch=valid_secret_body
            )

    @pytest.mark.asyncio
    async def test_on_pguser_secret_created_missing_user(self, valid_secret_body):
        # Test when user is missing from secret data
        del valid_secret_body.data["user"]

        with pytest.raises(kopf.TemporaryError, match="Could not parse role_name"):
            await on_pguser_secret_created(
                body=valid_secret_body, patch=valid_secret_body
            )

    @pytest.mark.asyncio
    async def test_on_pguser_secret_created_superuser_skip(self, valid_secret_body):
        # Test when the user is the superuser (should be skipped)
        valid_secret_body.data["user"] = base64.b64encode(b"postgres").decode()

        # Should return without error and without calling change_owner
        with patch("userinit.userinit.DatabaseManager") as mock_db_manager_class:
            await on_pguser_secret_created(
                body=valid_secret_body, patch=valid_secret_body
            )
            mock_db_manager_class.assert_not_called()

    @pytest.mark.asyncio
    @patch("userinit.userinit.ConnectionManager.open_cluster_connection")
    @patch("userinit.userinit.DatabaseManager")
    async def test_on_pguser_secret_created_change_owner_error(
        self, mock_db_manager_class, mock_open_conn, valid_secret_body
    ):
        # Test when change_owner raises an exception
        mock_conn = AsyncMock()
        mock_open_conn.return_value = mock_conn

        mock_db_manager = AsyncMock()
        mock_db_manager.change_owner.side_effect = Exception("Database error")
        mock_db_manager_class.return_value = mock_db_manager

        with pytest.raises(kopf.TemporaryError, match="Failed to change the owner"):
            await on_pguser_secret_created(
                body=valid_secret_body, patch=valid_secret_body
            )

        # Ensure connection is still closed even on error
        mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("userinit.userinit.ConnectionManager.open_cluster_connection")
    async def test_on_pguser_secret_created_connection_error(
        self, mock_open_conn, valid_secret_body
    ):
        # Test when connection fails
        mock_open_conn.side_effect = kopf.TemporaryError("Connection failed", delay=10)

        with pytest.raises(kopf.TemporaryError, match="Connection failed"):
            await on_pguser_secret_created(
                body=valid_secret_body, patch=valid_secret_body
            )


@pytest.mark.unit
class TestDeprecatedLabels:
    """Test handling of deprecated labels."""

    async def test_deprecated_labels_error(self, mock_k8s_secret):
        deprecated_secret_body = mock_k8s_secret(
            actual_annotations=False, actual_labels=False, deprecated_labels=True
        )

        with pytest.raises(kopf.PermanentError):
            await on_deprecated_labels(body=deprecated_secret_body)
