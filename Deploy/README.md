# BigProject — Azure Application Infrastructure

## Overview

This directory provisions the application infrastructure for BigProject on
Microsoft Azure, using [Pulumi](https://www.pulumi.com/) (Python). It is the
Azure-native equivalent of an AWS/Terraform reference architecture,
re-designed around Azure's native service catalog.

Depends on `../SetUp/`, deployed first, consumed here via
`pulumi.StackReference`.

## Architecture summary

| Layer | Azure Service | Notes |
|---|---|---|
| Network | VNet, 4 subnets, 4 NSGs | Public/private segmentation, least-privilege traffic rules |
| Database | Postgres Flexible Server (primary + replica) | GeneralPurpose tier, VNet-integrated, TimescaleDB |
| Container Registry | Azure Container Registry | Application image |
| Compute | AKS | Standard tier control plane, 2-node system pool, CNI Overlay |
| Ingress | Application Gateway (Standard_v2) | HTTP + HTTPS, health-probed, direct-to-node backend |
| Identity | Azure AD login (App Registration in `SetUp/`) | Real user authentication, role-based access (Admin/Viewer) |
| Secrets | Key Vault (in `SetUp/`) + Kubernetes Secrets | SP credentials, DB password, Azure AD client secret |

## Request flow

```
Browser → Application Gateway (HTTPS, public IP, self-signed cert)
        → health probe on /health, fixed NodePort (32665)
        → AKS node private IPs (private-app-subnet)
        → local pod on that node (externalTrafficPolicy: Local)
        → /login redirects to Microsoft Entra sign-in
        → /auth/callback validates the result, sets a signed session cookie
          containing the user's name and App Role
        → /sensors reads the session cookie, queries Postgres with a
          role-appropriate level of detail (Admin: hourly, Viewer: daily)
```

## Network topology

| Subnet | CIDR | Purpose | NSG |
|---|---|---|---|
| `public-subnet` | 10.0.1.0/24 | Application Gateway | `public-nsg` — 80/443 from Internet, GatewayManager on 65200-65535 |
| `private-app-subnet` | 10.0.2.0/24 | AKS nodes | `app-nsg` — app port and NodePort allowed only from `public-subnet` |
| `private-db-subnet` | 10.0.3.0/24 | Postgres primary + replica | `db-nsg` — Postgres port from `private-app-subnet`, `admin-subnet`, and within its own subnet |
| `admin-subnet` | 10.0.4.0/28 | Temporary debugging tools | `admin-nsg` — denies all inbound |

## Ingress design: direct-to-node backend pool

Application Gateway's backend pool targets AKS node private IPs directly on
a fixed Kubernetes `NodePort`, rather than a Kubernetes `LoadBalancer`
Service (the AKS-managed internal Standard Load Balancer).

**Rationale:** the AKS-managed internal Load Balancer, combined with its
default Direct Server Return (floating IP) configuration, does not reliably
serve Application Gateway v2's cross-subnet probe and proxy traffic in this
environment — confirmed via isolated testing (NSGs, probe config, and pods
all individually verified correct and healthy; bypassing the LB and hitting
node IPs directly resolved it immediately).

**Tradeoff:** node IPs are not guaranteed stable across node replacement or
scaling. This design assumes a fixed, non-autoscaling node pool. For dynamic
node counts, use **AGIC (Application Gateway Ingress Controller)** instead.

## TLS

Application Gateway serves both HTTP (port 80) and HTTPS (port 443) with a
**self-signed certificate**, generated locally and supplied to Pulumi as an
encrypted config secret:

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=<application-gateway-public-ip>"
openssl pkcs12 -export -out cert.pfx -inkey key.pem -in cert.pem -passout pass:CertPass123!

base64 -w0 cert.pfx | pulumi config set --secret appgw_ssl_cert_data
pulumi config set --secret appgw_ssl_cert_password 'CertPass123!'
```

HTTPS is required because **Azure AD does not accept plain HTTP redirect
URIs** (except `localhost`) — this is why TLS was added specifically to
support the login flow, not as a general hardening pass. Browsers will show
a certificate warning; this is expected for a self-signed cert and should be
replaced with a real certificate (e.g. via Key Vault-integrated
certificates, or a proper CA) before this pattern is used beyond a demo.

## Prerequisites

- `../SetUp/` deployed
- Pulumi CLI, Azure CLI, `kubectl`, `docker`, `openssl` installed
- Correct Azure subscription selected (`az account show`)
- Python 3.12+

## Deployment guide

Follow in order. Steps have real dependencies on each other — skipping
ahead reliably produces specific, documented failures (see "Known issues on
a fresh deployment" below).

### 1. Configure the stack (first time only)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

pulumi config set --secret db_admin_password 'YourStrongPasswordHere'
pulumi config set azure-native:resourceProviderRegistrations all
```

**Choose the database password deliberately and remember it exactly** — it
is used again in step 5 for a Kubernetes Secret, in a separate manual
command with no automatic sync. Always re-read it with `pulumi config get
db_admin_password` rather than retyping from memory.

Application Gateway's backend pool needs AKS node IPs, unknown until the
cluster exists. Set placeholders for the first apply:

```bash
pulumi config set app_backend_ip_1 10.0.2.4
pulumi config set app_backend_ip_2 10.0.2.5
```

Generate and store the TLS certificate (see "TLS" above):

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=0.0.0.0"
openssl pkcs12 -export -out cert.pfx -inkey key.pem -in cert.pem -passout pass:CertPass123!
base64 -w0 cert.pfx | pulumi config set --secret appgw_ssl_cert_data
pulumi config set --secret appgw_ssl_cert_password 'CertPass123!'
```

(The certificate's CN doesn't need to match the real IP for a self-signed
cert used only with `curl -k` / browser click-through — it becomes worth
matching only if replaced with a real, validated certificate later.)

### 2. Provision the infrastructure

```bash
pulumi preview
pulumi up
```

Creates network, NSGs, Postgres (primary + replica), ACR, AKS, and
Application Gateway (HTTP + HTTPS). Typically 20–30 minutes.

### 3. Update the Azure AD redirect URI with the real public IP

```bash
pulumi stack output appgw_public_ip
```

Go to `../SetUp/app_registration.py`, update the `redirect_uri` argument to
`https://<real-ip>/auth/callback`, then:

```bash
cd ../SetUp
pulumi up
cd ../Deploy
```

This updates the existing Azure AD Application in place — no need to
recreate it or its secret.

### 4. Build and publish the application image

```bash
cd app
az acr login --name bigprojectacr
docker build -t bigprojectacr.azurecr.io/bigproject-app:latest .
docker push bigprojectacr.azurecr.io/bigproject-app:latest
cd ..
```

### 5. Connect to the cluster and create secrets

```bash
az aks get-credentials --resource-group bigproject-rg --name bigproject-aks
kubectl get nodes -o wide
```

Confirm the node IPs match `app_backend_ip_1` / `app_backend_ip_2` from
step 1; update and re-apply in step 7 if they differ.

**Database credentials** — read the real value from Pulumi, do not retype:

```bash
pulumi config get db_admin_password
kubectl create secret generic db-credentials \
  --from-literal=password='<paste-the-exact-value-from-above>'
```

**Azure AD credentials:**

```bash
az keyvault secret show --vault-name $(cd ../SetUp && pulumi stack output key_vault_name) --name app-client-secret --query value -o tsv
kubectl create secret generic aad-credentials \
  --from-literal=client-secret='<paste-the-exact-value-from-above>'
```

### 6. Deploy the application

```bash
cd k8s
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f service-nodeport.yaml
cd ..
```

```bash
kubectl get pods -o wide
```

**Expect `CrashLoopBackOff` at this point.** This is normal — see
"Database initialization" below before treating it as a fault.

### 7. Reconcile node IPs with Application Gateway

Only if the node IPs from step 5 differ from what's currently configured:

```bash
pulumi config set app_backend_ip_1 <real-node-1-ip>
pulumi config set app_backend_ip_2 <real-node-2-ip>
pulumi up
```

### 8. Verify

In-cluster:

```bash
kubectl run curl-test --image=curlimages/curl:latest --rm -it --restart=Never -- sh
curl http://bigproject-app-service/health
curl http://bigproject-app-service/
```

Public path (once pods are `1/1 Running` per step 6's note):

```bash
pulumi stack output appgw_public_ip
curl -k https://<ip>/health
curl -k https://<ip>/
```

**Login flow requires a real browser** (interactive Microsoft sign-in
cannot be tested with `curl`). Navigate to:

```
https://<appgw_public_ip>/login
```

Accept the self-signed certificate warning, sign in, and confirm redirect
to `/sensors` with `"logged_in": true` (visible at `/`) and role-appropriate
data returned (`/sensors`).

New users default to the `Viewer` role. To grant `Admin`, see
`../SetUp/README.md` → "Assigning users to App Roles."

## Database initialization

TimescaleDB activation is a two-step process: allow-list via
`azure.extensions`, then add to `shared_preload_libraries` — a **static**
parameter requiring a Postgres restart before `CREATE EXTENSION
timescaledb;` succeeds. Pulumi applies both settings but cannot trigger the
restart. **This reliably produces `CrashLoopBackOff` on first deployment**,
with logs showing:

```
psycopg2.OperationalError: SSL connection has been closed unexpectedly
```

Fix, treated as a standard step of every fresh deployment:

```bash
az postgres flexible-server restart --resource-group bigproject-rg --name bigproject-pg-server
az postgres flexible-server show --resource-group bigproject-rg --name bigproject-pg-server --query state -o tsv
# wait for "Ready"
kubectl delete pod -l app=bigproject-app
kubectl get pods -o wide -w
```

**A second, distinct failure mode** produces `FATAL: password
authentication failed for user "pgadmin"` instead — this means the
`db-credentials` Kubernetes Secret doesn't match Postgres's actual password.
Fix by re-reading the value from Pulumi (never retype from memory) and
recreating the secret — see step 5.

```bash
kubectl logs -l app=bigproject-app --tail=20   # confirms which of the two this is
```

## AKS cluster configuration

- Control plane: Standard tier, SLA-backed.
- Node pool: 2× `Standard_D2s_v3`, system pool.
- Networking: Azure CNI Overlay, dedicated service CIDR (`10.100.0.0/16`).
- Image pulls: kubelet identity has `AcrPull` on the registry directly.
- VNet permissions: cluster identity requires **Network Contributor** on
  the (user-managed) VNet — without it, load balancer operations fail
  silently with `AuthorizationFailed`, visible only via `kubectl describe
  service`.

## Application deployment

Manifests in `k8s/`: `deployment.yaml` (2 replicas, preferred pod
anti-affinity, `/health` probes), `service.yaml` (`ClusterIP`, in-cluster),
`service-nodeport.yaml` (`NodePort` fixed at `32665`, App Gateway's target).

## Application code — Azure AD login

`app/main.py` uses `msal` (Microsoft's auth library) for the OAuth2 flow:

- `GET /login` — redirects to Microsoft's sign-in page
- `GET /auth/callback` — exchanges the returned code for tokens, reads the
  `roles` claim from the ID token, signs a session cookie (via
  `itsdangerous`) containing the user's name and role
- `GET /logout` — clears the session cookie
- `GET /sensors` — requires a valid session; queries Postgres with detail
  proportional to role (`Admin`: hourly aggregates; `Viewer`: daily)

Required environment variables (set in `deployment.yaml`):
`AAD_CLIENT_ID`, `AAD_TENANT_ID` (plain values), `AAD_CLIENT_SECRET`
(from the `aad-credentials` Secret).

**Role changes require re-login** — the role is embedded in the ID token at
login time, not re-checked on subsequent requests.

## Connecting to Postgres (private-only, no public IP)

```bash
az provider register --namespace Microsoft.ContainerInstance   # one-time, no cost
az container create \
  --resource-group bigproject-rg \
  --name psql-jumpbox \
  --image postgres:16 \
  --os-type Linux \
  --cpu 1 \
  --memory 1 \
  --vnet bigproject-vnet \
  --subnet admin-subnet \
  --command-line "sleep 3600" \
  --restart-policy Never

az container exec --resource-group bigproject-rg --name psql-jumpbox --exec-command "/bin/bash"
psql "host=bigproject-pg-server.postgres.database.azure.com port=5432 dbname=postgres user=pgadmin sslmode=require"
```

`\dx` confirms `timescaledb`. Delete the jumpbox after use — not managed by
Pulumi:

```bash
az container delete --resource-group bigproject-rg --name psql-jumpbox --yes
```

## Retrieving stack outputs

```bash
pulumi stack output
pulumi stack output appgw_public_ip
pulumi stack output aks_cluster_name
```

## Cost management

Pay-as-you-go, no trial credit. `pulumi destroy` at the end of each
session — Postgres, AKS, and Application Gateway are the largest costs.

```bash
pulumi destroy
```

If destroy fails on `shared-preload-libraries-config` with
`Code="InvalidParameterValue"` (a known Azure provider bug where the delete
operation incorrectly resends `source="user-override"`), remove it from
Pulumi state directly — the underlying Azure config is deleted
automatically with the parent Postgres server regardless:

```bash
pulumi stack export | grep -A2 "shared-preload-libraries-config"
pulumi state delete '<urn-from-above>'
pulumi destroy
```

`az consumption usage list` lags 24–48 hours. Key Vault deletions are
soft-deleted for up to 90 days:

```bash
az keyvault list-deleted --output table
az keyvault purge --name <vault-name>
```

Jumpbox Container Instances are not managed by Pulumi.

## Design notes

- Read replicas require GeneralPurpose tier (Burstable doesn't support them).
- Replicas need the `network` block explicitly repeated — no automatic
  inheritance from the primary.
- **Postgres `Configuration` resources must be applied sequentially**, not
  in parallel — `azure-extensions-config` and
  `shared-preload-libraries-config` both mutate the same server;
  concurrent application intermittently fails with `Code="ServerIsBusy"`.
  Fixed via an explicit `depends_on` chain in `database.py`.
- Subnet delegation is exclusive per service; removal can't happen in the
  same operation as deleting the resource that required it.
- Private DNS types live in `pulumi_azure_native.privatedns`, not `.network`.
- Pulumi `Output[T]` needs `.apply()` before string interpolation.
- Regional VM SKU availability/quota varies by subscription and generation.
- A user-managed VNet needs explicit Network Contributor for the AKS identity.
- Application Gateway sub-resource IDs must be built deterministically when
  created in the same apply as the parent gateway.
- `db-nsg` must explicitly allow Postgres traffic within its own subnet,
  not only from other subnets — required for primary↔replica replication.
- The database password exists in two unsynced places (Pulumi config, a
  Kubernetes Secret) — always read from Pulumi, never retype.
- **Azure AD redirect URIs require HTTPS**, and Application Gateway's
  public IP is not known until after its own first deployment, creating a
  genuine bootstrap ordering dependency between `SetUp/` and `Deploy/` —
  see step 3 of the deployment guide.
- `azuread.Application`'s roles argument is `app_roles` (plural).

## Build status

| Component | Status |
|---|---|
| VNet, 4 subnets, NSGs | Complete |
| Postgres primary + replica + TimescaleDB | Complete |
| ACR | Complete |
| AKS cluster | Complete |
| Application on AKS (2 replicas, anti-affinity) | Complete, verified |
| Application Gateway, HTTP + HTTPS | Complete, verified |
| **Azure AD login + role-based access (Admin/Viewer)** | **Complete, verified live in browser** |
| Azure Monitor / Log Analytics | Not started |

See `../scenario.md` for the architecture diagram.
