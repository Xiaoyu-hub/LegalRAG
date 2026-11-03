"""网关 API：多租户对话 + 用量查询。

状态码约定（面试会问「超预算你为什么返 429 不返 500」）：
  403 ModelNotAllowed  —— 租户白名单不允许（换模型即可）
  401 UnknownTenant    —— 租户不存在（认证问题）
  429 QuotaExceeded    —— 超预算/超速，带 Retry-After
  503 NoProviderAvailable —— 后端全崩（重试可能有用）
"""
import logging

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.deps import resolve_tenant

from backend.gateway import (
    ModelNotAllowed,
    NoProviderAvailable,
    QuotaExceeded,
    UnknownTenant,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gateway", tags=["gateway"])


class GatewayChatRequest(BaseModel):
    system: str = "You are a helpful assistant."
    question: str
    model: str | None = None
    stream: bool = False


def _err(status: int, message: str) -> dict:
    return {"status": "error", "data": None, "error": message, "_status": status}


@router.post("/chat")
def gateway_chat(
    req: GatewayChatRequest,
    request: Request,
    tenant: str = Depends(resolve_tenant),
):
    """网关对话。

    同 search：底层是同步 HTTP 调用（ollama / openai），写成 async def 会串行化。
    实测 async 版本并发 1→16 吞吐恒为 ~20.8 rps，P99 从 66ms 涨到 2292ms。
    """
    gw = request.app.state.gateway

    try:
        if req.stream:
            gen = gw.stream(tenant, req.system, req.question, model=req.model)
            return StreamingResponse(gen, media_type="text/plain")

        res = gw.complete(tenant, req.system, req.question, model=req.model)
        return {
            "status": "ok",
            "data": {
                "answer": res.content,
                "model": res.model,
                "provider": res.provider,
                "prompt_tokens": res.prompt_tokens,
                "completion_tokens": res.completion_tokens,
                "cost_usd": round(res.cost_usd, 8),
                "latency_ms": round(res.latency_ms, 1),
                "fallback_from": res.fallback_from,
            },
            "error": None,
        }
    except UnknownTenant as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={
            "status": "error", "data": None, "error": f"unknown tenant: {exc}"})
    except ModelNotAllowed as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={
            "status": "error", "data": None, "error": str(exc)})
    except QuotaExceeded as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=429,
            content={"status": "error", "data": None, "error": str(exc)},
            headers={"Retry-After": str(exc.retry_after)},
        )
    except NoProviderAvailable as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={
            "status": "error", "data": None, "error": str(exc)})


@router.get("/usage")
async def gateway_usage(request: Request,
                        tenant: str = Depends(resolve_tenant)):
    gw = request.app.state.gateway
    try:
        return {"status": "ok", "data": gw.usage(tenant), "error": None}
    except UnknownTenant as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={
            "status": "error", "data": None, "error": f"unknown tenant: {exc}"})
