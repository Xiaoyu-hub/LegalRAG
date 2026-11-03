"""LLM 网关：多后端路由 + 主备降级 + 租户配额 + 成本归因。

它做的是「Provider 之上、业务之下」这一层，也就是 OpenHex JD 里
「LLM 网关：多租户、并发、成本控制」指的活。LiteLLM 之类解决「多 provider 协议与路由」，
但不管业务侧配额与成本归属——那层在这里。
"""
import logging
import time
from dataclasses import dataclass
from typing import Iterator

from backend.generation.providers.base import Provider, ProviderResponse
from backend.gateway.metering import MeteringStore, UsageRecord
from backend.gateway.pricing import PricingTable
from backend.gateway.tenants import Tenant, TenantRegistry

logger = logging.getLogger(__name__)


class GatewayError(Exception):
    """网关层错误基类。"""


class QuotaExceeded(GatewayError):
    """超预算或超速。调用方应返回 429，并带上 retry_after 秒。"""

    def __init__(self, tenant: str, reason: str, retry_after: int = 60):
        super().__init__(f"tenant={tenant} quota exceeded: {reason}")
        self.tenant = tenant
        self.reason = reason
        self.retry_after = retry_after


class ModelNotAllowed(GatewayError):
    """模型不在该租户白名单内。调用方应返回 403。"""


class NoProviderAvailable(GatewayError):
    """候选后端全崩。调用方应返回 502/503。"""


@dataclass
class GatewayResult:
    content: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: float
    fallback_from: str = ""


class LLMGateway:
    def __init__(
        self,
        providers: dict[str, Provider],
        routes: dict[str, str],
        pricing: PricingTable,
        tenants: TenantRegistry,
        metering: MeteringStore,
    ):
        """
        Args:
            providers: provider 名 -> 实例（ollama / openai / fake ...）
            routes: 模型名 -> provider 名（一个模型走哪个后端）
        """
        self.providers = providers
        self.routes = routes
        self.pricing = pricing
        self.tenants = tenants
        self.metering = metering

    # ── 配额 ────────────────────────────────────────────────────────────
    def _check_quota(self, tenant: Tenant):
        if tenant.rpm_limit:
            used = self.metering.recent_calls(tenant.id, window_sec=60)
            if used >= tenant.rpm_limit:
                raise QuotaExceeded(tenant.id, f"rpm {used}/{tenant.rpm_limit}", 60)

        if tenant.monthly_budget_usd is not None:
            spent = self.metering.month_cost(tenant.id)
            if spent >= tenant.monthly_budget_usd:
                # 预算耗尽：退避到月初，这里给 3600 让调用方别立刻重试
                raise QuotaExceeded(
                    tenant.id,
                    f"monthly budget {spent:.6f}/{tenant.monthly_budget_usd}",
                    3600,
                )

    # ── 路由 ────────────────────────────────────────────────────────────
    def _candidates(self, tenant: Tenant, model: str | None) -> list[str]:
        primary = model or tenant.default_model or (tenant.models[0] if tenant.models else "")
        if not primary:
            raise ModelNotAllowed(f"tenant={tenant.id} 没有可用模型")
        if not tenant.allows(primary):
            raise ModelNotAllowed(
                f"tenant={tenant.id} 不允许模型 {primary}（白名单 {tenant.models}）"
            )
        # 主模型在前，白名单内其余模型作降级候选
        others = [m for m in tenant.models if m != primary]
        return [primary] + others

    def complete(
        self,
        tenant_id: str | None,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> GatewayResult:
        tenant = self.tenants.get(tenant_id)
        self._check_quota(tenant)

        last_error: Exception | None = None
        primary = model or tenant.default_model
        for candidate in self._candidates(tenant, model):
            provider_name = self.routes.get(candidate)
            provider = self.providers.get(provider_name) if provider_name else None
            if provider is None:
                logger.warning("模型 %s 没有可用后端（route=%s），跳过", candidate, provider_name)
                continue
            start = time.time()
            try:
                resp: ProviderResponse = provider.generate(system_prompt, user_prompt)
            except Exception as exc:
                last_error = exc
                logger.warning("后端 %s 调用 %s 失败：%s", provider_name, candidate, exc)
                continue

            latency_ms = (time.time() - start) * 1000
            cost = self.pricing.cost(candidate, resp.prompt_tokens, resp.completion_tokens)
            fallback_from = primary if candidate != primary else ""
            self.metering.record(UsageRecord(
                tenant=tenant.id,
                model=candidate,
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                ok=True,
                fallback_from=fallback_from,
            ))
            return GatewayResult(
                content=resp.content,
                model=candidate,
                provider=provider_name,
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                fallback_from=fallback_from,
            )

        raise NoProviderAvailable(
            f"tenant={tenant.id} 所有候选后端均失败：{last_error}"
        )

    def stream(self, tenant_id: str | None, system_prompt: str,
               user_prompt: str, model: str | None = None) -> Iterator[str]:
        """流式：配额与路由同 complete；token 在流结束后计量。"""
        tenant = self.tenants.get(tenant_id)
        self._check_quota(tenant)

        candidates = self._candidates(tenant, model)
        primary = candidates[0]
        provider = None
        chosen = primary
        for candidate in candidates:
            provider_name = self.routes.get(candidate)
            cand_provider = self.providers.get(provider_name) if provider_name else None
            if cand_provider is not None:
                provider, chosen = cand_provider, candidate
                break
        if provider is None:
            raise NoProviderAvailable(f"tenant={tenant.id} 所有候选后端均不可用")

        start = time.time()
        buf: list[str] = []
        for piece in provider.stream(system_prompt, user_prompt):
            buf.append(piece)
            yield piece

        from backend.generation.tokens import count_tokens

        content = "".join(buf)
        prompt_tokens = count_tokens(system_prompt) + count_tokens(user_prompt)
        completion_tokens = count_tokens(content)
        cost = self.pricing.cost(chosen, prompt_tokens, completion_tokens)
        self.metering.record(UsageRecord(
            tenant=tenant.id,
            model=chosen,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            latency_ms=(time.time() - start) * 1000,
            ok=True,
        ))

    def usage(self, tenant_id: str | None) -> dict:
        tenant = self.tenants.get(tenant_id)
        summary = self.metering.summary(tenant.id)
        summary["month_cost_usd"] = round(self.metering.month_cost(tenant.id), 6)
        summary["monthly_budget_usd"] = tenant.monthly_budget_usd
        summary["rpm_limit"] = tenant.rpm_limit
        summary["rpm_used"] = self.metering.recent_calls(tenant.id, window_sec=60)
        return summary
