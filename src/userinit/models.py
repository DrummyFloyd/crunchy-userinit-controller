import base64

import kopf

from .config import APP_NAME, LABEL_SUPERUSER


class PgUserSecret:
    """Represents a PostgreSQL user secret from Kubernetes"""

    def __init__(self, secret_name: str, cluster_name: str, cluster_ns: str,
                 superuser: str, dbname: str, role_name: str):
        self.secret_name = secret_name
        self.cluster_name = cluster_name
        self.cluster_ns = cluster_ns
        self.superuser = superuser
        self.dbname = dbname
        self.role_name = role_name

    @classmethod
    def from_k8s_secret(cls, secret_body) -> 'PgUserSecret':
        """Create PgUserSecret from Kubernetes secret body"""
        secret = secret_body
        secret_name = secret.metadata.name
        cluster_name = secret.metadata.labels["postgres-operator.crunchydata.com/cluster"]
        cluster_ns = secret.metadata.namespace
        superuser = secret.metadata.labels.get(LABEL_SUPERUSER)

        if not superuser:
            raise kopf.TemporaryError(
                f"superuser label not found on cluster, but {APP_NAME} is enabled. "
                f"Please check the documentation. cluster={cluster_name} ns={cluster_ns}",
                delay=60,
            )

        data = secret.get("data")
        dbname = decode_value(data.get("dbname"))
        role_name = decode_value(data.get("user"))

        err_msg = f"Could not parse %s from secret_name={secret_name}"
        if not dbname:
            raise kopf.TemporaryError(err_msg % "dbname", delay=30)
        if not role_name:
            raise kopf.TemporaryError(err_msg % "role_name", delay=30)

        return cls(secret_name, cluster_name, cluster_ns, superuser, dbname, role_name)


def decode_value(v: str) -> str|None :
    """Decode base64 value from Kubernetes secret"""
    if not v:
        return None
    return base64.b64decode(v).decode("utf-8")
