# -*- coding: utf-8 -*-
"""Intraday job (every 5 min during trading hours).

Refreshes the spot cache. Cheap and frequent — kept tight to avoid stepping on
pre/post market work.
"""
from __future__ import annotations
import asyncio

from core.trace import logger
from pipelines import spot as spot_pipe


async def run_async() -> None:
    try:
        await spot_pipe.run()
    except Exception as e:
        logger.warning("[job:intraday] spot refresh failed: %s", e)


def run() -> None:
    asyncio.run(run_async())
