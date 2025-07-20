import asyncio
import base64
import logging
import os
import re
from pprint import pprint
from typing import Dict, Optional

import asyncpg
import kopf
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client.api_client import ApiClient

#############
# Constants #
#############

APP_NAME = "crunchy-userinit"
K8S_API_NS = "crunchy-userinit.ramblurr.github.com"
LABEL_ENABLED = f"{K8S_API_NS}/enabled"
LABEL_SUPERUSER = f"{K8S_API_NS}/superuser"
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

#######################
# Lifecycle Functions #
#######################


@kopf.on.startup()
async def configure(settings: kopf.OperatorSettings, **_):
    settings.persistence.diffbase_storage = kopf.AnnotationsDiffBaseStorage(
        prefix=K8S_API_NS,
        key="last-handled-configuration",
    )
    if DEV_MODE:
        logger.warning("running in dev mode")
        await config.load_kube_config()
    else:
        config.load_incluster_config()


@kopf.on.update(
    "",
    "v1",
    "secret",
    labels={"postgres-operator.crunchydata.com/role": "pguser", LABEL_ENABLED: "true"},
)
@kopf.on.create(
    "",
    "v1",
    "secret",
    labels={"postgres-operator.crunchydata.com/role": "pguser", LABEL_ENABLED: "true"},
)
@kopf.on.resume(
    "",
    "v1",
    "secret",
    labels={"postgres-operator.crunchydata.com/role": "pguser", LABEL_ENABLED: "true"},
)
async def on_pguser_secret_created(body, **kwargs):
    secret = body
    secret_name = secret.metadata.name
    cluster_name = secret.metadata.labels["postgres-operator.crunchydata.com/cluster"]
    cluster_ns = secret.metadata.namespace
    superuser = secret.metadata.labels.get(
        LABEL_SUPERUSER,
    )
    if not superuser:
        raise kopf.TemporaryError(
            f"superuser label not found on cluster, but {APP_NAME} is enabled. Please check the documentation Please check the documentation. cluster={cluster_name} ns={cluster_ns}",
            delay=60,
        )
    logger.info(
        f"found pguser to manage. secret_name={secret_name}, cluster_name={cluster_name} ns={cluster_ns} superuser={superuser}"
    )
    data = secret.get("data")
    dbname = decode_value(data.get("dbname"))
    role_name = decode_value(data.get("user"))
    err_msg = (f"Could not parse %s from secret_name={secret_name}",)
    if not dbname:
        raise kopf.TemporaryError(err_msg.format("dbname"), delay=30)
    if not role_name:
        raise kopf.TemporaryError(err_msg.format("role_name"), delay=30)

    if role_name == superuser:
        logger.info(f"skipping {role_name} as it is the superuser")
        return

    conn = await open_cluster_connection(cluster_ns, cluster_name, superuser)

    try:
        await change_owner(conn, dbname, role_name)
    except Exception as e:
        raise kopf.TemporaryError(
            f"Failed to change the owner of the database: db={database_name} new_owner={role_name} e={e}",
            delay=60,
        )


#####################
# Utility Functions #
#####################


async def change_owner(
    conn: asyncpg.Connection, database_name: str, role_name: str
) -> None:
    """
    Change the owner of a PostgreSQL database using asyncpg with improved input validation.

    Parameters:
    - conn: An asyncpg connection object.
    - database_name (str): The name of the database.
    - new_owner (str): The name of the new owner role.

    All exceptions are delegated to the caller.
    """
    check_owner_sql = f"""
    SELECT pg_roles.rolname
    FROM pg_database
    JOIN pg_roles ON pg_database.datdba = pg_roles.oid
    WHERE pg_database.datname = $1;
    """
    # Unfortunately there is no way to use prepared statements for DDL operations like this
    alter_sql = f'ALTER DATABASE "{database_name}" OWNER TO "{role_name}"'
    current_owner = await conn.fetchval(check_owner_sql, database_name)
    if current_owner == role_name:
        logger.info(
            f"current owner of {database_name} is {current_owner}. nothing to do."
        )
        return
    else:
        logger.info(
            f"changing owner of db={database_name} from old_owner={current_owner} to new_ownwer={role_name} with '{alter_sql}'"
        )
        await conn.execute(alter_sql)
    logger.info(
        f"database owner changed successfully: db={database_name} new_owner={role_name} old_owner={current_owner}"
    )


def decode_value(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return base64.b64decode(v).decode("utf-8")


async def get_superuser_uri(
    cluster_ns: str, cluster_name: str, superuser_name: str
) -> str:
    secret_name = f"{cluster_name}-pguser-{superuser_name}"
    print(f"Getting secret: {secret_name}")
    async with ApiClient() as api:
        v1 = client.CoreV1Api(api)
        secret = await v1.read_namespaced_secret(secret_name, cluster_ns)
        secret_data = secret.data
        if not DEV_MODE:
            uri = decode_value(secret_data.get("uri"))
            if not uri:
                raise kopf.TemporaryError(
                    f"Could not parse connection uri for secret_name={secret_name}, cluster={cluster_name} ns={cluster_ns} superuser={superuser_name}",
                    delay=30,
                )
            return uri
        else:
            # in devmode we are port-forwarding to the pg pod
            user = decode_value(secret_data.get("user"))
            password = decode_value(secret_data.get("password"))
            dbname = decode_value(secret_data.get("dbname"))
            port = decode_value(secret_data.get("port"))
            return f"postgresql://{user}:{password}@localhost:{port}/{dbname}"


async def open_cluster_connection(
    cluster_ns: str, cluster_name: str, superuser_name: str
):
    uri = await get_superuser_uri(cluster_ns, cluster_name, superuser_name)
    try:
        return await asyncpg.connect(uri)
    except Exception as e:
        raise kopf.TemporaryError(
            f"Cannot connect to the database cluster={cluster_name} ns={cluster_ns} superuser={superuser_name}, e={e}",
            delay=10,
        )
