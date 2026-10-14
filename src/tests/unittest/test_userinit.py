import base64
import sys
from pathlib import Path
from unittest.mock import AsyncMock, call, patch

import kopf
import pytest

# Add src directory to path so we can import userinit
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the main userinit handler
from userinit.userinit import (
    CredentialFreeDiffBaseStorage,
    configure,
    on_cluster_event,
    on_deprecated_labels,
    on_pguser_secret_created,
)

OPT_IN_ALL = {
    "crunchy-userinit.drummyfloyd.github.com/pgbouncer-connect": "other, testuser",
    "crunchy-userinit.drummyfloyd.github.com/public-schema": "*",
}


def cluster(annotations: dict) -> dict:
    """PostgresCluster as returned by ConnectionManager.get_cluster"""
    return {
        "apiVersion": "postgres-operator.crunchydata.com/v1beta1",
        "kind": "PostgresCluster",
        "metadata": {
            "name": "test-cluster",
            "namespace": "test-ns",
            "annotations": annotations,
        },
    }


@pytest.fixture(autouse=True)
def events():
    """kopf.info/warn need a running operator: capture them instead"""
    with (
        patch("userinit.userinit.kopf.info") as info,
        patch("userinit.userinit.kopf.warn") as warn,
    ):
        yield info, warn


