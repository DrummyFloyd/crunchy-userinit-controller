<div align="center">

# crunchy-userinit-controller

_A simple k8s controller to assist in creating users for the [crunchydata postgres operator][crunchy]._

[![License](https://img.shields.io/github/license/ramblurr/crunchy-userinit-controller?style=for-the-badge&v1)](https://spdx.org/licenses/AGPL-3.0-or-later.html)

</div>

# Fork Information

This is a maintained fork of the [original crunchy-userinit-controller](https://github.com/Ramblurr/crunchy-userinit-controller). The original maintainer, @Ramblurr, no longer has a need for this project, as explained [here](https://github.com/Ramblurr/crunchy-userinit-controller) and [here](https://github.com/Ramblurr/crunchy-userinit-controller/issues/1#issuecomment-2676249147).

As a user of the [CrunchyData PostgreSQL Operator](https://github.com/CrunchyData/postgres-operator), I'll take up the torch and continue maintaining this project.

Special thanks to @Ramblurr for creating this valuable project and maintaining it. Your work has been instrumental in helping the community manage PostgreSQL user initialization with the CrunchyData operator. Thank you for your contributions and for making this project available to the open-source community.

## Migration from 0.x to v1.x

> **⚠️ BREAKING CHANGE:** If you're migrating from the original `ramblurr/crunchy-userinit-controller`, you **must** update your `PostgresCluster` manifests.

### What Changed

The API namespace has been migrated from:

- **Old:** `crunchy-userinit.ramblurr.github.com`
- **New:** `crunchy-userinit.drummyfloyd.github.com`

### Migration Steps

1. **Update your PostgresCluster labels:**

   ```yaml
   # ❌ OLD - Will cause errors
   metadata:
     labels:
       crunchy-userinit.ramblurr.github.com/enabled: "true"
       crunchy-userinit.ramblurr.github.com/superuser: "dbroot"

   # ✅ NEW - Required format
   metadata:
     labels:
       crunchy-userinit.drummyfloyd.github.com/enabled: "true"
       crunchy-userinit.drummyfloyd.github.com/superuser: "dbroot"
   ```

2. **Automated migration command:**

   ```bash
   # Update all your PostgresCluster YAML files
   sed -i 's/crunchy-userinit\.ramblurr\.github\.com/crunchy-userinit.drummyfloyd.github.com/g' *.yaml

   # Apply the updated manifests
   kubectl apply -f your-postgres-cluster.yaml
   ```

3. **Upgrade the controller:**

   ```bash
   # Uninstall old version
   helm uninstall -n YOUR_DB_NS crunchy-userinit-controller

   # Install new version
   helm repo add crunchy-userinit-controller https://drummyfloyd.github.io/crunchy-userinit-controller
   helm install -n YOUR_DB_NS crunchy-userinit-controller/crunchy-userinit-controller
   ```

### Impact

- **✅ No data loss:** Existing database ownership remains intact
- **✅ No service disruption:** Databases continue functioning normally
- **⚠️ New user processing:** Will fail until manifests are updated
- **🔧 One-time change:** Once migrated, no further action required

## What?

This is a k8s controller that exists to run `ALTER DATABASE "{database_name}" OWNER TO "{user_name}"`.

This controller should be deployed alongside a [crunchydata postgres-operator][crunchy] `PostgresCluster` instance.

It will watch for `pguser` secrets created by the PostgresCluster (due to you adding [users with databases](https://access.crunchydata.com/documentation/postgres-operator/latest/tutorials/basic-setup/user-management) to the cluster instance).

When a pguser secret is detected it will open up the secret, pull out the username and dbname, then using superuser creds, it will connect to the database and execute the above `ALTER` statement.

### Optional grants

Two grants are available on demand, through annotations on the `PostgresCluster` itself (not
`spec.metadata`, which the postgres-operator copies to the Postgres pods and would restart them).
Each annotation takes a comma-separated list of users, or `*` for all of them. Each grant is skipped
when already in place, and changing an annotation applies it right away.

| Annotation | Runs | Why |
| --- | --- | --- |
| `crunchy-userinit.drummyfloyd.github.com/pgbouncer-connect` | `GRANT CONNECT ON DATABASE "{database_name}" TO "_crunchypgbouncer"` | PgBouncer runs its `auth_query` inside the target database: it fails where `CONNECT` was revoked from `PUBLIC` (the Nextcloud installer does it). Skipped when PgBouncer is not enabled. |
| `crunchy-userinit.drummyfloyd.github.com/public-schema` | `GRANT ALL ON SCHEMA public TO "{user_name}"` | The database owner has it since PostgreSQL 15, but not on databases created by an older version. |

```yaml
apiVersion: postgres-operator.crunchydata.com/v1
kind: PostgresCluster
metadata:
  name: "app-db"
  annotations:
    crunchy-userinit.drummyfloyd.github.com/pgbouncer-connect: "nextcloud"
    crunchy-userinit.drummyfloyd.github.com/public-schema: "app1, app2"
```

## Why?

🤦

## How?

```
helm repo add crunchy-userinit-controller https://drummyfloyd.github.io/crunchy-userinit-controller
helm repo update
helm install -n YOUR_DB_NS crunchy-userinit-controller/crunchy-userinit-controller
```

You must label annotate your `PostgresCluster` so the `userinit-controller` can find it:

```yaml
---
apiVersion: postgres-operator.crunchydata.com/v1
kind: PostgresCluster
metadata:
  name: "app-db"
  namespace: database
spec:
  metadata:
    labels:
      # This label is required for the userinit-controller to activate
      crunchy-userinit.drummyfloyd.github.com/enabled: "true"
      # This label is required to tell the userinit-controller which user is the the superuser
      crunchy-userinit.drummyfloyd.github.com/superuser: "dbroot"
  postgresVersion: 16

  ... snip ...

  users:

    # This is the useruser that will be used by the userinit-controller to execute the SQL
    - name: "dbroot"
      databases:
        - "postgres"
      options: "SUPERUSER"
      password:
        type: AlphaNumeric

    # This is a user that will be affected by the userinit-controller
    - name: "nextcloud"
      databases:
        - "nextcloud"
      password:
        type: AlphaNumeric

  ... snip ...
```

### The Chart

The chart is pretty simple and is in [charts](/charts/crunchy-userinit/) directory.

### PGO 5.x

The controller uses the `postgres-operator.crunchydata.com/v1` API, available since
Crunchy Postgres for Kubernetes 6.0. On PGO 5.x, which only serves `v1beta1`, set
`CRUI_PGO_VERSION`:

```yaml
extraEnv:
  - name: CRUI_PGO_VERSION
    value: v1beta1
```

[crunchy]: https://access.crunchydata.com/documentation/postgres-operator/latest/

## Contributing

If you have improvements or fixes, we would love to have your contributions.
Please read [CONTRIBUTING.md](./CONTRIBUTING.md) for more information on the process we would like
contributors to follow.
