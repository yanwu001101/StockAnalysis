"""GPT 分析引擎 (设计文档 §4)。

走 OpenAI 兼容协议 (/chat/completions), DeepSeek / Kimi / 通义 / GPT 等均可,
通过环境变量 ASTOCK_LLM_BASE_URL / ASTOCK_LLM_API_KEY / ASTOCK_LLM_MODEL 配置。
未配置 Key 或调用失败时返回 None, 由上层降级为纯规则报告。
"""
from __future__ import annotations

import requests

import config


def available() -> bool:
    return bool(config.LLM_API_KEY)


def chat(system: str, user: str, temperature: float = 0.4) -> str | None:
    if not available():
        return None
    url = config.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    body = {
        "model": config.LLM_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            json=body,
            timeout=config.LLM_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        print(f"[AI] LLM 调用失败, 降级为规则分析: {e}")
        return None
