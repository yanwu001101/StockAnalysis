"""REST routes (command side + query side of the CQRS split).

* ``POST /api/v1/analyze`` — command: mint a task, schedule the graph run.
* ``GET  /api/v1/result/{taskId}`` — query: the verdict, once it exists.
* ``GET  /api/v1/tasks/{taskId}`` — query: task status (progress lives on the
  WebSocket, this endpoint is for pollers and debugging).
* ``GET  /health`` / ``GET /ready`` — liveness and dependency readiness.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    Container,
    get_command_service,
    get_container,
    get_market_data,
    get_query_service,
    get_repository,
)
from app.config import get_settings
from app.domain.models import AnalyzeRequest, AnalyzeResponse, AnalysisTask
from app.domain.models import MarketOverview, QuantVerdictPayload, SystemStats
from app.domain.ports import MarketDataPort, TaskRepositoryPort
from app.services.analysis_service import AnalysisCommandService, AnalysisQueryService

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    status_code=201,
    summary="提交分析任务",
    response_description="任务已创建，通过 WebSocket 或 /result 获取结论",
)
async def analyze(
    body: AnalyzeRequest,
    commands: AnalysisCommandService = Depends(get_command_service),
) -> AnalyzeResponse:
    # async def on purpose: submit() schedules the graph run with
    # asyncio.create_task, which requires the request's own event loop.
    task = commands.submit(body.symbol, body.backtest)
    return AnalyzeResponse(task_id=task.task_id, symbol=task.symbol, status=task.status)


@router.get(
    "/result/{task_id}",
    response_model=QuantVerdictPayload,
    summary="获取分析结论",
    responses={404: {"description": "任务不存在"}, 409: {"description": "任务尚未完成"}},
)
def get_result(
    task_id: str,
    queries: AnalysisQueryService = Depends(get_query_service),
) -> QuantVerdictPayload:
    return queries.get_verdict(task_id)


@router.get(
    "/tasks/{task_id}",
    response_model=AnalysisTask,
    summary="查询任务状态",
    responses={404: {"description": "任务不存在"}},
)
def get_task(
    task_id: str,
    queries: AnalysisQueryService = Depends(get_query_service),
) -> AnalysisTask:
    return queries.get(task_id)


@router.get("/stats", response_model=SystemStats, summary="智能体舰队统计（驾驶舱）")
def stats(repository: TaskRepositoryPort = Depends(get_repository)) -> SystemStats:
    return repository.stats()


@router.get(
    "/market/overview",
    response_model=MarketOverview,
    summary="市场概览（基准指数 + 涨跌家数）",
)
def market_overview(
    market_data: MarketDataPort = Depends(get_market_data),
) -> MarketOverview:
    settings = get_settings()
    return market_data.fetch_market_overview(settings.benchmark_symbol)


health_router = APIRouter(tags=["ops"])


@health_router.get("/health", summary="存活探针")
def health() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/ready", summary="就绪探针（依赖健康检查）")
def ready(container: Container = Depends(get_container)) -> dict[str, object]:
    checks = container.health()
    degraded = {name: ok for name, ok in checks.items() if not ok}
    return {
        "status": "ready" if not degraded else "degraded",
        "checks": checks,
        "note": "degraded = 依赖不可用，已降级为内存模式运行",
    }


__all__ = ["router", "health_router", "AlphaForgeError"]
