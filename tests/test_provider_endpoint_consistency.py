"""CLI 与客户端兜底必须指向同一个 provider 端点（#113）。

同一批 provider 的 base URL 写在两处：`cli/utils.py` 的 `select_llm_provider()`
里给 CLI 用，`llm_clients/openai_client.py` 的 `_PROVIDER_CONFIG` 给客户端兜底
（Web 侧栏 Base URL 留空时生效）。v0.2.4 引入时两处就没对齐：glm 一边
`open.bigmodel.cn`（国内站）一边 `api.z.ai`（海外站），qwen 一边
`dashscope.aliyuncs.com` 一边 `dashscope-intl`。两站都能用同一个 key 且返回同一份
模型列表，所以**不报错**，只是从 CLI 跑和从 Web 跑会静默走不同网络路径。

这条测试钉住「两处对同一个 provider 必须给同一个值」，防止再分裂一次。
CLI 的列表是 `select_llm_provider()` 的局部变量，所以照 test_sentiment_data_tools
的做法扫源码而不是 import。
"""

import inspect
import re

from cli.utils import select_llm_provider
from tradingagents.llm_clients.openai_client import _PROVIDER_CONFIG


def _cli_endpoints() -> dict[str, str]:
    """从 select_llm_provider 源码里抽出 {provider_key: base_url}，跳过 base_url 为 None 的。"""
    src = inspect.getsource(select_llm_provider)
    return {
        key: url
        for key, url in re.findall(r'\(\s*"[^"]+"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', src)
    }


# 两侧都带 base URL、因而必须逐字一致的 provider。
# 不含 minimax（只有客户端兜底有，CLI 的 provider 列表里没有这一项），
# 也不含 azure / google / openai_compatible（CLI 侧 base_url 为 None，运行时再问）。
_MUST_AGREE = {"deepseek", "glm", "ollama", "openrouter", "qwen", "requesty", "xai"}


def test_cli_and_client_fallback_agree_on_endpoints():
    """两处都定义了的 provider，base URL 必须逐字相同。"""
    cli = _cli_endpoints()
    assert cli, "没从 select_llm_provider 里解析出任何 provider，正则或源码结构变了"

    shared = sorted(set(cli) & set(_PROVIDER_CONFIG))
    # 这里必须是**恰好相等**而不是「非空」：只断言非空的话，某一侧少写了一个
    # provider（或正则漏解析了一行）会让它悄悄退出比对范围，测试照样绿——
    # 那正是这条测试要防的失效模式。少了就说明两侧的 provider 名单开始分家，
    # 新增 provider 时请同步更新 _MUST_AGREE。
    assert set(shared) == _MUST_AGREE, (
        f"应当逐字比对的 provider 集合变了：实际 {sorted(shared)}，预期 {sorted(_MUST_AGREE)}。"
        "若是有意增删 provider，请同步改 _MUST_AGREE；否则是某一侧漏写或解析失效。"
    )

    mismatches = {
        key: (cli[key], _PROVIDER_CONFIG[key][0])
        for key in shared
        if cli[key] != _PROVIDER_CONFIG[key][0]
    }
    assert not mismatches, (
        "CLI 与客户端兜底对同一 provider 给了不同端点，用户换个入口就换站点：\n"
        + "\n".join(f"  {k}: CLI={v[0]!r} 兜底={v[1]!r}" for k, v in mismatches.items())
    )


def test_domestic_providers_point_to_domestic_sites():
    """glm / qwen 面向国内用户，兜底端点不能是海外站（#113 的具体取向）。

    这是 A 股特化 fork，README 中英文都让用户去 open.bigmodel.cn 申请 key。
    要改成面向海外，需同时改 CLI、兜底、README 三处并在 CHANGELOG 标 breaking。
    """
    overseas = {
        "glm": "api.z.ai",
        "qwen": "dashscope-intl",
    }
    for provider, marker in overseas.items():
        url = _PROVIDER_CONFIG[provider][0]
        assert marker not in url, (
            f"{provider} 的兜底端点回到了海外站 {url}；"
            f"若确要切换，请同时改 cli/utils.py 与 README 并标 breaking"
        )
