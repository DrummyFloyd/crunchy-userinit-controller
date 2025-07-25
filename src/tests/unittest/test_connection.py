import base64
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import kopf
import pytest

# Add src directory to path so we can import userinit
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the connections module
from userinit.connections import ConnectionManager


class TestConnectionManager:
    """Test the ConnectionManager class."""

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
    @patch('userinit.connections.DEV_MODE', False)
    @patch('userinit.connections.client.CoreV1Api')
    @patch('userinit.connections.ApiClient')
    async def test_get_superuser_uri_production_mode(self, mock_api_client, mock_core_v1, mock_secret_data):
        # Test production mode (uses URI from secret)
        mock_secret = MagicMock()
        mock_secret.data = mock_secret_data

        mock_v1_instance = AsyncMock()
        mock_v1_instance.read_namespaced_secret.return_value = mock_secret
        mock_core_v1.return_value = mock_v1_instance

        mock_api_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await ConnectionManager.get_superuser_uri("test-ns", "test-cluster", "postgres")

        assert result == "postgresql://user:pass@host:5432/db"
        mock_v1_instance.read_namespaced_secret.assert_called_once_with(
            "test-cluster-pguser-postgres", "test-ns"
        )

    @pytest.mark.asyncio
    @patch('userinit.connections.DEV_MODE', True)
    @patch('userinit.connections.client.CoreV1Api')
    @patch('userinit.connections.ApiClient')
    async def test_get_superuser_uri_dev_mode(self, mock_api_client, mock_core_v1, mock_secret_data):
        # Test dev mode (constructs localhost URI)
        mock_secret = MagicMock()
        mock_secret.data = mock_secret_data

        mock_v1_instance = AsyncMock()
        mock_v1_instance.read_namespaced_secret.return_value = mock_secret
        mock_core_v1.return_value = mock_v1_instance

        mock_api_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await ConnectionManager.get_superuser_uri("test-ns", "test-cluster", "postgres")

        assert result == "postgresql://superuser:password123@localhost:5432/postgres"

    @pytest.mark.asyncio
    @patch('userinit.connections.DEV_MODE', False)
    @patch('userinit.connections.client.CoreV1Api')
    @patch('userinit.connections.ApiClient')
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
            await ConnectionManager.get_superuser_uri("test-ns", "test-cluster", "postgres")

    @pytest.mark.asyncio
    @patch('userinit.connections.ConnectionManager.get_superuser_uri')
    @patch('userinit.connections.asyncpg.connect')
    async def test_open_cluster_connection_success(self, mock_connect, mock_get_uri):
        # Test successful connection
        mock_get_uri.return_value = "postgresql://user:pass@host:5432/db"
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn

        result = await ConnectionManager.open_cluster_connection("test-ns", "test-cluster", "postgres")

        assert result == mock_conn
        mock_get_uri.assert_called_once_with("test-ns", "test-cluster", "postgres")
        mock_connect.assert_called_once_with("postgresql://user:pass@host:5432/db")

    @pytest.mark.asyncio
    @patch('userinit.connections.ConnectionManager.get_superuser_uri')
    @patch('userinit.connections.asyncpg.connect')
    async def test_open_cluster_connection_failure(self, mock_connect, mock_get_uri):
        # Test connection failure
        mock_get_uri.return_value = "postgresql://user:pass@host:5432/db"
        mock_connect.side_effect = Exception("Connection failed")

        with pytest.raises(kopf.TemporaryError, match="Cannot connect to the database"):
            await ConnectionManager.open_cluster_connection("test-ns", "test-cluster", "postgres")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
