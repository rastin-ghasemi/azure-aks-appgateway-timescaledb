import pulumi
import pulumi_azure_native as azure_native

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}


def create_acr(resource_group_name: str, location: str):
    registry = azure_native.containerregistry.Registry(
        "bigproject-acr",
        resource_group_name=resource_group_name,
        registry_name="bigprojectacr",  # must be globally unique, alphanumeric only, no dashes
        location=location,
        tags=TAGS,
        sku=azure_native.containerregistry.SkuArgs(
            name="Basic",  # cheapest tier, fine for a demo
        ),
        admin_user_enabled=True,  # lets us `docker login` with username/password for now
    )
    return registry
