import pulumi
import pulumi_azure_native as azure_native

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}


def create_container_app(
    resource_group_name: str,
    location: str,
    app_subnet_id,
    acr_login_server,
    acr_name: str,
    db_host: str,
    db_user: str,
    db_password: pulumi.Output,
):
    environment = azure_native.app.ManagedEnvironment(
        "bigproject-env",
        resource_group_name=resource_group_name,
        environment_name="bigproject-env",
        location=location,
        tags=TAGS,
        vnet_configuration=azure_native.app.VnetConfigurationArgs(
            infrastructure_subnet_id=app_subnet_id,
            internal=True,
        ),
    )

    acr_creds = azure_native.containerregistry.list_registry_credentials_output(
        resource_group_name=resource_group_name,
        registry_name=acr_name,
    )
    acr_username = acr_creds.username
    acr_password = acr_creds.passwords[0].value

    container_app = azure_native.app.ContainerApp(
        "bigproject-app",
        resource_group_name=resource_group_name,
        container_app_name="bigproject-app",
        location=location,
        tags=TAGS,
        managed_environment_id=environment.id,
        configuration=azure_native.app.ConfigurationArgs(
            ingress=azure_native.app.IngressArgs(
                external=False,
                target_port=8000,
            ),
            registries=[
                azure_native.app.RegistryCredentialsArgs(
                    server=acr_login_server,
                    username=acr_username,
                    password_secret_ref="acr-password",
                )
            ],
            secrets=[
                azure_native.app.SecretArgs(name="acr-password", value=acr_password),
                azure_native.app.SecretArgs(name="db-password", value=db_password),
            ],
        ),
        template=azure_native.app.TemplateArgs(
            containers=[
                azure_native.app.ContainerArgs(
                    name="bigproject-app",
                    image=acr_login_server.apply(lambda server: f"{server}/bigproject-app:latest"),
                    env=[
                        azure_native.app.EnvironmentVarArgs(name="DB_HOST", value=db_host),
                        azure_native.app.EnvironmentVarArgs(name="DB_USER", value=db_user),
                        azure_native.app.EnvironmentVarArgs(
                            name="DB_PASSWORD", secret_ref="db-password"
                        ),
                        azure_native.app.EnvironmentVarArgs(name="DB_NAME", value="postgres"),
                    ],
                    resources=azure_native.app.ContainerResourcesArgs(
                        cpu=0.5,
                        memory="1.0Gi",
                    ),
                )
            ],
            scale=azure_native.app.ScaleArgs(min_replicas=1, max_replicas=1),
        ),
    )

    return environment, container_app
