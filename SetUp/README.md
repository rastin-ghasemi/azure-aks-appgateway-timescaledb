# BigProject — Azure Bootstrap (SetUp)

## Overview

Bootstrap layer for BigProject's Azure infrastructure, built with Pulumi
(Python). This is the Azure equivalent of an AWS/Terraform `SetUp/` layer —
it creates the foundational resources that `../Deploy/` depends on, deployed
and destroyed independently for safety and cost control.

This stack must be deployed **before** `../Deploy/`, since `Deploy/` reads
several of its outputs via `pulumi.StackReference`.

## What this creates

| Resource | Purpose |
|---|---|
| Resource Group (`bigproject-rg`) | Container for all project resources |
| Admin Service Principal | Used by Pulumi to deploy `Deploy/`. Scoped via custom RBAC roles (below), not broad Contributor access |
| Debug Service Principal | Read-only (Monitoring Reader) — for safely inspecting logs without deploy/modify access |
| Custom RBAC roles | One per resource type (network, database, ACR, AKS), each granting only the specific actions needed — built incrementally as the project grew |
| Key Vault | Stores both Service Principals' secrets, never printed to terminal |
| **Azure AD App Registration** | A separate identity — not for infrastructure deployment, but for **end users logging into the deployed web application** |

## Two distinct identity concerns — do not conflate them

This stack manages two unrelated categories of identity, both built on
Azure AD but serving different purposes:

1. **Infrastructure deploy identities** (admin/debug Service Principals +
   custom roles) — control what *Pulumi itself* is allowed to do when
   provisioning Azure resources. Scoped narrowly, one role per resource
   type, expanded only as new resource types are introduced.
2. **Application login identity** (the App Registration) — controls who can
   *log into the web application* once it's running, and what they see
   based on their assigned App Role (`Admin` or `Viewer`). This has no
   relationship to infrastructure permissions and should not be merged with
   category 1's roles.

## Prerequisites

- [Pulumi CLI](https://www.pulumi.com/docs/install/) installed
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
- Logged in: `az login`
- Correct subscription selected: `az account show`
- Python 3.12+

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
pulumi preview   # like terraform plan
pulumi up        # deploy
pulumi destroy   # tear down — do this at the end of each work session
```

## Azure AD App Registration — redirect URI dependency

The App Registration requires a fixed OAuth2 redirect URI at creation time
(`app_registration.py`, currently hardcoded to
`https://<application-gateway-public-ip>/auth/callback`).

**On a fresh deployment, Application Gateway's public IP is not known until
`../Deploy/` has been applied at least once** — but `SetUp/` is deployed
*before* `Deploy/`. This is a genuine chicken-and-egg dependency. Handle it
in one of two ways:

1. **Deploy `SetUp/` once with a placeholder redirect URI**, deploy
   `Deploy/` to get the real Application Gateway public IP, then update
   `app_registration.py`'s `redirect_uri` argument with the real IP and
   re-run `pulumi up` in `SetUp/` (Azure AD apps can be updated in place;
   this does not require deleting and recreating the app or its secret).
2. **If the public IP is already known from a previous deployment** (Static
   SKU IPs can sometimes persist across a `Deploy/` destroy/recreate cycle,
   though this is not guaranteed), use it directly on the first pass.

Given Application Gateway's Public IP is provisioned with `Standard` SKU
and `Static` allocation, but is still destroyed and recreated on every
`pulumi destroy` / `pulumi up` cycle of `Deploy/`, **assume the IP changes
on every fresh rebuild** and plan for step 1 above as the normal path, not
an edge case.

## Retrieving secrets

Secrets are **not** exported to stdout or stack outputs — they live only in
Key Vault.

```bash
az keyvault secret list --vault-name <key_vault_name> --output table
az keyvault secret show --vault-name <key_vault_name> --name admin-client-secret --query value -o tsv
az keyvault secret show --vault-name <key_vault_name> --name debug-client-secret --query value -o tsv
az keyvault secret show --vault-name <key_vault_name> --name app-client-secret --query value -o tsv
```

Get the vault name from stack outputs:

```bash
pulumi stack output key_vault_name
```

The application login client ID (not secret — safe to reference directly)
is also exported:

```bash
pulumi stack output app_client_id
```

## Assigning users to App Roles

Newly registered users have no App Role by default (the application treats
unassigned users as `Viewer`, per its own fallback logic — see
`../Deploy/app/main.py`). To explicitly assign a user to `Admin`:

**1. Find the user's object ID.** For accounts added as guests (e.g.
personal Microsoft accounts), the UPN is not the plain email address — list
users to find the actual UPN format Azure AD assigned:

```bash
az ad user list --query "[].{displayName:displayName, userPrincipalName:userPrincipalName}" -o table
az ad user show --id "<upn-from-above>" --query id -o tsv
```

**2. Find the Enterprise Application's (Service Principal's) object ID:**

```bash
az ad sp show --id $(pulumi stack output app_client_id) --query id -o tsv
```

**3. Create the role assignment** via Microsoft Graph (no dedicated `az ad`
subcommand exists for this operation):

```bash
az rest --method POST \
  --uri "https://graph.microsoft.com/v1.0/users/<user-object-id>/appRoleAssignments" \
  --body '{
    "principalId": "<user-object-id>",
    "resourceId": "<service-principal-object-id>",
    "appRoleId": "1b4f816e-5eaf-4ce5-9b47-4a1a1b1a0001"
  }'
```

`appRoleId` values (fixed, defined in `app_registration.py`):
- Admin: `1b4f816e-5eaf-4ce5-9b47-4a1a1b1a0001`
- Viewer: `1b4f816e-5eaf-4ce5-9b47-4a1a1b1a0002`

The user must log out and log back in to the application for a new role
assignment to take effect — the role is embedded in the ID token issued at
login time, not checked live on every request.

## Security notes

- Both Service Principal secrets **expire after 90 days**.
- Admin SP is scoped to custom roles covering only network, database, ACR,
  and AKS actions — not subscription-wide or broad Contributor access.
- Debug SP is scoped to **Monitoring Reader** only.
- The App Registration's client secret is stored in Key Vault, never
  printed to terminal or committed to source control.
- All resources are tagged `project:bigproject`, `managed-by:pulumi`,
  `environment:dev`.
- This subscription is **pay-as-you-go with no trial credit** — a $10/year
  budget alert is configured as a backup tripwire. Always run `pulumi
  destroy` after each session.

## Known provider quirks

- **Secret expiry recalculates on every `pulumi up`.** `identities.py`
  computes `datetime.utcnow() + 90 days` at code-execution time rather than
  storing a fixed date, so both Service Principal passwords show as
  `replace` on every apply, even when nothing else changed. Cosmetic and
  harmless (new secrets are correctly written to Key Vault each time), but
  worth knowing so it isn't mistaken for an unintended change.
- **`azuread.Application`'s App Roles argument is `app_roles` (plural)**,
  not `app_role` — the singular form is accepted by some Terraform-derived
  documentation examples but rejected by this SDK version with
  `TypeError: unexpected keyword argument 'app_role'`.

## State

State is stored in Pulumi Cloud, not locally. No manual state file
management needed.

## Next step

See `../Deploy/` for the application infrastructure layer.
