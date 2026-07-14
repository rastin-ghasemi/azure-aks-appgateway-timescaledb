import pulumi
import pulumi_azure_native as azure_native

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}


def create_log_analytics_workspace(resource_group_name: str, location: str):
    workspace = azure_native.operationalinsights.Workspace(
        "bigproject-logs",
        resource_group_name=resource_group_name,
        workspace_name="bigproject-logs",
        location=location,
        tags=TAGS,
        sku=azure_native.operationalinsights.WorkspaceSkuArgs(
            name="PerGB2018",
        ),
        retention_in_days=30,
    )
    return workspace


def create_postgres_diagnostics(postgres_server_id, workspace_id, resource_name: str):
    return azure_native.monitor.DiagnosticSetting(
        resource_name,
        resource_uri=postgres_server_id,
        name=f"{resource_name}-diag",
        workspace_id=workspace_id,
        logs=[
            azure_native.monitor.LogSettingsArgs(
                category="PostgreSQLLogs",
                enabled=True,
            ),
        ],
        metrics=[
            azure_native.monitor.MetricSettingsArgs(
                category="AllMetrics",
                enabled=True,
            ),
        ],
    )


def create_aks_diagnostics(aks_cluster_id, workspace_id):
    return azure_native.monitor.DiagnosticSetting(
        "aks-diagnostics",
        resource_uri=aks_cluster_id,
        name="aks-diag",
        workspace_id=workspace_id,
        logs=[
            azure_native.monitor.LogSettingsArgs(category="kube-apiserver", enabled=True),
            azure_native.monitor.LogSettingsArgs(category="kube-controller-manager", enabled=True),
            azure_native.monitor.LogSettingsArgs(category="kube-scheduler", enabled=True),
            azure_native.monitor.LogSettingsArgs(category="kube-audit", enabled=True),
            azure_native.monitor.LogSettingsArgs(category="guard", enabled=True),
        ],
        metrics=[
            azure_native.monitor.MetricSettingsArgs(category="AllMetrics", enabled=True),
        ],
    )


def create_appgw_diagnostics(appgw_id, workspace_id):
    return azure_native.monitor.DiagnosticSetting(
        "appgw-diagnostics",
        resource_uri=appgw_id,
        name="appgw-diag",
        workspace_id=workspace_id,
        logs=[
            azure_native.monitor.LogSettingsArgs(category="ApplicationGatewayAccessLog", enabled=True),
            azure_native.monitor.LogSettingsArgs(category="ApplicationGatewayPerformanceLog", enabled=True),
            azure_native.monitor.LogSettingsArgs(category="ApplicationGatewayFirewallLog", enabled=True),
        ],
        metrics=[
            azure_native.monitor.MetricSettingsArgs(category="AllMetrics", enabled=True),
        ],
    )
