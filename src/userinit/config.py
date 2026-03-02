import logging
import os

#############
# Constants #
#############

APP_NAME = "crunchy-userinit"
K8S_API_NS = "crunchy-userinit.drummyfloyd.github.com"
K8S_API_NS_DEPRECATED = "crunchy-userinit.ramblurr.github.com"
LABEL_ENABLED = f"{K8S_API_NS}/enabled"
LABEL_ENABLED_DEPRECATED = f"{K8S_API_NS_DEPRECATED}/enabled"
LABEL_SUPERUSER = f"{K8S_API_NS}/superuser"
ANNOTATION_MIGRATED = f"{K8S_API_NS}/migrated"
LABELS_MATCH = {
    "postgres-operator.crunchydata.com/role": "pguser",
    LABEL_ENABLED: "true",
}
LABELS_MATCH_DEPRECATED = {
    "postgres-operator.crunchydata.com/role": "pguser",
    LABEL_ENABLED_DEPRECATED: "true",
}
truthy = (
    "true",
    "1",
    "yes",
    "on",
    "y",
)

CRUI_WATCH_NAMESPACE = os.environ.get("CRUI_WATCH_NAMESPACE", "default")
CRUI_DISABLE_CLUSTER_SCOPE = (
    os.environ.get("CRUI_DISABLE_CLUSTER_SCOPE", "false").lower() in truthy
)

DEV_MODE = os.environ.get("DEV_MODE", "false").lower() in truthy
logger = logging.getLogger(APP_NAME)
