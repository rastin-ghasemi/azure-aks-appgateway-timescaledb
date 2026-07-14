import pulumi
import pulumi_azure_native as azure_native

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}


def create_aks_cluster(resource_group_name: str, location: str, subnet_id, acr_id, vnet_id, subscription_id):
    cluster = azure_native.containerservice.ManagedCluster(
        "bigproject-aks",
        resource_group_name=resource_group_name,
        resource_name_="bigproject-aks",
        location=location,
        tags=TAGS,
        dns_prefix="bigprojectaks",
        sku=azure_native.containerservice.ManagedClusterSKUArgs(
            name="Base",
            tier="Standard",
        ),
        identity=azure_native.containerservice.ManagedClusterIdentityArgs(
            type="SystemAssigned",
        ),
        agent_pool_profiles=[
            azure_native.containerservice.ManagedClusterAgentPoolProfileArgs(
                name="systempool",
                count=2,
                vm_size="Standard_D2s_v3",
                os_type="Linux",
                mode="System",
                vnet_subnet_id=subnet_id,
                max_pods=30,
            )
        ],
        network_profile=azure_native.containerservice.ContainerServiceNetworkProfileArgs(
            network_plugin="azure",
            network_plugin_mode="overlay",
            service_cidr="10.100.0.0/16",
            dns_service_ip="10.100.0.10",
        ),
    )

    kubelet_identity_object_id = cluster.identity_profile.apply(
        lambda profile: profile["kubeletidentity"].object_id if profile else None
    )

    azure_native.authorization.RoleAssignment(
        "aks-acr-pull",
        principal_id=kubelet_identity_object_id,
        principal_type="ServicePrincipal",
        role_definition_id="/providers/Microsoft.Authorization/roleDefinitions/7f951dda-4ed3-4680-a7ca-43fe172d538d",
        scope=acr_id,
    )

    # AKS's own cluster identity (its cloud-provider component) needs
    # Network Contributor on the VNet, since we brought our own VNet
    # rather than letting AKS create/manage it. Without this, the
    # in-cluster Azure cloud provider can't read subnets or create
    # internal Load Balancers — required for the internal LB Service
    # fronting the app.
    azure_native.authorization.RoleAssignment(
        "aks-network-contributor",
        principal_id=cluster.identity.apply(lambda i: i.principal_id if i else None),
        principal_type="ServicePrincipal",
        # Network Contributor built-in role
        role_definition_id=f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/4d97b98b-1d4f-4787-a291-c67834d212e7",
        scope=vnet_id,
    )

    return cluster
