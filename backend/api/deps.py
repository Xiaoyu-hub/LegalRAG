"""租户校验依赖：让所有接口对「什么算合法租户」只有一处判断。

之前 documents / search 认任意字符串（不存在的租户也能建索引），
而 gateway 查注册表认不出就 401。两套口径导致：给不存在的租户传文档成功了，
一问一答却 401。e2e 自检就是在这种情况下红掉的。
"""
from fastapi import Header, HTTPException, Request

from backend.gateway.tenants import UnknownTenant

DEFAULT_TENANT = "demo"


def resolve_tenant(
    request: Request,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> str:
    """返回合法租户 id；未注册直接 401（与网关同一套口径）。"""
    tid = x_tenant_id or DEFAULT_TENANT
    registry = getattr(request.app.state, "tenant_registry", None)
    if registry is None:
        # 未加载租户配置时降级放行，避免把配置问题变成 500
        return tid
    try:
        return registry.get(tid).id
    except UnknownTenant:
        raise HTTPException(
            status_code=401,
            detail=f"unknown tenant: {tid!r}（未在 configs/tenants.yaml 注册）",
        )
