"""
Test configuration and shared fixtures for crunchy-userinit operator tests.
"""

import asyncio
import base64
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class MockSecret:
    """
    A mock secret class that provides both dot notation and dict-like access.
    This matches the interface expected by the Kopf handlers.
    """

    def __init__(self, data_dict):
        # Store the original dict for get() method
        self._dict = data_dict
        # Convert nested structures to support dot notation
        for key, value in data_dict.items():
            if isinstance(value, dict):
                setattr(self, key, MockSecret(value))
            else:
                setattr(self, key, value)

    def get(self, key, default=None):
        """Provide dict-like get() method."""
        return self._dict.get(key, default)

    def __getitem__(self, key):
        """Provide dict-like [] access."""
        return self._dict[key]

    def __setitem__(self, key, value):
        """Allow setting values."""
        self._dict[key] = value
        setattr(self, key, value)

    def __delitem__(self, key):
        """Allow deleting keys."""
        del self._dict[key]
        if hasattr(self, key):
            delattr(self, key)

    def __contains__(self, key):
        """Support 'in' operator."""
        return key in self._dict


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_k8s_secret():
    """Create a mock Kubernetes secret with typical postgres-operator structure."""

    def _create_secret(
        cluster_name: str = "test-cluster",
        namespace: str = "test-namespace",
        username: str = "testuser",
        dbname: str = "testdb",
        superuser: str = "postgres",
        enabled: bool = True,
    ) -> MockSecret:
        labels = {
            "postgres-operator.crunchydata.com/cluster": cluster_name,
            "postgres-operator.crunchydata.com/role": "pguser",
        }

        if enabled:
            labels["crunchy-userinit.ramblurr.github.com/enabled"] = "true"

        if superuser:
            labels["crunchy-userinit.ramblurr.github.com/superuser"] = superuser

        secret_data = {
            "metadata": {
                "name": f"{cluster_name}-pguser-{username}",
                "namespace": namespace,
                "labels": labels,
            },
            "data": {
                "dbname": base64.b64encode(dbname.encode()).decode(),
                "user": base64.b64encode(username.encode()).decode(),
                "password": base64.b64encode("testpass123".encode()).decode(),
                "host": base64.b64encode("test-postgres-host".encode()).decode(),
                "port": base64.b64encode("5432".encode()).decode(),
                "uri": base64.b64encode(
                    f"postgresql://{username}:testpass123@test-postgres-host:5432/{dbname}".encode()
                ).decode(),
            },
        }
        return MockSecret(secret_data)

    return _create_secret


@pytest.fixture
def mock_superuser_secret():
    """Create a mock superuser secret."""

    def _create_superuser_secret(
        cluster_name: str = "test-cluster",
        namespace: str = "test-namespace",
        superuser: str = "postgres",
    ) -> MagicMock:
        secret = MagicMock()
        secret.data = {
            "user": base64.b64encode(superuser.encode()).decode(),
            "password": base64.b64encode("superpass123".encode()).decode(),
            "dbname": base64.b64encode("postgres".encode()).decode(),
            "host": base64.b64encode("test-postgres-host".encode()).decode(),
            "port": base64.b64encode("5432".encode()).decode(),
            "uri": base64.b64encode(
                f"postgresql://{superuser}:superpass123@test-postgres-host:5432/postgres".encode()
            ).decode(),
        }
        return secret

    return _create_superuser_secret


@pytest.fixture
def valid_secret_body():
    """Create a valid secret body for testing - this is the main fixture most tests will use."""
    return MockSecret(
        {
            "metadata": {
                "name": "test-cluster-pguser-testuser",
                "namespace": "test-ns",
                "labels": {
                    "postgres-operator.crunchydata.com/cluster": "test-cluster",
                    "postgres-operator.crunchydata.com/role": "pguser",
                    "crunchy-userinit.ramblurr.github.com/enabled": "true",
                    "crunchy-userinit.ramblurr.github.com/superuser": "postgres",
                },
            },
            "data": {
                "dbname": base64.b64encode(b"testdb").decode(),
                "user": base64.b64encode(b"testuser").decode(),
            },
        }
    )


@pytest.fixture
def mock_asyncpg_connection():
    """Create a mock asyncpg connection."""
    conn = AsyncMock()
    # Default behavior: database owner is different, so change is needed
    conn.fetchval.return_value = "old_owner"
    conn.execute.return_value = None
    return conn


@pytest.fixture
def mock_kubernetes_client():
    """Create a mock Kubernetes client."""
    with (
        patch("userinit.connections.client.CoreV1Api") as mock_core_v1,
        patch("userinit.connections.ApiClient") as mock_api_client,
    ):
        mock_v1_instance = AsyncMock()
        mock_core_v1.return_value = mock_v1_instance

        # Setup async context manager
        mock_api_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_api_client.return_value.__aexit__ = AsyncMock(return_value=None)

        yield mock_v1_instance


@pytest.fixture(autouse=True)
def setup_logging():
    """Setup logging for tests."""
    import logging

    logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def env_vars():
    """Fixture for managing environment variables in tests."""
    import os

    original_env = os.environ.copy()

    def set_env(**kwargs):
        for key, value in kwargs.items():
            os.environ[key] = str(value)

    def reset_env():
        os.environ.clear()
        os.environ.update(original_env)

    yield set_env
    reset_env()


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "slow: mark test as slow running")


# Custom assertion helpers
class AssertionHelpers:
    """Custom assertion helpers for tests."""

    @staticmethod
    def assert_temporary_error(
        exc_info, expected_message: str = None, expected_delay: int = None
    ):
        """Assert that a TemporaryError was raised with expected properties."""
        import kopf

        assert exc_info.type == kopf.TemporaryError
        if expected_message:
            assert expected_message in str(exc_info.value)
        if expected_delay:
            assert exc_info.value.delay == expected_delay


@pytest.fixture
def assert_helpers():
    """Provide assertion helpers."""
    return AssertionHelpers


# Mock data generators
@pytest.fixture
def data_generators():
    """Provide data generators for tests."""

    class DataGenerators:
        @staticmethod
        def base64_encode(value: str) -> str:
            return base64.b64encode(value.encode()).decode()

        @staticmethod
        def create_pg_connection_uri(
            user: str = "testuser",
            password: str = "testpass",
            host: str = "localhost",
            port: int = 5432,
            dbname: str = "testdb",
        ) -> str:
            return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

    return DataGenerators
