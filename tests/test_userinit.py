import asyncio
import base64
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import kopf
import pytest
from kopf.testing import KopfRunner
from kubernetes_asyncio.client.exceptions import ApiException

# Add src directory to path so we can import userinit
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import the functions from userinit module
from userinit import (
    decode_value,
    change_owner,
    get_superuser_uri,
    open_cluster_connection,
    on_pguser_secret_created
)

# Import MockSecret from conftest for type hints and direct usage if needed
from conftest import MockSecret


class TestDecodeValue:
    """Test the decode_value utility function."""

    def test_decode_value_valid_base64(self):
        # Test with valid base64 encoded string
        encoded = base64.b64encode(b"test_value").decode("utf-8")
        result = decode_value(encoded)
        assert result == "test_value"

    def test_decode_value_none(self):
        # Test with None input
        result = decode_value(None)
        assert result is None

    def test_decode_value_empty_string(self):
        # Test with empty string
        result = decode_value("")
        assert result is None

    def test_decode_value_unicode(self):
        # Test with unicode characters
        unicode_text = "héllo wörld"
        encoded = base64.b64encode(unicode_text.encode("utf-8")).decode("utf-8")
        result = decode_value(encoded)
        assert result == unicode_text


class TestChangeOwner:
    """Test the change_owner database function."""

    @pytest.mark.asyncio
    async def test_change_owner_same_owner(self, mock_asyncpg_connection):
        # Test when current owner is the same as the new owner
        mock_asyncpg_connection.fetchval.return_value = "test_user"

        await change_owner(mock_asyncpg_connection, "test_db", "test_user")

        mock_asyncpg_connection.fetchval.assert_called_once()
        mock_asyncpg_connection.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_change_owner_different_owner(self, mock_asyncpg_connection):
        # Test when current owner is different from new owner
        mock_asyncpg_connection.fetchval.return_value = "old_user"

        await change_owner(mock_asyncpg_connection, "test_db", "new_user")

        mock_asyncpg_connection.fetchval.assert_called_once()
        mock_asyncpg_connection.execute.assert_called_once_with(
            'ALTER DATABASE "test_db" OWNER TO "new_user"'
        )

    @pytest.mark.asyncio
    async def test_change_owner_database_error(self, mock_asyncpg_connection):
        # Test when database operation fails
        mock_asyncpg_connection.fetchval.return_value = "old_user"
        mock_asyncpg_connection.execute.side_effect = Exception("DB Error")

        with pytest.raises(Exception, match="DB Error"):
            await change_owner(mock_asyncpg_connection, "test_db", "new_user")


class TestGetSuperuserUri:
    """Test the get_superuser_uri function."""

    @pytest.fixture
    def mock_secret_data(self):
        """Create mock secret data."""
        return {
            "uri": base64.b64encode(b"postgresql://user:pass@host:5432/db").decode(),
            "user": base64.b64encode(b"superuser").decode(),
            "password": base64.b64encode(b"password123").decode(),
            "dbname": base64.b64encode(b"postgres").decode(),
            "port": base64.b64encode(b"5432").decode(),
        }

    @pytest.mark.asyncio
    @patch('userinit.DEV_MODE', False)
    @patch('userinit.client.CoreV1Api')
    @patch('userinit.ApiClient')
    async def test_get_superuser_uri_production_mode(self, mock_api_client, mock_core_v1, mock_secret_data):
        # Test production mode (uses URI from secret)
        mock_secret = MagicMock()
        mock_secret.data = mock_secret_data

        mock_v1_instance = AsyncMock()
        mock_v1_instance.read_namespaced_secret.return_value = mock_secret
        mock_core_v1.return_value = mock_v1_instance

        mock_api_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await get_superuser_uri("test-ns", "test-cluster", "postgres")

        assert result == "postgresql://user:pass@host:5432/db"
        mock_v1_instance.read_namespaced_secret.assert_called_once_with(
            "test-cluster-pguser-postgres", "test-ns"
        )

    @pytest.mark.asyncio
    @patch('userinit.DEV_MODE', True)
    @patch('userinit.client.CoreV1Api')
    @patch('userinit.ApiClient')
    async def test_get_superuser_uri_dev_mode(self, mock_api_client, mock_core_v1, mock_secret_data):
        # Test dev mode (constructs localhost URI)
        mock_secret = MagicMock()
        mock_secret.data = mock_secret_data

        mock_v1_instance = AsyncMock()
        mock_v1_instance.read_namespaced_secret.return_value = mock_secret
        mock_core_v1.return_value = mock_v1_instance

        mock_api_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await get_superuser_uri("test-ns", "test-cluster", "postgres")

        assert result == "postgresql://superuser:password123@localhost:5432/postgres"

    @pytest.mark.asyncio
    @patch('userinit.DEV_MODE', False)
    @patch('userinit.client.CoreV1Api')
    @patch('userinit.ApiClient')
    async def test_get_superuser_uri_missing_uri(self, mock_api_client, mock_core_v1):
        # Test when URI is missing from secret
        mock_secret = MagicMock()
        mock_secret.data = {"user": base64.b64encode(b"test").decode()}

        mock_v1_instance = AsyncMock()
        mock_v1_instance.read_namespaced_secret.return_value = mock_secret
        mock_core_v1.return_value = mock_v1_instance

        mock_api_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(kopf.TemporaryError, match="Could not parse connection uri"):
            await get_superuser_uri("test-ns", "test-cluster", "postgres")


