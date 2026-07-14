import pulumi
import pulumi_azure_native as azure_native
import pulumi_azuread as azuread

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}


def create_key_vault(resource_group_name: str, location: str, tenant_id: str, subscription_id: str):
    current_user = azuread.get_client_config()

    vault = azure_native.keyvault.Vault(
        "bigproject-kv",
        resource_group_name=resource_group_name,
        location=location,
        tags=TAGS,
        properties=azure_native.keyvault.VaultPropertiesArgs(
            sku=azure_native.keyvault.SkuArgs(
                family=azure_native.keyvault.SkuFamily.A,
                name=azure_native.keyvault.SkuName.STANDARD,
            ),
            tenant_id=tenant_id,
            enable_rbac_authorization=True,
        ),
    )

    azure_native.authorization.RoleAssignment(
        "kv-secrets-officer-you",
        principal_id=current_user.object_id,
        principal_type="User",
        role_definition_id=f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/b86a8fe4-44ce-4948-aee5-eccb2c155cd7",
        scope=vault.id,
    )

    return vault


def store_secret(resource_group_name: str, vault_name, secret_name: str, secret_value: pulumi.Output, resource_name: str):
    return azure_native.keyvault.Secret(
        resource_name,
        resource_group_name=resource_group_name,
        vault_name=vault_name,
        secret_name=secret_name,
        properties=azure_native.keyvault.SecretPropertiesArgs(
            value=secret_value,
        ),
    )