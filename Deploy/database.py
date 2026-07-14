import pulumi
import pulumi_azure_native as azure_native

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}


def create_database(resource_group_name: str, location: str, vnet_id, db_subnet_id, admin_password: pulumi.Output):
    dns_zone = azure_native.privatedns.PrivateZone(
        "postgres-dns-zone",
        resource_group_name=resource_group_name,
        location="global",
        private_zone_name="bigproject.postgres.database.azure.com",
        tags=TAGS,
    )

    dns_link = azure_native.privatedns.VirtualNetworkLink(
        "postgres-dns-link",
        resource_group_name=resource_group_name,
        private_zone_name=dns_zone.name,
        location="global",
        virtual_network=azure_native.privatedns.SubResourceArgs(id=vnet_id),
        registration_enabled=False,
    )

    # --- Primary server ---
    server = azure_native.dbforpostgresql.Server(
        "bigproject-pg",
        resource_group_name=resource_group_name,
        server_name="bigproject-pg-server",
        location=location,
        tags=TAGS,
        sku=azure_native.dbforpostgresql.SkuArgs(
            name="Standard_D2s_v3",
            tier="GeneralPurpose",
        ),
        version="16",
        administrator_login="pgadmin",
        administrator_login_password=admin_password,
        storage=azure_native.dbforpostgresql.StorageArgs(storage_size_gb=32),
        network=azure_native.dbforpostgresql.NetworkArgs(
            delegated_subnet_resource_id=db_subnet_id,
            private_dns_zone_arm_resource_id=dns_zone.id,
        ),
        opts=pulumi.ResourceOptions(depends_on=[dns_link]),
    )

    # Allow-list TimescaleDB so CREATE EXTENSION is permitted.
    # Runs after the server exists.
    extensions_config = azure_native.dbforpostgresql.Configuration(
        "azure-extensions-config",
        resource_group_name=resource_group_name,
        server_name=server.name,
        configuration_name="azure.extensions",
        value="TIMESCALEDB",
        source="user-override",
        opts=pulumi.ResourceOptions(depends_on=[server]),
    )

    # TimescaleDB must also be preloaded at server startup. This is a
    # "static" parameter requiring a server restart before CREATE EXTENSION
    # timescaledb will actually work.
    #
    # Explicitly depends on extensions_config (not just server) so Pulumi
    # applies these two server-level Configuration changes sequentially
    # instead of in parallel — running them concurrently against the same
    # server intermittently fails with Code="ServerIsBusy".
    preload_config = azure_native.dbforpostgresql.Configuration(
        "shared-preload-libraries-config",
        resource_group_name=resource_group_name,
        server_name=server.name,
        configuration_name="shared_preload_libraries",
        value="TIMESCALEDB",
        source="user-override",
        opts=pulumi.ResourceOptions(depends_on=[extensions_config]),
    )

    # --- Read replica ---
    # Explicitly depends on both config changes finishing first, not just
    # the primary server's creation — creating the replica concurrently
    # with in-flight server-level config changes on the primary also
    # intermittently triggers ServerIsBusy.
    replica = azure_native.dbforpostgresql.Server(
        "bigproject-pg-replica",
        resource_group_name=resource_group_name,
        server_name="bigproject-pg-replica",
        location=location,
        tags=TAGS,
        create_mode="Replica",
        source_server_resource_id=server.id,
        network=azure_native.dbforpostgresql.NetworkArgs(
            delegated_subnet_resource_id=db_subnet_id,
            private_dns_zone_arm_resource_id=dns_zone.id,
        ),
        opts=pulumi.ResourceOptions(depends_on=[preload_config]),
    )

    return server, replica
