import pulumi
import pulumi_azure_native as azure_native

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}


def create_network(resource_group_name: str, location: str, nsgs: dict):
    vnet = azure_native.network.VirtualNetwork(
        "main-vnet",
        resource_group_name=resource_group_name,
        location=location,
        virtual_network_name="bigproject-vnet",
        tags=TAGS,
        address_space=azure_native.network.AddressSpaceArgs(
            address_prefixes=["10.0.0.0/16"]
        ),
    )

    public_subnet = azure_native.network.Subnet(
        "public-subnet",
        resource_group_name=resource_group_name,
        virtual_network_name=vnet.name,
        subnet_name="public-subnet",
        address_prefix="10.0.1.0/24",
        network_security_group=azure_native.network.NetworkSecurityGroupArgs(
            id=nsgs["public_nsg"].id
        ),
    )

    # Still delegated to Container Apps for now — will be updated to AKS
    # (delegation removed) in a follow-up pulumi up, separately from any
    # resource deletion, per the sequencing note in the README.
    private_app_subnet = azure_native.network.Subnet(
        "private-app-subnet",
        resource_group_name=resource_group_name,
        virtual_network_name=vnet.name,
        subnet_name="private-app-subnet",
        address_prefix="10.0.2.0/24",
        network_security_group=azure_native.network.NetworkSecurityGroupArgs(
            id=nsgs["app_nsg"].id
        ),
    )

    private_db_subnet = azure_native.network.Subnet(
        "private-db-subnet",
        resource_group_name=resource_group_name,
        virtual_network_name=vnet.name,
        subnet_name="private-db-subnet",
        address_prefix="10.0.3.0/24",
        delegations=[
            azure_native.network.DelegationArgs(
                name="postgres-delegation",
                service_name="Microsoft.DBforPostgreSQL/flexibleServers",
            )
        ],
        network_security_group=azure_native.network.NetworkSecurityGroupArgs(
            id=nsgs["db_nsg"].id
        ),
    )

    admin_subnet = azure_native.network.Subnet(
        "admin-subnet",
        resource_group_name=resource_group_name,
        virtual_network_name=vnet.name,
        subnet_name="admin-subnet",
        address_prefix="10.0.4.0/28",
        delegations=[
            azure_native.network.DelegationArgs(
                name="aci-delegation",
                service_name="Microsoft.ContainerInstance/containerGroups",
            )
        ],
        network_security_group=azure_native.network.NetworkSecurityGroupArgs(
            id=nsgs["admin_nsg"].id
        ),
    )

    return {
        "vnet": vnet,
        "public_subnet": public_subnet,
        "private_app_subnet": private_app_subnet,
        "private_db_subnet": private_db_subnet,
        "admin_subnet": admin_subnet,
    }
