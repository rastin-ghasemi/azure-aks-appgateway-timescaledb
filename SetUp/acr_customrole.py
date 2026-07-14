import pulumi
import pulumi_azure_native as azure_native

ACR_ADMIN_ROLE_ID = "5d2c8a17-4e9b-4c1a-8f3d-2b7e6a1c9d05"


def create_acr_admin_role(subscription_id: str, resource_group_id: str):
    role = azure_native.authorization.RoleDefinition(
        "acr-admin-role",
        role_definition_id=ACR_ADMIN_ROLE_ID,
        role_name="BigProject ACR Admin",
        description="Can create and manage the Azure Container Registry only.",
        scope=resource_group_id,
        permissions=[
            azure_native.authorization.PermissionArgs(
                actions=[
                    "Microsoft.ContainerRegistry/registries/read",
                    "Microsoft.ContainerRegistry/registries/write",
                    "Microsoft.ContainerRegistry/registries/delete",
                    "Microsoft.ContainerRegistry/registries/listCredentials/action",
                    "Microsoft.Resources/subscriptions/resourceGroups/read",
                ],
                not_actions=[],
                data_actions=[],
                not_data_actions=[],
            )
        ],
        assignable_scopes=[resource_group_id],
    )
    return role
