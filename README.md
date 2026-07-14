# BigProject — Azure Cloud Infrastructure

Production-shaped, end-to-end cloud infrastructure on Microsoft Azure —
private networking, managed Kubernetes, a time-series database, TLS
ingress, real user authentication, and centralized observability, all
defined as code with [Pulumi](https://www.pulumi.com/) (Python).

## Architecture

![BigProject Azure Architecture](./diagram.jpg)

**Request flow:**

```
Browser
  │  HTTPS
  ▼
Application Gateway (public subnet, TLS, health-probed)
  │  routes directly to AKS node private IPs on a fixed NodePort
  ▼
AKS  (2-node cluster, private subnet)
  │  /login → Azure AD (Microsoft Entra) sign-in
  │  /auth/callback → session cookie with user's role (Admin / Viewer)
  ▼
Azure Database for PostgreSQL  (private subnet, primary + read replica)
  + TimescaleDB extension for time-series sensor data

Postgres, AKS, and Application Gateway all send diagnostics to a shared
Azure Monitor / Log Analytics Workspace.
```

## Technology stack

| Category | Technology |
|---|---|
| Infrastructure as Code | Pulumi (Python) |
| Cloud provider | Microsoft Azure |
| Compute | Azure Kubernetes Service (AKS) |
| Database | Azure Database for PostgreSQL Flexible Server + TimescaleDB |
| Container registry | Azure Container Registry |
| Ingress / load balancing | Azure Application Gateway (Standard_v2) |
| Identity (infrastructure) | Azure AD Service Principals, custom RBAC roles |
| Identity (application) | Azure AD (Microsoft Entra ID) OAuth2 login, App Roles |
| Secrets | Azure Key Vault |
| Observability | Azure Monitor / Log Analytics |
| Application | FastAPI (Python), `msal`, `psycopg2` |

## Repository layout

```
.
├── SetUp/          Bootstrap stack: resource group, identities, RBAC roles,
│                   Key Vault, Azure AD App Registration for user login
├── Deploy/         Application stack: network, database, AKS, ingress,
│   ├── app/        The demo application (FastAPI)
│   └── k8s/        Kubernetes manifests
├── diagram.jpg     Architecture diagram
└── README.md       This file
```

## Prerequisites

Install and configure before starting:

- [Pulumi CLI](https://www.pulumi.com/docs/install/)
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- `kubectl`
- `docker`
- `openssl`
- Python 3.12+
- An Azure subscription, with `az login` completed and the correct
  subscription selected (`az account show`)

---

## Part 1 — Bootstrap (`SetUp/`)

Creates the resource group, deploy identities with least-privilege custom
RBAC roles, Key Vault, and the Azure AD App Registration used for
application login.

### 1.1 Install dependencies

```bash
cd SetUp
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 1.2 Deploy

```bash
pulumi preview
pulumi up
```

Creates: resource group, admin and debug Service Principals, four custom
RBAC roles (network, database, ACR, AKS), Key Vault, and an Azure AD App
Registration with two App Roles (`Admin`, `Viewer`). Typically completes in
under 2 minutes.

The App Registration's OAuth2 redirect URI depends on Application
Gateway's public IP, which doesn't exist yet — it's set to a placeholder
for now and updated in Part 2, step 2.3.

### 1.3 Retrieve outputs you'll need later

```bash
pulumi stack output key_vault_name
pulumi stack output app_client_id
```

---

## Part 2 — Application infrastructure (`Deploy/`)

Creates the network, database, container registry, Kubernetes cluster,
ingress, and monitoring; then deploys the application onto it.

### 2.1 Install dependencies and configure

```bash
cd ../Deploy
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

pulumi config set --secret db_admin_password 'YourStrongPasswordHere'
pulumi config set azure-native:resourceProviderRegistrations all
```

**Remember the database password exactly** — it's used again in step 2.5
for a Kubernetes Secret, in a separate manual command with no automatic
sync. Always re-read it with `pulumi config get db_admin_password` rather
than retyping from memory.

Set placeholder AKS node IPs (real values aren't known until the cluster
exists — corrected in step 2.6):

```bash
pulumi config set app_backend_ip_1 10.0.2.4
pulumi config set app_backend_ip_2 10.0.2.5
```

Generate a self-signed TLS certificate for Application Gateway. This is
required because Azure AD only accepts HTTPS redirect URIs:

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=bigproject"
openssl pkcs12 -export -out cert.pfx -inkey key.pem -in cert.pem -passout pass:CertPass123!
base64 -w0 cert.pfx | pulumi config set --secret appgw_ssl_cert_data
pulumi config set --secret appgw_ssl_cert_password 'CertPass123!'
```

### 2.2 Provision the infrastructure

```bash
pulumi preview
pulumi up
```

Creates the VNet, four subnets, Network Security Groups, Postgres (primary
+ read replica), Azure Container Registry, AKS cluster, Application
Gateway (HTTP + HTTPS), and the Log Analytics Workspace with diagnostic
settings. This is the longest step — typically 25–30 minutes, dominated by
Postgres and AKS provisioning.

If this fails partway with `Code="ServerIsBusy"` on a Postgres
`Configuration` resource, or with `SubscriptionNotRegistered` on a resource
provider (e.g. `Microsoft.Insights`), simply re-run `pulumi up` — both are
transient and resolve on retry (the latter may need
`az provider register --namespace <provider-name>` first if it persists).

### 2.3 Update the Azure AD redirect URI with the real public IP

```bash
pulumi stack output appgw_public_ip
cd ../SetUp
pulumi config set appgw_public_ip $(cd ../Deploy && pulumi stack output appgw_public_ip)
pulumi up
cd ../Deploy
```

Updates the existing Azure AD Application in place with the real
Application Gateway address — no need to recreate it or its secret.

### 2.4 Build and publish the application image

```bash
cd app
az acr login --name bigprojectacr
docker build -t bigprojectacr.azurecr.io/bigproject-app:latest .
docker push bigprojectacr.azurecr.io/bigproject-app:latest
cd ..
```

### 2.5 Connect to the cluster and create secrets

```bash
az aks get-credentials --resource-group bigproject-rg --name bigproject-aks
kubectl get nodes -o wide
```

Note the two node IPs (`INTERNAL-IP` column) — confirm they match
`app_backend_ip_1` / `app_backend_ip_2` from step 2.1; if not, this is
corrected in step 2.7.

Database credentials — read the real value from Pulumi, never retype from
memory:

```bash
pulumi config get db_admin_password
kubectl create secret generic db-credentials \
  --from-literal=password='<paste-the-exact-value-from-above>'
```

Azure AD application credentials:

```bash
az keyvault secret show --vault-name $(cd ../SetUp && pulumi stack output key_vault_name) --name app-client-secret --query value -o tsv
kubectl create secret generic aad-credentials \
  --from-literal=client-secret='<paste-the-exact-value-from-above>'
```

### 2.6 Deploy the application

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

**Expect `CrashLoopBackOff` here — this is normal on first deployment**,
with logs (`kubectl logs -l app=bigproject-app --tail=20`) showing:

```
psycopg2.OperationalError: SSL connection has been closed unexpectedly
```

This happens because TimescaleDB's `shared_preload_libraries` setting only
takes effect after a Postgres restart, which Pulumi cannot trigger
automatically. Fix, once per fresh deployment:

```bash
az postgres flexible-server restart --resource-group bigproject-rg --name bigproject-pg-server
az postgres flexible-server show --resource-group bigproject-rg --name bigproject-pg-server --query state -o tsv
# wait for "Ready", typically 2–5 minutes
kubectl delete pod -l app=bigproject-app
kubectl get pods -o wide -w
```

Pods should reach `1/1 Running` within about 15 seconds of the restart
completing.

If instead the logs show `FATAL: password authentication failed for user
"pgadmin"`, the `db-credentials` secret doesn't match Postgres's actual
password — re-read it with `pulumi config get db_admin_password` and
recreate the secret as in step 2.5.

### 2.7 Reconcile node IPs with Application Gateway

Only needed if the node IPs noted in step 2.5 differ from
`app_backend_ip_1` / `app_backend_ip_2`:

```bash
pulumi config set app_backend_ip_1 <real-node-1-ip>
pulumi config set app_backend_ip_2 <real-node-2-ip>
pulumi up
```

### 2.8 Verify

In-cluster:

```bash
kubectl run curl-test --image=curlimages/curl:latest --rm -it --restart=Never -- sh
curl http://bigproject-app-service/health
curl http://bigproject-app-service/
curl http://bigproject-app-service/sensors
```

Public path:

```bash
pulumi stack output appgw_public_ip
curl -k https://<ip>/health
curl -k https://<ip>/
```

The login flow requires a real browser (interactive Microsoft sign-in
can't be tested with `curl`). Navigate to:

```
https://<appgw_public_ip>/login
```

Accept the self-signed certificate warning, sign in, and confirm redirect
to `/sensors` with role-appropriate data. New users default to the
`Viewer` role.

### 2.9 (Optional) Grant a user the Admin role

```bash
az ad user list --query "[].{displayName:displayName, userPrincipalName:userPrincipalName}" -o table
az ad user show --id "<upn-from-above>" --query id -o tsv
az ad sp show --id $(cd SetUp && pulumi stack output app_client_id) --query id -o tsv

az rest --method POST \
  --uri "https://graph.microsoft.com/v1.0/users/<user-object-id>/appRoleAssignments" \
  --body '{
    "principalId": "<user-object-id>",
    "resourceId": "<service-principal-object-id>",
    "appRoleId": "1b4f816e-5eaf-4ce5-9b47-4a1a1b1a0001"
  }'
```

Log out and back in to the application for the new role to take effect —
it's embedded in the ID token at login time, not re-checked per request.

---

## Tearing down

```bash
cd Deploy
pulumi destroy
cd ../SetUp
pulumi destroy
```

If `pulumi destroy` in `Deploy/` fails on `shared-preload-libraries-config`
with `Code="InvalidParameterValue"` (a known Azure provider bug on delete),
remove it from Pulumi state directly — the underlying Azure setting is
deleted automatically along with the parent Postgres server regardless:

```bash
pulumi stack export | grep -A2 "shared-preload-libraries-config"
pulumi state delete '<urn-from-above>'
pulumi destroy
```

Temporary debugging jumpboxes (Container Instances, if used) and
soft-deleted Key Vaults are not removed by `pulumi destroy` — clean those
up separately if needed:

```bash
az container list --resource-group bigproject-rg -o table
az keyvault list-deleted --output table
```

## Notable engineering decisions

- **AKS over Azure Container Apps** for the compute layer — chosen for
  closer alignment with production Kubernetes practice, including explicit
  control over scheduling behavior (pod anti-affinity) and networking.
- **Application Gateway targets AKS nodes directly on a fixed NodePort**,
  bypassing the AKS-managed internal Load Balancer — a deliberate decision
  made after isolating a real, reproducible issue where that Load
  Balancer's Direct Server Return configuration did not reliably serve
  Application Gateway's cross-subnet traffic. Node IPs are not guaranteed
  stable across node replacement or scaling; a dynamic node pool would use
  AGIC (Application Gateway Ingress Controller) instead.
- **Custom RBAC roles built incrementally**, one per Azure resource type,
  rather than a single broad Contributor grant for the deploying identity.
- **Two independent Pulumi stacks** (`SetUp/`, `Deploy/`) so foundational
  identity/secrets infrastructure can persist independently of the more
  frequently-iterated application infrastructure.
- **Postgres `Configuration` resources are applied sequentially**
  (explicit `depends_on` chain), since concurrent application of
  `azure.extensions` and `shared_preload_libraries` against the same
  server intermittently fails with `Code="ServerIsBusy"`.

## License

Personal portfolio / learning project. No license is implied for
production use.
