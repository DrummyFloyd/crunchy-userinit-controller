import kopf
from kubernetes_asyncio import config

from .config import (
    CRUI_DISABLE_CLUSTER_SCOPE,
    DEV_MODE,
    K8S_API_NS,
    K8S_API_NS_DEPRECATED,
    LABELS_MATCH,
    LABELS_MATCH_DEPRECATED,
    logger,
)
from .connections import ConnectionManager
from .database import DatabaseManager
from .models import PgUserSecret


@kopf.on.startup(id="crui-startup")
async def configure(settings: kopf.OperatorSettings, **_):
    # INFO: Lines 20-27: tested with pytest.marker.integration
    settings.peering.standalone = True
    settings.scanning.disabled = CRUI_DISABLE_CLUSTER_SCOPE
    settings.persistence.diffbase_storage = kopf.AnnotationsDiffBaseStorage(
        prefix=K8S_API_NS, key="last-handled-configuration", v1=False
    )
    if DEV_MODE:
        logger.warning("running in dev mode")
        _ = await config.load_kube_config()
    else:  # pragma: no cover
        _ = config.load_incluster_config()


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
            _ = await conn.close()

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
