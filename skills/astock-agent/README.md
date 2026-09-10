# AStock-Agent（A股游资分析助手）

基于 **数据分析 + AI 推理** 的 A 股短线资金研究工具。采集市场行情、涨停、龙虎榜、板块数据，分析市场情绪周期、热点板块轮动、龙头强弱与游资资金行为，自动生成每日复盘报告与个股分析报告。

> 本工具只做资金行为研究，不构成任何投资建议。研究资金而非预测价格，研究概率而非追求确定，控制风险优先于盈利。

## 系统架构

```
 数据源(东财/新浪, 多层回退)
   行情 · 涨停池 · 炸板池 · 跌停池 · 龙虎榜席位 · 板块资金流
        │
 数据采集层  data/market.py · data/stock.py · data/longhu.py
        │        (交易日历/容错重试/ST过滤/单位自愈)
 数据分析层  analysis/
   ├─ emotion.py  市场温度(0~100) + 情绪周期(启动/发酵/高潮/退潮/过渡)
   ├─ dragon.py   连板梯队 + 龙头评分(题材30/高度25/资金20/辨识度15/龙虎榜10)
   ├─ theme.py    板块强度(涨停数+资金+持续性+龙头) + 主线/轮动状态
   └─ capital.py  游资席位识别 + 资金类型/态度 + 风险
        │
 AI 决策层   ai/prompt.py · ai/gpt.py (OpenAI兼容协议, 可选)
        │
 输出层      report/generator.py -> reports/*.md · --json 结构化输出
 持久层      database/sqlite.py (stock/limit_up/longhu/trader/market_daily)
```

## 快速开始

```bash
pip install -r requirements.txt

python main.py                    # 最近交易日全市场复盘
python main.py --date 20260715   # 指定交易日
python main.py --stock 600664    # 个股资金分析
python main.py --json            # stdout 输出结构化 JSON (日志在 stderr)
python main.py --no-ai           # 跳过 LLM
```

报告落盘 `reports/daily_YYYYMMDD.md` / `reports/stock_代码_日期.md`。

**建议每个交易日收盘后运行一次**：情绪周期趋势、板块持续天数、晋级率对比依赖 SQLite 中的历史快照，连续积累数日后判断显著更准。龙虎榜一般在 17:00~19:00 公布，晚间运行数据最全。

## AI 复盘配置（可选）

走 OpenAI 兼容协议，DeepSeek / Kimi / 通义 / GPT 均可；不配置则纯规则报告（配合 Claude skill 使用时由 Claude 充当 AI 层）：

```bash
export ASTOCK_LLM_API_KEY=sk-xxx
export ASTOCK_LLM_BASE_URL=https://api.deepseek.com/v1   # 默认
export ASTOCK_LLM_MODEL=deepseek-chat                     # 默认
```

AI 输出强制包含：市场环境 / 资金方向 / 龙头判断 / 风险分析 / 明日观察 / 仓位建议；禁止保证盈利、必买推荐、确定性涨跌预测。

## 核心模型

**市场温度 (0~100)** = 涨停强度(40) + 上涨比例(25) + 成交额/量能环比(15) + 封板质量(20) − 跌停惩罚(15)，缺失分量自动重新归一化。`≥70 强势 / 45~70 震荡 / 30~45 弱势 / <30 退潮`

**情绪周期**：结合温度趋势、连板高度变化、昨日涨停晋级率、亏钱效应、大面数量规则判定，输出阶段 + 判定依据 + 应对策略。

**龙头评分** = 题材强度×30% + 连板高度×25% + 成交资金×20% + 市场辨识度×15% + 龙虎榜资金×10%，输出定位（市场龙头/板块龙头/梯队成员）、优势与风险。

**板块强度** = 涨停数量(40) + 主力净流入(25) + 持续天数(20) + 龙头高度(15)，输出主线、状态（启动/发酵/分化提纯/持续/退潮）与持续性。

**游资识别**：内置知名席位标签库（民间公开统计，关键词匹配，存 `trader` 表可扩展），龙虎榜席位分类为 机构/北向/散户通道/知名游资/普通席位，推导资金类型与态度。

## 数据源与容错

- 涨停/跌停/炸板池、龙虎榜：东方财富（akshare），支持历史日期
- 指数与成交额：东财日线 → 新浪日线 → 新浪实时 多层回退；成交量单位错位自动修正
- 涨跌家数：乐咕 → 东财全市场快照，均失败则温度模型自动降权
- 板块资金流：东财（仅当日有效，历史日期自动取中性值）
- ST/*ST/退市股全部过滤；非交易日自动回退最近交易日

## 目录结构

```
astock-agent/
├── SKILL.md               # Claude skill 定义
├── main.py                # CLI 入口
├── config.py              # 配置(权重/阈值/LLM/路径)
├── data/                  # 采集层: market / stock / longhu
├── analysis/              # 分析层: emotion / dragon / theme / capital
├── ai/                    # AI层: prompt / gpt
├── database/sqlite.py     # 持久层
├── report/generator.py    # Markdown 报告生成
├── examples.md            # 使用示例
└── reports/               # 输出目录(运行时生成)
```

## 路线图

- **V1 基础版（已完成）**：数据采集、涨停统计、龙虎榜读取、自动复盘报告
- **V2 智能分析版（已完成）**：龙头评分、游资标签、情绪周期判断、板块轮动、个股分析、AI 复盘
- **V3 实战版（规划）**：盘中实时监控、自选股提醒、微信推送、Web Dashboard（可接入本仓库 data-service/frontend）

## 免责声明

本项目所有输出均为公开数据的程序化整理与研究参考，不构成任何投资建议。游资席位风格标签来自民间公开统计，可能存在误差。市场有风险，交易需谨慎。
