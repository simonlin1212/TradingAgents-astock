"""火山方舟（Volcengine Ark）订阅套餐接入。

方舟的 Coding Plan / Agent Plan 对外提供 **Anthropic Messages 兼容**端点，
所以底层直接复用 anthropic_client 里的 ChatAnthropic 封装；与官方 Anthropic
的区别只有三处，也正是这个模块存在的原因：

1. base_url 是套餐固定的（见 model_catalog.ARK_PLAN_ENDPOINTS），用户不填也能跑；
2. API Key 用套餐专属变量。方舟给两个套餐各发一把 Key，与方舟平台的 API Key
   不同、且不能混用，所以不能和 ANTHROPIC_API_KEY 共享一个入口；
3. 模型 ID 是方舟自己的命名（ark-code-latest / kimi-k3 / glm-5.2 …），不是 claude-*。

出处：https://docs.volcengine.com/docs/82379/2373746
"""

import os
from typing import Any, Optional

from .anthropic_client import _PASSTHROUGH_KWARGS, NormalizedChatAnthropic
from .base_client import BaseLLMClient
from .model_catalog import ARK_PLAN_ENDPOINTS
from .validators import validate_model


class VolcengineArkClient(BaseLLMClient):
    """方舟订阅套餐客户端（provider 取 ark_coding / ark_agent）。"""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "ark_coding",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider

    def _resolve_api_key(self) -> str:
        """取套餐专属 Key，没配则回落 ANTHROPIC_API_KEY。

        回落是为了兼容既有配置：只订了一个套餐的用户此前就把方舟 Key 放在
        ANTHROPIC_API_KEY 里跑，不该因为这次新增而失效。
        """
        _, api_key_env = ARK_PLAN_ENDPOINTS[self.provider]
        api_key = os.environ.get(api_key_env) or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                f"{self.provider} 需要 API Key：在 .env 里设 {api_key_env}"
                "（或 ANTHROPIC_API_KEY）。注意方舟给 Coding Plan 和 Agent Plan "
                "各发一把专属 Key，与方舟平台 API Key 不同，不能混用。"
            )
        return api_key

    def get_llm(self) -> Any:
        """返回配好方舟端点与 Key 的 ChatAnthropic 实例。"""
        self.warn_if_unknown_model()
        default_base, _ = ARK_PLAN_ENDPOINTS[self.provider]
        llm_kwargs: dict[str, Any] = {
            "model": self.model,
            "base_url": self.base_url or default_base,
            "api_key": self._resolve_api_key(),
        }

        # 放在后面：显式传入的 api_key 优先于环境变量（与 openai_client 一致）。
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        """校验模型 ID。方舟在 validators 里放行任意 ID（会持续上下线模型）。"""
        return validate_model(self.provider, self.model)