class TestOpenClusterConnection:
    """Test the open_cluster_connection function."""

    @pytest.mark.asyncio
    @patch('userinit.get_superuser_uri')
    @patch('userinit.asyncpg.connect')
    async def test_open_cluster_connection_success(self, mock_connect, mock_get_uri):
        # Test successful connection
        mock_get_uri.return_value = "postgresql://user:pass@host:5432/db"
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn

        result = await open_cluster_connection("test-ns", "test-cluster", "postgres")

        assert result == mock_conn
        mock_get_uri.assert_called_once_with("test-ns", "test-cluster", "postgres")
        mock_connect.assert_called_once_with("postgresql://user:pass@host:5432/db")

    @pytest.mark.asyncio
    @patch('userinit.get_superuser_uri')
    @patch('userinit.asyncpg.connect')
    async def test_open_cluster_connection_failure(self, mock_connect, mock_get_uri):
        # Test connection failure
        mock_get_uri.return_value = "postgresql://user:pass@host:5432/db"
        mock_connect.side_effect = Exception("Connection failed")

        with pytest.raises(kopf.TemporaryError, match="Cannot connect to the database"):
            await open_cluster_connection("test-ns", "test-cluster", "postgres")


class TestPgUserSecretHandler:
    """Test the main Kopf event handler."""

    @pytest.mark.asyncio
    @patch('userinit.open_cluster_connection')
    @patch('userinit.change_owner')
    async def test_on_pguser_secret_created_success(self, mock_change_owner, mock_open_conn, valid_secret_body):
        # Test successful execution of the handler
        mock_conn = AsyncMock()
        mock_open_conn.return_value = mock_conn

        await on_pguser_secret_created(body=valid_secret_body)

        mock_open_conn.assert_called_once_with("test-ns", "test-cluster", "postgres")
        mock_change_owner.assert_called_once_with(mock_conn, "testdb", "testuser")

    @pytest.mark.asyncio
    async def test_on_pguser_secret_created_missing_superuser_label(self, valid_secret_body):
        # Test when superuser label is missing
        del valid_secret_body.metadata.labels["crunchy-userinit.ramblurr.github.com/superuser"]

        with pytest.raises(kopf.TemporaryError, match="superuser label not found"):
            await on_pguser_secret_created(body=valid_secret_body)

    @pytest.mark.asyncio
    async def test_on_pguser_secret_created_missing_dbname(self, valid_secret_body):
        # Test when dbname is missing from secret data
        del valid_secret_body.data["dbname"]

        with pytest.raises(kopf.TemporaryError, match="Could not parse dbname"):
            await on_pguser_secret_created(body=valid_secret_body)

    @pytest.mark.asyncio
    async def test_on_pguser_secret_created_missing_user(self, valid_secret_body):
        # Test when user is missing from secret data
        del valid_secret_body.data["user"]

        with pytest.raises(kopf.TemporaryError, match="Could not parse role_name"):
            await on_pguser_secret_created(body=valid_secret_body)

    @pytest.mark.asyncio
    async def test_on_pguser_secret_created_superuser_skip(self, valid_secret_body):
        # Test when the user is the superuser (should be skipped)
        valid_secret_body.data["user"] = base64.b64encode(b"postgres").decode()

        # Should return without error and without calling change_owner
        with patch('userinit.change_owner') as mock_change_owner:
            await on_pguser_secret_created(body=valid_secret_body)
            mock_change_owner.assert_not_called()

    @pytest.mark.asyncio
    @patch('userinit.open_cluster_connection')
    @patch('userinit.change_owner')
    async def test_on_pguser_secret_created_change_owner_error(self, mock_change_owner, mock_open_conn, valid_secret_body):
        # Test when change_owner raises an exception
        mock_conn = AsyncMock()
        mock_open_conn.return_value = mock_conn
        mock_change_owner.side_effect = Exception("Database error")

        with pytest.raises(kopf.TemporaryError, match="Failed to change the owner"):
            await on_pguser_secret_created(body=valid_secret_body)

    @pytest.mark.asyncio
    async def test_custom_secret_creation(self, mock_k8s_secret):
        # Example of using the mock_k8s_secret factory
        custom_secret = mock_k8s_secret(
            cluster_name="custom-cluster",
            username="customuser",
            dbname="customdb"
        )

        # Now you can test with this custom secret
        assert custom_secret.metadata.name == "custom-cluster-pguser-customuser"
        assert decode_value(custom_secret.data.user) == "customuser"
        assert decode_value(custom_secret.data.dbname) == "customdb"


class TestEnvironmentConfiguration:
    """Test environment-specific configurations."""

    @patch.dict('os.environ', {'DEV_MODE': 'true'})
    def test_dev_mode_enabled(self):
        # Test DEV_MODE environment variable parsing
        import importlib
        import userinit
        importlib.reload(userinit)
        assert userinit.DEV_MODE is True

    @patch.dict('os.environ', {'DEV_MODE': 'false'})
    def test_dev_mode_disabled(self):
        # Test DEV_MODE disabled
        import importlib
        import userinit
        importlib.reload(userinit)
        assert userinit.DEV_MODE is False

    @patch.dict('os.environ', {'CRUI_WATCH_NAMESPACE': 'custom-namespace'})
    def test_custom_watch_namespace(self):
        # Test custom watch namespace configuration
        import importlib
        import userinit
        importlib.reload(userinit)
        assert userinit.CRUI_WATCH_NAMESPACE == 'custom-namespace'


# Test configuration
pytest_plugins = ['pytest_asyncio']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