@pytest.mark.unit
class TestPgUserSecretHandler:
    """Test the main Kopf event handler."""

    @pytest.mark.asyncio
    @patch("userinit.userinit.ConnectionManager.get_cluster")
    @patch("userinit.userinit.ConnectionManager.open_cluster_connection")
    @patch("userinit.userinit.DatabaseManager")
    async def test_on_pguser_secret_created_success(
        self,
        mock_db_manager_class,
        mock_open_conn,
        mock_annotations,
        valid_secret_body,
        events,
    ):
        # No opt-in annotation: only the owner is changed
        mock_annotations.return_value = cluster({})
        mock_conn = AsyncMock()
        mock_open_conn.return_value = mock_conn

        mock_db_manager = AsyncMock()
        mock_db_manager_class.return_value = mock_db_manager

        await on_pguser_secret_created(body=valid_secret_body, patch=valid_secret_body)

        mock_annotations.assert_called_once_with("test-ns", "test-cluster")
        mock_open_conn.assert_called_once_with("test-ns", "test-cluster", "postgres")
        mock_db_manager.change_owner.assert_called_once_with("testdb", "testuser")
        mock_db_manager.grant_pgbouncer_connect.assert_not_called()
        mock_db_manager.grant_public_schema.assert_not_called()
        mock_conn.close.assert_called_once()
        events[0].assert_not_called()

    @pytest.mark.asyncio
    @patch("userinit.userinit.ConnectionManager.get_cluster")
    @patch("userinit.userinit.ConnectionManager.open_cluster_connection")
    @patch("userinit.userinit.DatabaseManager")
    async def test_on_pguser_secret_created_opt_in(
        self,
        mock_db_manager_class,
        mock_open_conn,
        mock_annotations,
        valid_secret_body,
        events,
    ):
        # The user is in the pgbouncer-connect list and public-schema is "*"
        mock_annotations.return_value = cluster(OPT_IN_ALL)
        mock_conn = AsyncMock()
        mock_open_conn.return_value = mock_conn

        mock_db_manager = AsyncMock()
        mock_db_manager_class.return_value = mock_db_manager

        await on_pguser_secret_created(body=valid_secret_body, patch=valid_secret_body)

        assert mock_open_conn.call_args_list == [
            call("test-ns", "test-cluster", "postgres"),
            call("test-ns", "test-cluster", "postgres", database="testdb"),
        ]
        mock_db_manager.grant_pgbouncer_connect.assert_called_once_with("testdb")
        mock_db_manager.grant_public_schema.assert_called_once_with("testuser")
        assert mock_conn.close.call_count == 2
        # Both grants ran: one event each, on the PostgresCluster
        info = events[0]
        assert [c.kwargs["reason"] for c in info.call_args_list] == ["GrantApplied"] * 2
        assert info.call_args_list[0].args[0]["kind"] == "PostgresCluster"
        assert "_crunchypgbouncer" in info.call_args_list[0].kwargs["message"]
        assert "schema public" in info.call_args_list[1].kwargs["message"]

    @pytest.mark.asyncio
    @patch(
        "userinit.userinit.ConnectionManager.get_cluster",
        AsyncMock(return_value=cluster(OPT_IN_ALL)),
    )
    @patch("userinit.userinit.ConnectionManager.open_cluster_connection")
    @patch("userinit.userinit.DatabaseManager")
    async def test_on_pguser_secret_created_already_granted(
        self, mock_db_manager_class, mock_open_conn, valid_secret_body, events
    ):
        # Selected, but both grants are already in place: no event
        mock_open_conn.return_value = AsyncMock()
        mock_db_manager = AsyncMock()
        mock_db_manager.grant_pgbouncer_connect.return_value = False
        mock_db_manager.grant_public_schema.return_value = False
        mock_db_manager_class.return_value = mock_db_manager

        await on_pguser_secret_created(body=valid_secret_body, patch=valid_secret_body)

        events[0].assert_not_called()

    @pytest.mark.asyncio
    @patch("userinit.userinit.ConnectionManager.get_cluster")
    @patch("userinit.userinit.ConnectionManager.open_cluster_connection")
    @patch("userinit.userinit.DatabaseManager")
    async def test_on_pguser_secret_created_not_selected(
        self, mock_db_manager_class, mock_open_conn, mock_annotations, valid_secret_body
    ):
        # Annotations list other users only
        mock_annotations.return_value = cluster(
            {
                "crunchy-userinit.drummyfloyd.github.com/pgbouncer-connect": "other",
                "crunchy-userinit.drummyfloyd.github.com/public-schema": "other,another",
            }
        )
        mock_open_conn.return_value = AsyncMock()
        mock_db_manager = AsyncMock()
        mock_db_manager_class.return_value = mock_db_manager

        await on_pguser_secret_created(body=valid_secret_body, patch=valid_secret_body)

        mock_open_conn.assert_called_once()
        mock_db_manager.grant_pgbouncer_connect.assert_not_called()
        mock_db_manager.grant_public_schema.assert_not_called()

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
    @patch(
        "userinit.userinit.ConnectionManager.get_cluster",
        AsyncMock(return_value=cluster({})),
    )
    @patch("userinit.userinit.ConnectionManager.open_cluster_connection")
    @patch("userinit.userinit.DatabaseManager")
    async def test_on_pguser_secret_created_change_owner_error(
        self, mock_db_manager_class, mock_open_conn, valid_secret_body, events
    ):
        # Test when change_owner raises an exception
        mock_conn = AsyncMock()
        mock_open_conn.return_value = mock_conn

        mock_db_manager = AsyncMock()
        mock_db_manager.change_owner.side_effect = Exception("Database error")
        mock_db_manager_class.return_value = mock_db_manager

        with pytest.raises(kopf.TemporaryError, match="Failed to set up the database"):
            await on_pguser_secret_created(
                body=valid_secret_body, patch=valid_secret_body
            )

        # Ensure connection is still closed even on error
        mock_conn.close.assert_called_once()
        assert events[1].call_args.kwargs["reason"] == "UserInitFailed"

    @pytest.mark.asyncio
    @patch(
        "userinit.userinit.ConnectionManager.get_cluster",
        AsyncMock(return_value=cluster(OPT_IN_ALL)),
    )
    @patch("userinit.userinit.ConnectionManager.open_cluster_connection")
    @patch("userinit.userinit.DatabaseManager")
    async def test_on_pguser_secret_created_public_schema_error(
        self, mock_db_manager_class, mock_open_conn, valid_secret_body, events
    ):
        # Test when grant_public_schema raises an exception
        mock_conn = AsyncMock()
        mock_open_conn.return_value = mock_conn

        mock_db_manager = AsyncMock()
        mock_db_manager.grant_public_schema.side_effect = Exception("Database error")
        mock_db_manager_class.return_value = mock_db_manager

        with pytest.raises(
            kopf.TemporaryError, match="Failed to grant the public schema"
        ):
            await on_pguser_secret_created(
                body=valid_secret_body, patch=valid_secret_body
            )

        # Both connections are closed even on error
        assert mock_conn.close.call_count == 2
        assert "public schema" in events[1].call_args.kwargs["message"]

    @pytest.mark.asyncio
    @patch(
        "userinit.userinit.ConnectionManager.get_cluster",
        AsyncMock(return_value=cluster({})),
    )
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
class TestClusterEventHandler:
    """Test the PostgresCluster opt-in annotations handler."""

    @staticmethod
    def cluster_body(annotations):
        return kopf.Body(
            {
                "metadata": {
                    "name": "test-cluster",
                    "namespace": "test-ns",
                    "annotations": annotations,
                }
            }
        )

    @pytest.mark.asyncio
    @patch("userinit.userinit.init_pguser")
    @patch("userinit.userinit.ConnectionManager.list_pguser_secrets")
    async def test_annotations_changed(self, mock_list, mock_init, valid_secret_body):
        # New values: every pguser secret of the cluster is processed again
        mock_list.return_value = [valid_secret_body._dict]
        memo = kopf.Memo(opt_in=(None, None))

        await on_cluster_event(body=self.cluster_body(OPT_IN_ALL), memo=memo)

        mock_list.assert_called_once_with("test-ns", "test-cluster")
        mock_init.assert_called_once()
        assert mock_init.call_args.args[0].role_name == "testuser"
        # The cluster body itself is passed: annotations and events target
        assert mock_init.call_args.args[1].metadata.annotations == OPT_IN_ALL
        assert memo["opt_in"] == ("other, testuser", "*")

    @pytest.mark.asyncio
    @patch("userinit.userinit.ConnectionManager.list_pguser_secrets")
    async def test_first_observation(self, mock_list):
        # Controller start: values are only remembered, resume already applies them
        memo = kopf.Memo()

        await on_cluster_event(body=self.cluster_body(OPT_IN_ALL), memo=memo)

        mock_list.assert_not_called()
        assert memo["opt_in"] == ("other, testuser", "*")

    @pytest.mark.asyncio
    @patch("userinit.userinit.ConnectionManager.list_pguser_secrets")
    async def test_annotations_unchanged(self, mock_list):
        # Same values as last time (e.g. a status update): nothing to do
        memo = kopf.Memo(opt_in=("other, testuser", "*"))

        await on_cluster_event(body=self.cluster_body(OPT_IN_ALL), memo=memo)

        mock_list.assert_not_called()

    @pytest.mark.asyncio
    @patch("userinit.userinit.init_pguser")
    @patch("userinit.userinit.ConnectionManager.list_pguser_secrets")
    async def test_annotations_failure_retried(
        self, mock_list, mock_init, valid_secret_body
    ):
        # A failure keeps the memo unchanged, so the next event retries
        mock_list.return_value = [valid_secret_body._dict]
        mock_init.side_effect = kopf.TemporaryError("db down", delay=60)
        memo = kopf.Memo(opt_in=(None, None))

        await on_cluster_event(body=self.cluster_body(OPT_IN_ALL), memo=memo)

        mock_init.assert_called_once()
        assert memo["opt_in"] == (None, None)


