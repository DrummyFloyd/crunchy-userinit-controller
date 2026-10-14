import os

import kopf
from kubernetes_asyncio import config

from .config import (
    ANNOTATION_PGBOUNCER_CONNECT,
    ANNOTATION_PUBLIC_SCHEMA,
    APP_NAME,
    CRUI_DISABLE_CLUSTER_SCOPE,
    DEV_MODE,
    K8S_API_NS,
    K8S_API_NS_DEPRECATED,
    LABELS_MATCH,
    LABELS_MATCH_DEPRECATED,
    PGBOUNCER_ROLE,
    PGO_GROUP,
    PGO_PLURAL,
    PGO_VERSION,
    logger,
)
from .connections import ConnectionManager
from .database import DatabaseManager
from .models import PgUserSecret, selects

# The only secret data the handler reads: changes to them must still trigger it
TRACKED_DATA_KEYS = ("dbname", "user")


class CredentialFreeDiffBaseStorage(kopf.AnnotationsDiffBaseStorage):
    """Diff-base annotation without the pguser credentials.

    kopf stores the whole object as last-handled-configuration, so the password,
    verifier and URIs of the secret were copied in clear into an annotation.
    """

    def build(self, *, body, extra_fields=None):
        essence = super().build(body=body, extra_fields=extra_fields)
        if "data" in essence:
            essence["data"] = {
                k: v for k, v in essence["data"].items() if k in TRACKED_DATA_KEYS
            }
        return essence


@kopf.on.startup(id="crui-startup")
async def configure(settings: kopf.OperatorSettings, **_):
    # INFO: Lines 20-27: tested with pytest.marker.integration
    settings.peering.standalone = True
    settings.scanning.disabled = CRUI_DISABLE_CLUSTER_SCOPE
    settings.persistence.diffbase_storage = CredentialFreeDiffBaseStorage(
        prefix=K8S_API_NS, key="last-handled-configuration", v1=False
    )
    # Events show the controller, not the framework ("From" in kubectl describe)
    settings.posting.reporting_component = APP_NAME
    settings.posting.reporting_instance = os.environ.get("HOSTNAME", APP_NAME)
    settings.posting.event_name_prefix = f"{APP_NAME}-"
    if DEV_MODE:
        logger.warning("running in dev mode")
        _ = await config.load_kube_config()
    else:  # pragma: no cover
        _ = config.load_incluster_config()


async def init_pguser(pguser_secret: PgUserSecret, cluster: dict | None = None):
    """Set the database owner, then the opt-in grants selected by the cluster
    annotations (PostgresCluster read when not given).

    Grants actually run, or failing, are reported as events on the PostgresCluster.
    """

    # Skip if this is the superuser itself
    if pguser_secret.role_name == pguser_secret.superuser:
        logger.info(f"skipping {pguser_secret.role_name} as it is the superuser")
        return

    if cluster is None:
        cluster = await ConnectionManager.get_cluster(
            pguser_secret.cluster_ns, pguser_secret.cluster_name
        )
    annotations = cluster.get("metadata", {}).get("annotations") or {}
    db, role = pguser_secret.dbname, pguser_secret.role_name

    pgbouncer_connect = selects(
        annotations.get(ANNOTATION_PGBOUNCER_CONNECT), pguser_secret.role_name
    )
    public_schema = selects(
        annotations.get(ANNOTATION_PUBLIC_SCHEMA), pguser_secret.role_name
    )

    # Get database connection and change ownership
    conn = await ConnectionManager.open_cluster_connection(
        pguser_secret.cluster_ns,
        pguser_secret.cluster_name,
        pguser_secret.superuser,
    )

    try:
        db_manager = DatabaseManager(conn)
        await db_manager.change_owner(pguser_secret.dbname, pguser_secret.role_name)
        if pgbouncer_connect and await db_manager.grant_pgbouncer_connect(db):
            kopf.info(
                cluster,
                reason="GrantApplied",
                message=f"CONNECT on database {db} to {PGBOUNCER_ROLE}",
            )
    except Exception as e:
        message = f"Failed to set up the database: db={db} owner={role} e={e}"
        kopf.warn(cluster, reason="UserInitFailed", message=message)
        raise kopf.TemporaryError(message, delay=60)
    finally:
        _ = await conn.close()

    if not public_schema:
        return

    # Schema privileges are per database: connect to the target one
    db_conn = await ConnectionManager.open_cluster_connection(
        pguser_secret.cluster_ns,
        pguser_secret.cluster_name,
        pguser_secret.superuser,
        database=pguser_secret.dbname,
    )

    try:
        if await DatabaseManager(db_conn).grant_public_schema(role):
            kopf.info(
                cluster,
                reason="GrantApplied",
                message=f"ALL on schema public of database {db} to {role}",
            )
    except Exception as e:
        message = f"Failed to grant the public schema: db={db} role={role} e={e}"
        kopf.warn(cluster, reason="UserInitFailed", message=message)
        raise kopf.TemporaryError(message, delay=60)
    finally:
        _ = await db_conn.close()


