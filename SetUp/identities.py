import datetime
import pulumi
import pulumi_azuread as azuread
import pulumi_azure_native as azure_native

TAGS = ["project:bigproject", "managed-by:pulumi", "environment:dev"]


def create_identities(resource_group_id: str, subscription_id: str, network_role, database_role, acr_role, aks_role):
    expiry = (datetime.datetime.utcnow() + datetime.timedelta(days=90)).isoformat() + "Z"

    # --- Admin identity: scoped, resource-specific permissions only ---
    admin_app = azuread.Application(
        "admin-app", display_name="bigproject-admin", tags=TAGS
    )
    admin_sp = azuread.ServicePrincipal("admin-sp", client_id=admin_app.client_id)
    admin_sp_password = azuread.ServicePrincipalPassword(
        "admin-sp-password",
        service_principal_id=admin_sp.id,
        end_date=expiry,
    )

    azure_native.authorization.RoleAssignment(
        "admin-network-role-assignment",
        principal_id=admin_sp.object_id,
        principal_type="ServicePrincipal",
        role_definition_id=network_role.id,
        scope=resource_group_id,
    )

    azure_native.authorization.RoleAssignment(
        "admin-database-role-assignment",
        principal_id=admin_sp.object_id,
        principal_type="ServicePrincipal",
        role_definition_id=database_role.id,
        scope=resource_group_id,
    )

    azure_native.authorization.RoleAssignment(
        "admin-acr-role-assignment",
        principal_id=admin_sp.object_id,
        principal_type="ServicePrincipal",
        role_definition_id=acr_role.id,
        scope=resource_group_id,
    )

    azure_native.authorization.RoleAssignment(
        "admin-aks-role-assignment",
        principal_id=admin_sp.object_id,
        principal_type="ServicePrincipal",
        role_definition_id=aks_role.id,
        scope=resource_group_id,
    )

    # --- Debug identity: read-only on logs/monitoring in the RG ---
    debug_app = azuread.Application(
        "debug-app", display_name="bigproject-debug-reader", tags=TAGS
    )
    debug_sp = azuread.ServicePrincipal("debug-sp", client_id=debug_app.client_id)
    debug_sp_password = azuread.ServicePrincipalPassword(
        "debug-sp-password",
        service_principal_id=debug_sp.id,
        end_date=expiry,
    )

    azure_native.authorization.RoleAssignment(
        "debug-role-assignment",
        principal_id=debug_sp.object_id,
        principal_type="ServicePrincipal",
        role_definition_id=f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/43d0d8ad-25c7-4714-9337-8ba259a9fe05",
        scope=resource_group_id,
    )

    return {
        "admin_client_id": admin_app.client_id,
        "admin_client_secret": admin_sp_password.value,
        "admin_object_id": admin_sp.object_id,
        "debug_client_id": debug_app.client_id,
        "debug_client_secret": debug_sp_password.value,
        "debug_object_id": debug_sp.object_id,
    }
