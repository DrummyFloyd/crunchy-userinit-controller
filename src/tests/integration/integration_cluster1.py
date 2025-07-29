# INFO: https://github.com/nolar/kopf/blob/main/examples/09-testing/test_example_09.py
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
                timeout=60,
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
        assert not any(
            "crunchy-userinit.ramblurr.github.com" in key
            for key in current_secret.metadata.annotations
        )
