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
# Opt-in grants, set on the PostgresCluster metadata: comma-separated users or "*"
ANNOTATION_PGBOUNCER_CONNECT = f"{K8S_API_NS}/pgbouncer-connect"
ANNOTATION_PUBLIC_SCHEMA = f"{K8S_API_NS}/public-schema"
# PgBouncer auth_user created by the postgres-operator
PGBOUNCER_ROLE = "_crunchypgbouncer"
PGO_GROUP = "postgres-operator.crunchydata.com"
# v1 since CPK 6.0; set "v1beta1" for PGO 5.x
PGO_VERSION = os.environ.get("CRUI_PGO_VERSION", "v1")
PGO_PLURAL = "postgresclusters"
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
