import pulumi
import pulumi_azure_native as azure_native

# Fixed GUID for this custom role — must stay the same across deploys
# so Pulumi/Azure recognize it as the same role, not a new one each time.
NETWORK_ADMIN_ROLE_ID = "8f3b7e21-9c4a-4d5e-b1f0-6a2c9d4e7b10"


def create_network_admin_role(subscription_id: str, resource_group_id: str):
    role = azure_native.authorization.RoleDefinition(
        "network-admin-role",
        role_definition_id=NETWORK_ADMIN_ROLE_ID,
        role_name="BigProject VNet Admin",
        description="Can create and modify VNets and subnets only. Expand as new resource types are added.",
        scope=resource_group_id,
        permissions=[
            azure_native.authorization.PermissionArgs(
                actions=[
                    "Microsoft.Network/virtualNetworks/read",
                    "Microsoft.Network/virtualNetworks/write",
                    "Microsoft.Network/virtualNetworks/delete",
                    "Microsoft.Network/virtualNetworks/subnets/read",
                    "Microsoft.Network/virtualNetworks/subnets/write",
                    "Microsoft.Network/virtualNetworks/subnets/delete",
                    "Microsoft.Network/virtualNetworks/subnets/join/action",
                    "Microsoft.Network/locations/operations/read",
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
