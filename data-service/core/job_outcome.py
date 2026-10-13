"""Versioned, serializable outcomes for migrated maintenance jobs only.

Older jobs returning None are outside this contract. A caller must check
outcome_version == 1 before interpreting this shape. Row counts mean reported
upsert rows (not newly inserted rows and not a freshness guarantee).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Integral
from typing import Awaitable, Callable


OUTCOME_VERSION = 1


@dataclass
class JobOutcome:
    job: str
    universe_size: int = 0
    steps: list[dict] = field(default_factory=list)

    def failed(self, name: str, error: object) -> None:
        self.steps.append({"name": name, "status": "failed", "rows": 0,
                           "error": str(error)[:500]})

    def skipped(self, name: str, reason: str) -> None:
        self.steps.append({"name": name, "status": "skipped", "rows": 0, "reason": reason})

    async def run_step(self, name: str, work: Callable[[], Awaitable[int]]) -> None:
        try:
            value = await work()
            # A DataFrame/dict/None/bool is not a row count. In particular, do
            # not call bool(DataFrame), len(dict), or int(None or 0).
            if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
                raise ValueError(f"管线未返回有效写入行数（{type(value).__name__}）")
            rows = int(value)
            if rows == 0:
                self.skipped(name, "no_rows")
            else:
                self.steps.append({"name": name, "status": "success", "rows": rows})
        except Exception as error:
            self.failed(name, error)

    def finish(self) -> dict:
        rows = sum(step["rows"] for step in self.steps)
        incomplete = [s for s in self.steps if s["status"] == "failed" or s.get("reason") == "no_rows"]
        status = "failed" if rows == 0 else "partial" if incomplete else "success"
        out = {"outcome_version": OUTCOME_VERSION, "job": self.job,
               "status": status, "rows": rows, "universe_size": self.universe_size,
               "row_semantics": "reported_upsert_rows_not_freshness",
               "steps": [dict(step) for step in self.steps]}
        if status != "success":
            out["error"] = "未写入任何数据，请检查任务明细" if rows == 0 else "部分管线失败或未写入数据，请检查任务明细"
            if rows == 0:
                out["reason"] = "no_rows"
        return out


def skipped_outcome(job: str, reason: str) -> dict:
    return {"outcome_version": OUTCOME_VERSION, "job": job, "status": "skipped",
            "rows": 0, "universe_size": 0, "reason": reason,
            "row_semantics": "reported_upsert_rows_not_freshness",
            "steps": [{"name": "schedule", "status": "skipped", "rows": 0, "reason": reason}]}


def failed_outcome(job: str, name: str, error: object) -> dict:
    outcome = JobOutcome(job)
    outcome.failed(name, error)
    return outcome.finish()