@kopf.on.event(PGO_GROUP, PGO_VERSION, PGO_PLURAL, id="opt-in-crui")
async def on_cluster_event(body: kopf.Body, memo: kopf.Memo, **_):
    """Re-run the pguser secrets of a cluster when its opt-in annotations change.

    on.event keeps no state on the PostgresCluster: the last applied values live
    in the per-object memo.
    """
    name, ns = body.metadata.name, body.metadata.namespace
    current = tuple(
        body.metadata.annotations.get(a)
        for a in (ANNOTATION_PGBOUNCER_CONNECT, ANNOTATION_PUBLIC_SCHEMA)
    )
    # First sight (controller start, new cluster): only remember the values,
    # the secret handlers (resume, create) already apply them
    if "opt_in" not in memo:
        memo["opt_in"] = current
        return
    if memo["opt_in"] == current:
        return

    logger.info(f"opt-in annotations changed on cluster={name} ns={ns}: {current}")
    try:
        for raw in await ConnectionManager.list_pguser_secrets(ns, name):
            await init_pguser(PgUserSecret.from_k8s_secret(kopf.Body(raw)), body)
    # Events are not retried: keep memo unchanged so the next event retries
    except Exception as e:  # noqa: BLE001
        logger.error(f"failed to apply opt-in grants on cluster={name} ns={ns}: {e}")
        return
    memo["opt_in"] = current


@kopf.on.create("", "v1", "secret", labels=LABELS_MATCH, id="create-crui")
@kopf.on.update("", "v1", "secret", labels=LABELS_MATCH, id="update-crui")
@kopf.on.resume("", "v1", "secret", labels=LABELS_MATCH, id="resume-crui")
async def on_pguser_secret_created(body: kopf.Body, patch: kopf.Patch, **_):
    """Handle PostgreSQL user secret creation/update events"""

    # INFO: block if: tested with pytest.marker.integration
    for annotation in body.metadata.annotations:
        if annotation.startswith(K8S_API_NS_DEPRECATED):
            logger.warning(
                f"removing deprecated annotation {annotation} from secret {body.metadata.name}"
            )
            patch.metadata.annotations[annotation] = None

    try:
        # Parse and validate the secret
        pguser_secret = PgUserSecret.from_k8s_secret(body)

        logger.info(
            f"found pguser to manage. secret_name={pguser_secret.secret_name}, cluster_name={pguser_secret.cluster_name} ns={pguser_secret.cluster_ns} superuser={pguser_secret.superuser}"
        )

        await init_pguser(pguser_secret)

    except kopf.TemporaryError:
        # Re-raise kopf errors as-is
        raise
    except Exception as e:  # pragma: no cover no need to test this
        # Wrap unexpected errors
        raise kopf.TemporaryError(
            f"Unexpected error processing pguser secret: {e}",
            delay=60,
        )


@kopf.on.create(
    "", "v1", "secret", labels=LABELS_MATCH_DEPRECATED, id="create-deprecated"
)
@kopf.on.update(
    "", "v1", "secret", labels=LABELS_MATCH_DEPRECATED, id="update-deprecated"
)
@kopf.on.resume(
    "", "v1", "secret", labels=LABELS_MATCH_DEPRECATED, id="resume-deprecated"
)
async def on_deprecated_labels(body: kopf.Body, **_):
    """Handle deprecated label events"""
    raise kopf.PermanentError(
        f"deprecated labels detected on secret {body.metadata.name}, please update to use {K8S_API_NS} instead of {K8S_API_NS_DEPRECATED}"
    )
