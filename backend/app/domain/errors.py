"""Domain errors.

Hexagonal rule: the domain raises its own errors; adapters translate theirs
into these. Nothing outside ``app.domain`` may raise a domain error.
"""
from __future__ import annotations


class AlphaForgeError(Exception):
    """Base class for every error this application raises on purpose."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class SymbolNotFoundError(AlphaForgeError):
    code = "SYMBOL_NOT_FOUND"
    http_status = 404


class DelistedError(AlphaForgeError):
    code = "SYMBOL_DELISTED"
    http_status = 422


class SuspendedError(AlphaForgeError):
    """The security is currently suspended: no tradeable bar to act on."""

    code = "SYMBOL_SUSPENDED"
    http_status = 422


class InsufficientDataError(AlphaForgeError):
    code = "INSUFFICIENT_DATA"
    http_status = 422


class UpstreamDataError(AlphaForgeError):
    """Every data source in the chain failed or returned garbage."""

    code = "UPSTREAM_DATA_ERROR"
    http_status = 502


class TaskNotFoundError(AlphaForgeError):
    code = "TASK_NOT_FOUND"
    http_status = 404


class TaskNotReadyError(AlphaForgeError):
    """The task exists but has not produced a verdict yet."""

    code = "TASK_NOT_READY"
    http_status = 409


class TooManyConnectionsError(AlphaForgeError):
    code = "TOO_MANY_CONNECTIONS"
    http_status = 429


class GraphExecutionError(AlphaForgeError):
    code = "GRAPH_EXECUTION_ERROR"
    http_status = 500
