# -*- coding: utf-8 -*-
# SQLAlchemy engine for data-service. Connection pool, retries, lazy init.
from __future__ import annotations
import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

log = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST", "mysql")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Stock@2024")
DB_NAME = os.getenv("DB_NAME", "stock_screener")

_engine: Engine | None = None
_engine_failed: bool = False


def _build_url() -> str:
    from urllib.parse import quote_plus
    return (
        f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )


def get_engine() -> Engine | None:
    """Return shared engine; None if MySQL unreachable (caller should fall back)."""
    global _engine, _engine_failed
    if _engine is not None:
        return _engine
    if _engine_failed:
        return None
    try:
        _engine = create_engine(
            _build_url(),
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={"connect_timeout": 5},
            future=True,
        )
        with _engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        log.info("MySQL engine ready: %s@%s:%s/%s", DB_USER, DB_HOST, DB_PORT, DB_NAME)
        return _engine
    except Exception as e:
        log.warning("MySQL unreachable, kline_repo will skip persistence: %s", e)
        _engine_failed = True
        _engine = None
        return None
