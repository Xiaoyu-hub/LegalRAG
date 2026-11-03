"""模型价格表：把 token 换算成钱。

诚实边界：本机 Ollama 是本地推理，边际成本≈0（只有电费），所以本地模型价格写 0。
云模型必须去官方定价页填真实数字——配置文件里留了出处字段，**没核实过的价格不要填**，
面试被问「你这 0.0004 美元怎么来的」要能指到定价页。
"""
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = "configs/model_prices.yaml"


@dataclass(frozen=True)
class Price:
    """每 100 万 token 的美元单价。"""

    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    source: str = ""


class PricingTable:
    def __init__(self, prices: dict[str, Price]):
        self.prices = prices

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG) -> "PricingTable":
        p = Path(path)
        if not p.exists():
            logger.warning("价格表 %s 不存在，全部按 0 计价", path)
            return cls({})
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        prices = {}
        for model, cfg in (data.get("models") or {}).items():
            prices[model] = Price(
                input_per_1m=float(cfg.get("input_per_1m", 0.0)),
                output_per_1m=float(cfg.get("output_per_1m", 0.0)),
                source=str(cfg.get("source", "")),
            )
        return cls(prices)

    def get(self, model: str) -> Price:
        price = self.prices.get(model)
        if price is None:
            # 未知模型不报错：宁可记 0 成本，也不要让一次请求因为价格表缺行而失败
            logger.warning("模型 %s 未在价格表中，按 0 计价", model)
            return Price()
        return price

    def cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        p = self.get(model)
        return (
            prompt_tokens / 1_000_000 * p.input_per_1m
            + completion_tokens / 1_000_000 * p.output_per_1m
        )
