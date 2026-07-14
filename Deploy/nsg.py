import pulumi
import pulumi_azure_native as azure_native

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}


def create_nsgs(resource_group_name: str, location: str):
    public_nsg = azure_native.network.NetworkSecurityGroup(
        "public-nsg",
        resource_group_name=resource_group_name,
        location=location,
        network_security_group_name="public-nsg",
        tags=TAGS,
        security_rules=[
            azure_native.network.SecurityRuleArgs(
                name="allow-https-inbound",
                priority=100,
                direction="Inbound",
                access="Allow",
                protocol="Tcp",
                source_port_range="*",
                destination_port_range="443",
                source_address_prefix="Internet",
                destination_address_prefix="*",
            ),
            azure_native.network.SecurityRuleArgs(
                name="allow-http-inbound",
                priority=110,
                direction="Inbound",
                access="Allow",
                protocol="Tcp",
                source_port_range="*",
                destination_port_range="80",
                source_address_prefix="Internet",
                destination_address_prefix="*",
            ),
            azure_native.network.SecurityRuleArgs(
                name="allow-gateway-manager",
                priority=120,
                direction="Inbound",
                access="Allow",
                protocol="Tcp",
                source_port_range="*",
                destination_port_range="65200-65535",
                source_address_prefix="GatewayManager",
                destination_address_prefix="*",
            ),
        ],
    )

    app_nsg = azure_native.network.NetworkSecurityGroup(
        "app-nsg",
        resource_group_name=resource_group_name,
        location=location,
        network_security_group_name="app-nsg",
        tags=TAGS,
        security_rules=[
            azure_native.network.SecurityRuleArgs(
                name="allow-from-public-subnet",
                priority=100,
                direction="Inbound",
                access="Allow",
                protocol="Tcp",
                source_port_range="*",
                destination_port_range="8000",
                source_address_prefix="10.0.1.0/24",
                destination_address_prefix="*",
            ),
            # Explicit allow for the fixed NodePort used by App Gateway's
            # direct-to-node backend pool (bypassing the internal Load
            # Balancer, which has an unresolved cross-subnet health probe
            # issue with AKS's Standard LB + floating IP/DSR). Without this
            # explicit rule, traffic on 32665 only works via Azure's default
            # AllowVnetInBound fallback, which is broader than intended.
            azure_native.network.SecurityRuleArgs(
                name="allow-nodeport-from-public-subnet",
                priority=105,
                direction="Inbound",
                access="Allow",
                protocol="Tcp",
                source_port_range="*",
                destination_port_range="32665",
                source_address_prefix="10.0.1.0/24",
                destination_address_prefix="*",
            ),
            azure_native.network.SecurityRuleArgs(
                name="deny-internet-inbound",
                priority=4000,
                direction="Inbound",
                access="Deny",
                protocol="*",
                source_port_range="*",
                destination_port_range="*",
                source_address_prefix="Internet",
                destination_address_prefix="*",
            ),
        ],
    )

    db_nsg = azure_native.network.NetworkSecurityGroup(
        "db-nsg",
        resource_group_name=resource_group_name,
        location=location,
        network_security_group_name="db-nsg",
        tags=TAGS,
        security_rules=[
            azure_native.network.SecurityRuleArgs(
                name="allow-postgres-from-app-subnet",
                priority=100,
                direction="Inbound",
                access="Allow",
                protocol="Tcp",
                source_port_range="*",
                destination_port_range="5432",
                source_address_prefix="10.0.2.0/24",
                destination_address_prefix="*",
            ),
            azure_native.network.SecurityRuleArgs(
                name="allow-postgres-within-db-subnet",
                priority=105,
                direction="Inbound",
                access="Allow",
                protocol="Tcp",
                source_port_range="*",
                destination_port_range="5432",
                source_address_prefix="10.0.3.0/24",
                destination_address_prefix="*",
            ),
            azure_native.network.SecurityRuleArgs(
                name="allow-postgres-from-admin-subnet",
                priority=110,
                direction="Inbound",
                access="Allow",
                protocol="Tcp",
                source_port_range="*",
                destination_port_range="5432",
                source_address_prefix="10.0.4.0/28",
                destination_address_prefix="*",
            ),
            azure_native.network.SecurityRuleArgs(
                name="deny-all-other-inbound",
                priority=4000,
                direction="Inbound",
                access="Deny",
                protocol="*",
                source_port_range="*",
                destination_port_range="*",
                source_address_prefix="*",
                destination_address_prefix="*",
            ),
        ],
    )

    admin_nsg = azure_native.network.NetworkSecurityGroup(
        "admin-nsg",
        resource_group_name=resource_group_name,
        location=location,
        network_security_group_name="admin-nsg",
        tags=TAGS,
        security_rules=[
            azure_native.network.SecurityRuleArgs(
                name="deny-all-inbound",
                priority=4000,
                direction="Inbound",
                access="Deny",
                protocol="*",
                source_port_range="*",
                destination_port_range="*",
                source_address_prefix="*",
                destination_address_prefix="*",
            ),
        ],
    )

    return {
        "public_nsg": public_nsg,
        "app_nsg": app_nsg,
        "db_nsg": db_nsg,
        "admin_nsg": admin_nsg,
    }
