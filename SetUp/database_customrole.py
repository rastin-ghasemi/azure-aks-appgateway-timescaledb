import pulumi
import pulumi_azure_native as azure_native

# Fixed GUID for this custom role — must stay the same across deploys
DATABASE_ADMIN_ROLE_ID = "3e9f1a44-7b2c-4e6d-9a1f-5c8b3d2e9f01"


def create_database_admin_role(subscription_id: str, resource_group_id: str):
    role = azure_native.authorization.RoleDefinition(
        "database-admin-role",
        role_definition_id=DATABASE_ADMIN_ROLE_ID,
        role_name="BigProject Database Admin",
        description="Can create and modify Postgres Flexible Server and its required Private DNS Zone.",
        scope=resource_group_id,
        permissions=[
            azure_native.authorization.PermissionArgs(
                actions=[
                    "Microsoft.DBforPostgreSQL/flexibleServers/read",
                    "Microsoft.DBforPostgreSQL/flexibleServers/write",
                    "Microsoft.DBforPostgreSQL/flexibleServers/delete",
                    "Microsoft.DBforPostgreSQL/flexibleServers/databases/read",
                    "Microsoft.DBforPostgreSQL/flexibleServers/databases/write",
                    "Microsoft.DBforPostgreSQL/flexibleServers/databases/delete",
                    # Postgres Flexible Server with VNet integration requires a
                    # Private DNS Zone — these actions let it create/link one.
                    "Microsoft.Network/privateDnsZones/read",
                    "Microsoft.Network/privateDnsZones/write",
                    "Microsoft.Network/privateDnsZones/delete",
                    "Microsoft.Network/privateDnsZones/virtualNetworkLinks/read",
                    "Microsoft.Network/privateDnsZones/virtualNetworkLinks/write",
                    "Microsoft.Network/privateDnsZones/virtualNetworkLinks/delete",
                    "Microsoft.Network/virtualNetworks/subnets/join/action",
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
