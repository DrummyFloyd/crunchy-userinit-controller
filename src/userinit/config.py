import logging
import os

#############
# Constants #
#############

APP_NAME = "crunchy-userinit"
K8S_API_NS = "crunchy-userinit.ramblurr.github.com"
LABEL_ENABLED = f"{K8S_API_NS}/enabled"
LABEL_SUPERUSER = f"{K8S_API_NS}/superuser"
LABELS_MATCH = {
    "postgres-operator.crunchydata.com/role": "pguser",
    LABEL_ENABLED: "true",
}
CRUI_WATCH_NAMESPACE = os.environ.get("CRUI_WATCH_NAMESPACE", "default")

truthy = (
    "true",
    "1",
    "yes",
    "on",
    "y",
)

DEV_MODE = os.environ.get("DEV_MODE", "false").lower() in truthy
logger = logging.getLogger(APP_NAME)
