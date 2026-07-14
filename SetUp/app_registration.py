import pulumi
import pulumi_azuread as azuread


def create_app_registration(redirect_uri: str):
    app_registration = azuread.Application(
        "bigproject-app-registration",
        display_name="bigproject-app-login",
        sign_in_audience="AzureADMyOrg",
        web=azuread.ApplicationWebArgs(
            redirect_uris=[redirect_uri],
            implicit_grant=azuread.ApplicationWebImplicitGrantArgs(
                access_token_issuance_enabled=False,
                id_token_issuance_enabled=True,
            ),
        ),
        app_roles=[
            azuread.ApplicationAppRoleArgs(
                id="1b4f816e-5eaf-4ce5-9b47-4a1a1b1a0001",
                allowed_member_types=["User"],
                description="Full access, including sensor data and admin views.",
                display_name="Admin",
                value="Admin",
            ),
            azuread.ApplicationAppRoleArgs(
                id="1b4f816e-5eaf-4ce5-9b47-4a1a1b1a0002",
                allowed_member_types=["User"],
                description="Read-only access to sensor dashboards.",
                display_name="Viewer",
                value="Viewer",
            ),
        ],
    )

    app_password = azuread.ApplicationPassword(
        "bigproject-app-registration-secret",
        application_id=app_registration.id,
    )

    service_principal = azuread.ServicePrincipal(
        "bigproject-app-registration-sp",
        client_id=app_registration.client_id,
    )

    return {
        "client_id": app_registration.client_id,
        "client_secret": app_password.value,
        "object_id": app_registration.object_id,
        "service_principal_id": service_principal.id,
    }
