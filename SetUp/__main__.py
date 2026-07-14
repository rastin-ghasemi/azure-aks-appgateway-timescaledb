"""Bootstrap: Resource Group + admin/debug identities + Key Vault + App Registration"""
import pulumi
import pulumi_azure_native as azure_native
from identities import create_identities
from key_vault import create_key_vault, store_secret
from network_customrole import create_network_admin_role
from database_customrole import create_database_admin_role
from acr_customrole import create_acr_admin_role
from aks_customrole import create_aks_admin_role
from app_registration import create_app_registration

location = "westus2"

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}

resource_group = azure_native.resources.ResourceGroup(
    "bigproject-rg",
    resource_group_name="bigproject-rg",
    location=location,
    tags=TAGS,
)

client_config = azure_native.authorization.get_client_config()
subscription_id = client_config.subscription_id
tenant_id = client_config.tenant_id

network_role = create_network_admin_role(subscription_id, resource_group.id)
database_role = create_database_admin_role(subscription_id, resource_group.id)
acr_role = create_acr_admin_role(subscription_id, resource_group.id)
aks_role = create_aks_admin_role(subscription_id, resource_group.id)

creds = create_identities(resource_group.id, subscription_id, network_role, database_role, acr_role, aks_role)

vault = create_key_vault(resource_group.name, location, tenant_id, subscription_id)

store_secret(resource_group.name, vault.name, "admin-client-secret", creds["admin_client_secret"], "admin-secret-kv")
store_secret(resource_group.name, vault.name, "debug-client-secret", creds["debug_client_secret"], "debug-secret-kv")

# --- Azure AD App Registration for end-user login to the web app ---
# The redirect URI depends on Application Gateway's public IP, which only
# exists after Deploy/ has been applied at least once. Rather than
# hardcoding it, read it from Pulumi config — update with:
#   pulumi config set appgw_public_ip <ip>
# or, chained directly from Deploy/'s own output:
#   pulumi config set appgw_public_ip $(cd ../Deploy && pulumi stack output appgw_public_ip)
config = pulumi.Config()
appgw_public_ip = config.get("appgw_public_ip") or "0.0.0.0"  # placeholder until Deploy/ exists
redirect_uri = f"https://{appgw_public_ip}/auth/callback"

app_reg = create_app_registration(redirect_uri=redirect_uri)

store_secret(resource_group.name, vault.name, "app-client-secret", app_reg["client_secret"], "app-secret-kv")

pulumi.export("resource_group_name", resource_group.name)
pulumi.export("key_vault_name", vault.name)
pulumi.export("admin_client_id", creds["admin_client_id"])
pulumi.export("debug_client_id", creds["debug_client_id"])
pulumi.export("tenant_id", tenant_id)
pulumi.export("subscription_id", subscription_id)
pulumi.export("app_client_id", app_reg["client_id"])
pulumi.export("app_redirect_uri", redirect_uri)
