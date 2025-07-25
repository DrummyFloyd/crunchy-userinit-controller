import asyncpg
import kopf
from kubernetes_asyncio import client
from kubernetes_asyncio.client.api_client import ApiClient

from .config import DEV_MODE
from .models import decode_value


class ConnectionManager:
    """Handles database connections"""

    @staticmethod
    async def get_superuser_uri(
        cluster_ns: str, cluster_name: str, superuser_name: str
    ) -> str:
        """
        Get the database URI for the superuser.

        This function retrieves connection information for a PostgreSQL superuser
        from a Kubernetes Secret and constructs a connection URI.

        Args:
            cluster_ns (str): Kubernetes namespace where the cluster is deployed
            cluster_name (str): Name of the PostgreSQL cluster
            superuser_name (str): Name of the PostgreSQL superuser

        Returns:
            str: A PostgreSQL connection URI string

        Raises:
            kopf.TemporaryError: If the connection URI cannot be parsed from the secret
        """
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
                        f"Could not parse connection uri for secret_name={secret_name}, "
                        f"cluster={cluster_name} ns={cluster_ns} superuser={superuser_name}",
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

    @staticmethod
    async def open_cluster_connection(
        cluster_ns: str, cluster_name: str, superuser_name: str
    ) -> asyncpg.Connection:
        """Open a database connection using superuser credentials.

        Attempts to establish a connection to the PostgreSQL database using the
        superuser URI obtained from ConnectionManager.get_superuser_uri.

        Args:
            cluster_ns: The namespace where the database cluster is deployed
            cluster_name: The name of the database cluster
            superuser_name: The name of the superuser to connect with

        Returns:
            asyncpg.Connection: An established database connection

        Raises:
            kopf.TemporaryError: If the connection cannot be established,
                will retry after 10 seconds
        """
        uri = await ConnectionManager.get_superuser_uri(
            cluster_ns, cluster_name, superuser_name
        )
        try:
            return await asyncpg.connect(uri)
        except Exception as e:
            raise kopf.TemporaryError(
                f"Cannot connect to the database cluster={cluster_name} "
                f"ns={cluster_ns} superuser={superuser_name}, e={e}",
                delay=10,
            )
