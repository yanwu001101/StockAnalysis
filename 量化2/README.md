# QMT Data Platform

面向 A 股研究、因子计算和实盘系统的本地数据底座。支持 QMT/XtQuant，也支持
`a-stock-data` 使用的腾讯公开行情接口；DuckDB 负责去重存储与分析查询，FastAPI
提供统一接口。没有 QMT/XtQuant 时，`auto` 模式会优先尝试真实公开行情。

## 当前能力

- XtQuant 历史行情下载与标准化接入
- 日线及 `1m/5m/15m/30m/1h` K 线
- 前复权、后复权和不复权参数
- 增量同步、主键去重、同步运行审计
- DuckDB 本地分析库与 ZSTD Parquet 导出
- REST API、Swagger 文档和命令行工具
- 模拟数据源和端到端自动化测试
- 无 QMT 时的腾讯实时快照与分钟/日线行情

这一版本只处理只读行情。账户、持仓和下单将在独立的交易网关中实现，并在接入前
加入账户白名单、金额上限、重复委托保护、交易时段校验和人工熔断。

## 架构

```text
QMT / XtQuant 或腾讯公开行情 (a-stock-data)
          |
          v
Provider Adapter -> Normalized Bars -> Sync Service -> DuckDB -> Parquet
                                             |
                                             v
                                      FastAPI / CLI
```

## 1. 创建环境

建议使用 QMT 兼容性更好的 Python 3.9：

```powershell
uv venv --python 3.9
.venv\Scripts\Activate.ps1
uv sync --python 3.9 --extra dev --no-editable
Copy-Item .env.example .env
```

当前目录含中文时建议保留 `--no-editable`。部分 Windows Python 工具链会错误编码
editable 安装的路径；代码变更后执行
`uv sync --extra dev --no-editable --reinstall-package qmt-data-platform` 更新已安装包。

## 2. 选择数据源

### 没有 QMT：使用 a-stock-data 公开行情

在 `.env` 中设置：

```dotenv
QDP_PROVIDER=astock
```

该模式不需要账户或 API Key，支持腾讯实时快照和日线/分钟 K 线，适合研究、复盘
和原型验证。腾讯接口是公开数据源，仍可能受网络、限流或接口变更影响。

### 使用 QMT/XtQuant

先安装并启动券商 QMT 客户端，完成一次登录和行情初始化。XtQuant 通常随 QMT
发行，不建议从非官方来源下载。将 QMT 安装目录内与当前 Python 版本匹配的
`xtquant` 包安装到 `.venv`，或把它的父目录写入虚拟环境的 `.pth` 文件。

确认接入：

```powershell
python -c "from xtquant import xtdata; print(len(xtdata.get_sector_list()))"
```

修改 `.env`：

```dotenv
QDP_PROVIDER=xtquant
QDP_QMT_PATH=C:\券商QMT\userdata_mini
```

`QDP_QMT_PATH` 在当前只读行情模块中仅用于诊断，后续连接 `XtQuantTrader` 时会作为
MiniQMT 用户目录使用。开发环境可设置 `QDP_PROVIDER=mock`。

## 3. 采集和查询

```powershell
qdp doctor
qdp sync 000001.SZ,600000.SH --period 1d --start 2024-01-01
qdp export
qdp serve
```

启动后访问：

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

常用接口：

```text
POST /v1/market/sync
GET  /v1/market/bars?symbol=000001.SZ&period=1d
GET  /v1/market/quotes?symbols=000001.SZ,600000.SH
POST /v1/storage/export
```

同步请求示例：

```json
{
  "symbols": ["000001.SZ", "600000.SH"],
  "period": "1d",
  "start": "2024-01-01T00:00:00",
  "end": null,
  "adjust": "none"
}
```

## 4. 验证

```powershell
pytest
ruff check .
```

## 生产演进路线

1. 标的主数据、交易日历、停复牌和除权除息校验。
2. 实时订阅进程、断线重连、心跳、数据延迟和缺口告警。
3. Tick/分钟数据迁移到 ClickHouse，PostgreSQL 保存任务与权限元数据。
4. 因子注册、版本管理、截面计算和数据质量报告。
5. 独立 `XtQuantTrader` 交易网关及强制风控，不与研究 API 混跑。
6. Prometheus/Grafana 监控、定时调度和备份恢复演练。
