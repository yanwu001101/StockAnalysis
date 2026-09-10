"""AStock-Agent 全局配置。

所有可调参数集中在这里, 支持环境变量覆盖。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 存储路径
DB_PATH = Path(os.getenv("ASTOCK_DB_PATH", str(BASE_DIR / "astock.db")))
REPORT_DIR = Path(os.getenv("ASTOCK_REPORT_DIR", str(BASE_DIR / "reports")))

# ---------------------------------------------------------------------------
# AI 分析引擎 (OpenAI 兼容协议, DeepSeek / Kimi / 通义 / GPT 等均可)
# 不配置 API Key 时自动降级为纯规则分析, 不影响报告生成。
# ---------------------------------------------------------------------------
LLM_BASE_URL = os.getenv("ASTOCK_LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY = os.getenv("ASTOCK_LLM_API_KEY", "")
LLM_MODEL = os.getenv("ASTOCK_LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT = int(os.getenv("ASTOCK_LLM_TIMEOUT", "120"))

# ---------------------------------------------------------------------------
# 龙头评分模型权重 (设计文档 §3.3)
# 题材强度 30% + 连板高度 25% + 成交资金 20% + 市场辨识度 15% + 龙虎榜资金 10%
# ---------------------------------------------------------------------------
DRAGON_WEIGHTS = {
    "theme": 0.30,   # 题材强度
    "height": 0.25,  # 连板高度
    "amount": 0.20,  # 成交资金
    "fame": 0.15,    # 市场辨识度
    "lhb": 0.10,     # 龙虎榜资金
}

# 市场温度阈值 (设计文档 §3.1): >=70 强势 / 45-70 震荡 / 30-45 弱势 / <30 退潮
TEMP_STRONG = 70
TEMP_RANGE = 45
TEMP_WEAK = 30

# 龙虎榜: 只对净买额靠前的 N 只个股拉取席位明细(控制请求量)
LHB_SEAT_DETAIL_TOP = 8

# 网络容错
FETCH_RETRIES = 3
FETCH_WAIT = 2.0
MAX_LOOKBACK_DAYS = 12  # 找不到数据时向前回退的最大自然日数