@pytest.mark.unit
class TestDeprecatedLabels:
    """Test handling of deprecated labels."""

    async def test_deprecated_labels_error(self, mock_k8s_secret):
        deprecated_secret_body = mock_k8s_secret(
            actual_annotations=False, actual_labels=False, deprecated_labels=True
        )

        with pytest.raises(kopf.PermanentError):
            await on_deprecated_labels(body=deprecated_secret_body)


@pytest.mark.unit
class TestCredentialFreeDiffBaseStorage:
    """Test the diff-base stored as an annotation on pguser secrets."""

    def test_build_drops_credentials(self, mock_k8s_secret):
        storage = CredentialFreeDiffBaseStorage(
            prefix="crunchy-userinit.drummyfloyd.github.com",
            key="last-handled-configuration",
            v1=False,
        )
        secret = mock_k8s_secret()

        essence = storage.build(body=kopf.Body(secret._dict))

        # Only what the handler reads is tracked: no password, verifier or URI
        assert set(essence["data"]) == {"dbname", "user"}
        assert essence["metadata"]["labels"] == secret._dict["metadata"]["labels"]


@pytest.mark.unit
class TestConfigure:
    """Test the operator settings."""

    @pytest.mark.asyncio
    @patch("userinit.userinit.DEV_MODE", True)
    @patch("userinit.userinit.config.load_kube_config", AsyncMock())
    async def test_events_posted_as_the_controller(self, env_vars):
        env_vars(HOSTNAME="crunchy-userinit-abc12")
        settings = kopf.OperatorSettings()

        await configure(settings=settings)

        assert settings.posting.reporting_component == "crunchy-userinit"
        assert settings.posting.reporting_instance == "crunchy-userinit-abc12"
        assert settings.posting.event_name_prefix == "crunchy-userinit-"
