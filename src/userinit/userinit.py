import kopf
from kubernetes_asyncio import config

from .config import DEV_MODE, K8S_API_NS, LABELS_MATCH, logger
from .connections import ConnectionManager
from .database import DatabaseManager
from .models import PgUserSecret


@kopf.on.startup()
async def configure(settings: kopf.OperatorSettings, **_):
    settings.persistence.diffbase_storage = kopf.AnnotationsDiffBaseStorage(
        prefix=K8S_API_NS,
        key="last-handled-configuration",
    )
    if DEV_MODE:
        logger.warning("running in dev mode")
        _ = await config.load_kube_config()
    else:
        config.load_incluster_config()


@kopf.on.update(
    "",
    "v1",
    "secret",
    labels=LABELS_MATCH,
)
@kopf.on.create(
    "",
    "v1",
    "secret",
    labels=LABELS_MATCH,
)
@kopf.on.resume(
    "",
    "v1",
    "secret",
    labels=LABELS_MATCH,
)
async def on_pguser_secret_created(body: kopf.Body, **_):
    """Handle PostgreSQL user secret creation/update events"""
    try:
        # Parse and validate the secret
        pguser_secret = PgUserSecret.from_k8s_secret(body)

        logger.info(
            f"found pguser to manage. secret_name={pguser_secret.secret_name}, cluster_name={pguser_secret.cluster_name} ns={pguser_secret.cluster_ns} superuser={pguser_secret.superuser}"
        )

        # Skip if this is the superuser itself
        if pguser_secret.role_name == pguser_secret.superuser:
            logger.info(f"skipping {pguser_secret.role_name} as it is the superuser")
            return

        # Get database connection and change ownership
        conn = await ConnectionManager.open_cluster_connection(
            pguser_secret.cluster_ns,
            pguser_secret.cluster_name,
            pguser_secret.superuser,
        )

        try:
            db_manager = DatabaseManager(conn)
            await db_manager.change_owner(pguser_secret.dbname, pguser_secret.role_name)
        except Exception as e:
            raise kopf.TemporaryError(
                f"Failed to change the owner of the database: db={pguser_secret.dbname} new_owner={pguser_secret.role_name} e={e}",
                delay=60,
            )
        finally:
            await conn.close()

    except kopf.TemporaryError:
        # Re-raise kopf errors as-is
        raise
    except Exception as e:
        # Wrap unexpected errors
        raise kopf.TemporaryError(
            f"Unexpected error processing pguser secret: {e}",
            delay=60,
        )
