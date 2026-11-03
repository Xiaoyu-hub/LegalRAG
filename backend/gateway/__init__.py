"""LLM 网关层（多后端路由 / 配额 / 计量 / 成本归因）。"""
from backend.gateway.gateway import (
    GatewayError,
    GatewayResult,
    LLMGateway,
    ModelNotAllowed,
    NoProviderAvailable,
    QuotaExceeded,
)
from backend.gateway.metering import MeteringStore, UsageRecord
from backend.gateway.pricing import Price, PricingTable
from backend.gateway.tenants import Tenant, TenantRegistry, UnknownTenant

__all__ = [
    "LLMGateway",
    "GatewayResult",
    "GatewayError",
    "QuotaExceeded",
    "ModelNotAllowed",
    "NoProviderAvailable",
    "MeteringStore",
    "UsageRecord",
    "PricingTable",
    "Price",
    "Tenant",
    "TenantRegistry",
    "UnknownTenant",
]
