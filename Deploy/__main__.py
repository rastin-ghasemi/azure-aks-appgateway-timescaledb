"""BigProject Deploy: Network + Database + ACR + AKS + App Gateway + Monitoring layer"""
import pulumi
import pulumi_azure_native as azure_native
from nsg import create_nsgs
from network import create_network
from database import create_database
from acr import create_acr
from aks import create_aks_cluster
from appgw import create_app_gateway
from monitoring import (
    create_log_analytics_workspace,
    create_postgres_diagnostics,
    create_aks_diagnostics,
    create_appgw_diagnostics,
)

location = "westus2"

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}

setup_stack = pulumi.StackReference("rastin-ghasemi/bigproject-setup/dev")
resource_group_name = setup_stack.get_output("resource_group_name")

client_config = azure_native.authorization.get_client_config()
subscription_id = client_config.subscription_id

nsgs = create_nsgs(resource_group_name, location)
net = create_network(resource_group_name, location, nsgs)

pulumi.export("vnet_id", net["vnet"].id)
pulumi.export("vnet_name", net["vnet"].name)
pulumi.export("public_subnet_id", net["public_subnet"].id)
pulumi.export("private_app_subnet_id", net["private_app_subnet"].id)
pulumi.export("private_db_subnet_id", net["private_db_subnet"].id)
pulumi.export("admin_subnet_id", net["admin_subnet"].id)

config = pulumi.Config()
db_password = config.require_secret("db_admin_password")

pg_server, pg_replica = create_database(
    resource_group_name,
    location,
    net["vnet"].id,
    net["private_db_subnet"].id,
    db_password,
)

pulumi.export("postgres_server_name", pg_server.name)
pulumi.export("postgres_replica_name", pg_replica.name)

registry = create_acr(resource_group_name, location)

pulumi.export("acr_login_server", registry.login_server)
pulumi.export("acr_name", registry.name)

aks_cluster = create_aks_cluster(
    resource_group_name,
    location,
    net["private_app_subnet"].id,
    registry.id,
    net["vnet"].id,
    subscription_id,
)

pulumi.export("aks_cluster_name", aks_cluster.name)

app_backend_ip_1 = config.require("app_backend_ip_1")
app_backend_ip_2 = config.require("app_backend_ip_2")
ssl_cert_data = config.require_secret("appgw_ssl_cert_data")
ssl_cert_password = config.require_secret("appgw_ssl_cert_password")

appgw, appgw_public_ip = create_app_gateway(
    resource_group_name,
    location,
    net["public_subnet"].id,
    [app_backend_ip_1, app_backend_ip_2],
    subscription_id,
    ssl_cert_data,
    ssl_cert_password,
)

pulumi.export("appgw_public_ip", appgw_public_ip.ip_address)

# --- Monitoring layer ---
log_workspace = create_log_analytics_workspace(resource_group_name, location)

create_postgres_diagnostics(pg_server.id, log_workspace.id, "postgres-primary-diagnostics")
create_postgres_diagnostics(pg_replica.id, log_workspace.id, "postgres-replica-diagnostics")
create_aks_diagnostics(aks_cluster.id, log_workspace.id)
create_appgw_diagnostics(appgw.id, log_workspace.id)

pulumi.export("log_analytics_workspace_name", log_workspace.name)
pulumi.export("log_analytics_workspace_id", log_workspace.id)
