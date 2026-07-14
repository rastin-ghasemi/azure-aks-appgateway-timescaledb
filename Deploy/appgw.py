import pulumi
import pulumi_azure_native as azure_native

TAGS = {
    "project": "bigproject",
    "managed-by": "pulumi",
    "environment": "dev",
}

GATEWAY_NAME = "bigproject-appgw"
NODE_PORT = 32665


def create_app_gateway(
    resource_group_name,
    location: str,
    public_subnet_id: str,
    backend_ips: list,
    subscription_id,
    ssl_cert_data: pulumi.Output,
    ssl_cert_password: pulumi.Output,
):
    public_ip = azure_native.network.PublicIPAddress(
        "appgw-public-ip",
        resource_group_name=resource_group_name,
        location=location,
        tags=TAGS,
        sku=azure_native.network.PublicIPAddressSkuArgs(name="Standard"),
        public_ip_allocation_method="Static",
    )

    def sub_id(args, kind, name):
        sub_id_val, rg_name = args
        return (
            f"/subscriptions/{sub_id_val}/resourceGroups/{rg_name}/providers/"
            f"Microsoft.Network/applicationGateways/{GATEWAY_NAME}/{kind}/{name}"
        )

    ids = pulumi.Output.all(subscription_id, resource_group_name)

    frontend_ip_id = ids.apply(lambda a: sub_id(a, "frontendIPConfigurations", "appgw-frontend-ip"))
    frontend_port_80_id = ids.apply(lambda a: sub_id(a, "frontendPorts", "port-80"))
    frontend_port_443_id = ids.apply(lambda a: sub_id(a, "frontendPorts", "port-443"))
    backend_pool_id = ids.apply(lambda a: sub_id(a, "backendAddressPools", "app-backend-pool"))
    backend_settings_id = ids.apply(lambda a: sub_id(a, "backendHttpSettingsCollection", "app-http-settings"))
    probe_id = ids.apply(lambda a: sub_id(a, "probes", "app-health-probe"))
    listener_http_id = ids.apply(lambda a: sub_id(a, "httpListeners", "app-listener-http"))
    listener_https_id = ids.apply(lambda a: sub_id(a, "httpListeners", "app-listener-https"))
    ssl_cert_id = ids.apply(lambda a: sub_id(a, "sslCertificates", "appgw-ssl-cert"))

    gateway = azure_native.network.ApplicationGateway(
        "bigproject-appgw",
        resource_group_name=resource_group_name,
        application_gateway_name=GATEWAY_NAME,
        location=location,
        tags=TAGS,
        sku=azure_native.network.ApplicationGatewaySkuArgs(
            name="Standard_v2",
            tier="Standard_v2",
        ),
        autoscale_configuration=azure_native.network.ApplicationGatewayAutoscaleConfigurationArgs(
            min_capacity=1,
            max_capacity=2,
        ),
        gateway_ip_configurations=[
            azure_native.network.ApplicationGatewayIPConfigurationArgs(
                name="appgw-ip-config",
                subnet=azure_native.network.SubResourceArgs(id=public_subnet_id),
            )
        ],
        frontend_ip_configurations=[
            azure_native.network.ApplicationGatewayFrontendIPConfigurationArgs(
                name="appgw-frontend-ip",
                public_ip_address=azure_native.network.SubResourceArgs(id=public_ip.id),
            )
        ],
        frontend_ports=[
            azure_native.network.ApplicationGatewayFrontendPortArgs(name="port-80", port=80),
            azure_native.network.ApplicationGatewayFrontendPortArgs(name="port-443", port=443),
        ],
        ssl_certificates=[
            azure_native.network.ApplicationGatewaySslCertificateArgs(
                name="appgw-ssl-cert",
                data=ssl_cert_data,
                password=ssl_cert_password,
            )
        ],
        backend_address_pools=[
            azure_native.network.ApplicationGatewayBackendAddressPoolArgs(
                name="app-backend-pool",
                backend_addresses=[
                    azure_native.network.ApplicationGatewayBackendAddressArgs(ip_address=ip)
                    for ip in backend_ips
                ],
            )
        ],
        probes=[
            azure_native.network.ApplicationGatewayProbeArgs(
                name="app-health-probe",
                protocol="Http",
                path="/health",
                pick_host_name_from_backend_http_settings=True,
                interval=30,
                timeout=30,
                unhealthy_threshold=3,
                match=azure_native.network.ApplicationGatewayProbeHealthResponseMatchArgs(
                    status_codes=["200-399"],
                ),
            )
        ],
        backend_http_settings_collection=[
            azure_native.network.ApplicationGatewayBackendHttpSettingsArgs(
                name="app-http-settings",
                port=NODE_PORT,
                protocol="Http",
                cookie_based_affinity="Disabled",
                request_timeout=30,
                pick_host_name_from_backend_address=True,
                probe=azure_native.network.SubResourceArgs(id=probe_id),
            )
        ],
        http_listeners=[
            azure_native.network.ApplicationGatewayHttpListenerArgs(
                name="app-listener-http",
                frontend_ip_configuration=azure_native.network.SubResourceArgs(id=frontend_ip_id),
                frontend_port=azure_native.network.SubResourceArgs(id=frontend_port_80_id),
                protocol="Http",
            ),
            azure_native.network.ApplicationGatewayHttpListenerArgs(
                name="app-listener-https",
                frontend_ip_configuration=azure_native.network.SubResourceArgs(id=frontend_ip_id),
                frontend_port=azure_native.network.SubResourceArgs(id=frontend_port_443_id),
                protocol="Https",
                ssl_certificate=azure_native.network.SubResourceArgs(id=ssl_cert_id),
            ),
        ],
        request_routing_rules=[
            azure_native.network.ApplicationGatewayRequestRoutingRuleArgs(
                name="app-routing-rule-http",
                rule_type="Basic",
                priority=100,
                http_listener=azure_native.network.SubResourceArgs(id=listener_http_id),
                backend_address_pool=azure_native.network.SubResourceArgs(id=backend_pool_id),
                backend_http_settings=azure_native.network.SubResourceArgs(id=backend_settings_id),
            ),
            azure_native.network.ApplicationGatewayRequestRoutingRuleArgs(
                name="app-routing-rule-https",
                rule_type="Basic",
                priority=110,
                http_listener=azure_native.network.SubResourceArgs(id=listener_https_id),
                backend_address_pool=azure_native.network.SubResourceArgs(id=backend_pool_id),
                backend_http_settings=azure_native.network.SubResourceArgs(id=backend_settings_id),
            ),
        ],
    )

    return gateway, public_ip
