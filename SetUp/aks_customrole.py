import pulumi
import pulumi_azure_native as azure_native

AKS_ADMIN_ROLE_ID = "9a1c3e77-2f5d-4b8a-b6e1-7d4f0c2a8e93"


def create_aks_admin_role(subscription_id: str, resource_group_id: str):
    role = azure_native.authorization.RoleDefinition(
        "aks-admin-role",
        role_definition_id=AKS_ADMIN_ROLE_ID,
        role_name="BigProject AKS Admin",
        description="Can create and manage the AKS cluster only.",
        scope=resource_group_id,
        permissions=[
            azure_native.authorization.PermissionArgs(
                actions=[
                    "Microsoft.ContainerService/managedClusters/read",
                    "Microsoft.ContainerService/managedClusters/write",
                    "Microsoft.ContainerService/managedClusters/delete",
                    "Microsoft.ContainerService/managedClusters/listClusterAdminCredential/action",
                    "Microsoft.ContainerService/managedClusters/listClusterUserCredential/action",
                    "Microsoft.Network/virtualNetworks/subnets/join/action",
                    "Microsoft.Authorization/roleAssignments/read",
                    "Microsoft.Authorization/roleAssignments/write",
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
