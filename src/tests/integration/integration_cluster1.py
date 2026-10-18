# INFO: https://github.com/nolar/kopf/blob/main/examples/09-testing/test_example_09.py
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import kopf
import pytest
from kubernetes import client

YAML_FILE = "cluster1"

os.environ["DEV_MODE"] = "true"  # Set DEV_MODE environment variable for testing]
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

SECRET_NAME_USER1 = f"{YAML_FILE}-pguser-user1"
OPT_IN_PREFIX = "crunchy-userinit.drummyfloyd.github.com"


def psql(sql: str, dbname: str = "postgres") -> str:
    """Run SQL as postgres on the primary of the test cluster"""
    pod = subprocess.run(
        f"kubectl -n {YAML_FILE} get pods -l postgres-operator.crunchydata.com/role=master -o name",
        shell=True,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return subprocess.run(
        ["kubectl", "-n", YAML_FILE, "exec", pod, "-c", "database", "--"]
        + ["psql", "-XAtq", "-d", dbname, "-c", sql],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def annotate_cluster(annotations: dict) -> None:
    _ = client.CustomObjectsApi().patch_namespaced_custom_object(
        "postgres-operator.crunchydata.com",
        "v1",
        YAML_FILE,
        "postgresclusters",
        YAML_FILE,
        {"metadata": {"annotations": annotations}},
    )


PATCH_DEPRECATED_ANNOTATIONS = {
    "metadata": {
        "annotations": {
            "crunchy-userinit.ramblurr.github.com/kopf": "yes",
            "crunchy-userinit.ramblurr.github.com/last-handled-configuration": "random config",
        }
    }
}


@pytest.mark.integration
@pytest.mark.requires_k8s
@pytest.mark.usefixtures("k8s_connection")
class IntegrationWithCluster1:
    def test_on_startup(self):
        from kopf.testing import KopfRunner

        settings = kopf.OperatorSettings()
        # settings.watching.server_timeout = 10

        with KopfRunner(
            [
                "run",
                "-n",
                YAML_FILE,
                "-m",
                "userinit.userinit",
            ],
            settings=settings,
        ) as runner:
            _ = subprocess.run(
                f"src/tests/integration/deploy.sh --pg {YAML_FILE}",
                shell=True,
                check=True,
                timeout=300,
                capture_output=True,
            )
            time.sleep(10)

        output = runner.output
        print(output)

        assert runner.exception is None
        assert runner.exit_code == 0
        assert "running in dev mode" in output
        assert (
            "database owner changed successfully: db=user2_main new_owner=user2 old_owner=postgres"
            in output
        )
        assert (
            "database owner changed successfully: db=user1_main new_owner=user1 old_owner=postgres"
            in output
        )

    def test_opt_in_grants(self):
        """Grants are applied only to the users listed in the cluster annotations."""
        from kopf.testing import KopfRunner

        # user1: CONNECT revoked from PUBLIC (what the Nextcloud installer does)
        _ = psql("REVOKE CONNECT ON DATABASE user1_main FROM PUBLIC")
        # Both users lose CREATE on public, like a database created before PG15
        for db in ("user1_main", "user2_main"):
            _ = psql("ALTER SCHEMA public OWNER TO postgres", dbname=db)

        with KopfRunner(
            ["run", "-n", YAML_FILE, "-m", "userinit.userinit"],
            settings=kopf.OperatorSettings(),
        ) as runner:
            time.sleep(5)
            annotate_cluster(
                {
                    f"{OPT_IN_PREFIX}/pgbouncer-connect": "user1, user2",
                    f"{OPT_IN_PREFIX}/public-schema": "user2",
                }
            )
            time.sleep(10)
            annotate_cluster(
                {
                    f"{OPT_IN_PREFIX}/pgbouncer-connect": None,
                    f"{OPT_IN_PREFIX}/public-schema": None,
                }
            )

        output = runner.output
        print(output)

        assert runner.exception is None
        assert runner.exit_code == 0
        assert (
            "connect granted successfully: db=user1_main role=_crunchypgbouncer"
            in output
        )
        assert (
            "_crunchypgbouncer can already connect to user2_main. nothing to do."
            in output
        )
        assert "public schema granted successfully: role=user2" in output
        assert (
            psql(
                "SELECT has_database_privilege('_crunchypgbouncer', 'user1_main', 'CONNECT')"
            )
            == "t"
        )
        # user2 is selected, user1 is not
        assert (
            psql(
                "SELECT has_schema_privilege('user2', 'public', 'CREATE')", "user2_main"
            )
            == "t"
        )
        assert (
            psql(
                "SELECT has_schema_privilege('user1', 'public', 'CREATE')", "user1_main"
            )
            == "f"
        )
        # Each grant actually run is reported on the PostgresCluster
        events = client.CoreV1Api().list_namespaced_event(
            YAML_FILE,
            field_selector=f"involvedObject.kind=PostgresCluster,involvedObject.name={YAML_FILE},reason=GrantApplied",
        )
        messages = sorted(e.message for e in events.items)
        assert messages == [
            "ALL on schema public of database user2_main to user2",
            "CONNECT on database user1_main to _crunchypgbouncer",
        ]
        # Posted as the controller, not as the framework
        assert {e.source.component for e in events.items} == {"crunchy-userinit"}

    def test_on_resume(self):
        """Test the controller's behavior when is restarted."""
        from kopf.testing import KopfRunner

        settings = kopf.OperatorSettings()
        v1 = client.CoreV1Api()

        _ = v1.patch_namespaced_secret(
            name=SECRET_NAME_USER1,
            namespace=YAML_FILE,
            body=PATCH_DEPRECATED_ANNOTATIONS,
        )
        with KopfRunner(
            [
                "run",
                "-n",
                YAML_FILE,
                "-m",
                "userinit.userinit",
            ],
            settings=settings,
        ) as runner:
            time.sleep(5)

        output = runner.output

        print(output)
        current_secret = v1.read_namespaced_secret(
            name=SECRET_NAME_USER1, namespace=YAML_FILE
        )

        _ = subprocess.run(
            f"src/tests/integration/deploy.sh --pg-delete {YAML_FILE}",
            shell=True,
            check=True,
            timeout=10,
            capture_output=True,
        )
        assert runner.exception is None
        assert runner.exit_code == 0
        assert "running in dev mode" in output
        assert "current owner of user2_main is user2. nothing to do." in output
        assert "current owner of user1_main is user1. nothing to do." in output
        # A restart only resumes the secrets: the opt-in handler does not run them again
        assert "opt-in annotations changed" not in output
        assert not any(
            "crunchy-userinit.ramblurr.github.com" in key
            for key in current_secret.metadata.annotations
        )
        # The diff-base annotation keeps no credentials
        diffbase = current_secret.metadata.annotations[
            "crunchy-userinit.drummyfloyd.github.com/last-handled-configuration"
        ]
        assert set(json.loads(diffbase)["data"]) == {"dbname", "user"}
