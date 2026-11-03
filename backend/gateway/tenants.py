"""租户注册表：模型白名单、预算、限速。"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = "configs/tenants.yaml"


class UnknownTenant(KeyError):
    """租户不存在。调用方应转成 401/403，而不是 500。"""


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str = ""
    models: tuple[str, ...] = ()
    monthly_budget_usd: float | None = None
    rpm_limit: int | None = None
    default_model: str = ""

    def allows(self, model: str) -> bool:
        return not self.models or model in self.models


class TenantRegistry:
    def __init__(self, tenants: dict[str, Tenant], default_tenant: str = "demo"):
        self.tenants = tenants
        self.default_tenant = default_tenant

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG) -> "TenantRegistry":
        p = Path(path)
        if not p.exists():
            logger.warning("租户配置 %s 不存在，只有默认租户", path)
            return cls({"demo": Tenant(id="demo", models=())}, "demo")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        tenants = {}
        for tid, cfg in (data.get("tenants") or {}).items():
            tenants[tid] = Tenant(
                id=tid,
                name=str(cfg.get("name", tid)),
                models=tuple(cfg.get("models") or ()),
                monthly_budget_usd=cfg.get("monthly_budget_usd"),
                rpm_limit=cfg.get("rpm_limit"),
                default_model=str(cfg.get("default_model", "")),
            )
        return cls(tenants, str(data.get("default_tenant", "demo")))

    def get(self, tenant_id: str | None) -> Tenant:
        tid = tenant_id or self.default_tenant
        if tid not in self.tenants:
            raise UnknownTenant(tid)
        return self.tenants[tid]
