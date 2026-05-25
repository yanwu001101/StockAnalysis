# -*- coding: utf-8 -*-
"""Strategy-score warmup job.

Scans the current spot snapshot, scores every code against every registered
strategy, and persists the result. The dashboard "各策略 Top 榜" then becomes
a millisecond SELECT (indexed on strategy_id, score) instead of a 3-5 minute
on-demand evaluation.

Cadence: hooks into the post-market schedule so end-of-day numbers reflect
that day's close. Can also be triggered manually via /api/admin/warmup.
"""
from __future__ import annotations

import time

import pandas as pd

import cache
from core.trace import logger
from repo import strategy_score_repo
from strategies import REGISTRY
from api.strategies_v2 import _load_ctx, _score_all


# Larger universes give a more complete picture but cost linearly. 0 = all.
_DEFAULT_UNIVERSE = 0


def _select_universe(top_n: int) -> list[str]:
    df = cache.get("spot")
    if df is None or not hasattr(df, "columns"):
        # Bootstrap if spot cache is cold (fresh worker, no dashboard hits yet)
        try:
            from app import fetch_spot
            df = fetch_spot()
        except Exception:
            df = None
    if df is None or not hasattr(df, "columns") or "代码" not in df.columns:
        return []
    out = df.copy()
    cap_col = "总市值_亿" if "总市值_亿" in out.columns else None
    if cap_col:
        out[cap_col] = pd.to_numeric(out[cap_col], errors="coerce")
        out = out.sort_values(cap_col, ascending=False, na_position="last")
    codes = out["代码"].astype(str).str.zfill(6).tolist()
    if top_n and top_n > 0:
        codes = codes[:top_n]
    return codes


def run(top_n: int = _DEFAULT_UNIVERSE) -> int:
    """Score every code in the chosen universe slice, upsert rows.

    Returns the number of (code, strategy) rows written.
    """
    codes = _select_universe(top_n)
    if not codes:
        logger.warning("[strategy_score] empty universe — is spot cached?")
        return 0

    started = time.time()
    rows: list[dict] = []
    batch_size = 100
    total = len(codes)
    logger.info("[strategy_score] scoring %d codes × %d strategies", total, len(REGISTRY))

    for i, code in enumerate(codes):
        try:
            ctx = _load_ctx(code)
            # _score_all returns (composite, signal, out_dict, out_list). out_list
            # carries one entry per strategy with score/signal/triggered.
            _, _, _, out_list = _score_all(ctx)
            for it in out_list:
                score = float(it.get("score") or 0)
                # Skip zero scores — they pollute the table with no-data rows
                # and would never appear in any top-N anyway.
                if score <= 0:
                    continue
                rows.append({
                    "code": code,
                    "strategy_id": it["id"],
                    "score": round(score, 2),
                    "signal_type": it.get("signal") or "neutral",
                    "triggered": 1 if it.get("triggered") else 0,
                })
        except Exception as e:
            logger.debug("[strategy_score] %s failed: %s", code, e)

        # Flush in batches so a crash mid-scan still keeps partial progress
        if len(rows) >= batch_size * len(REGISTRY):
            strategy_score_repo.upsert_scores(pd.DataFrame(rows))
            rows.clear()
            elapsed = time.time() - started
            done = i + 1
            eta = elapsed / done * (total - done)
            logger.info("[strategy_score] %d/%d codes scored, eta %.0fs", done, total, eta)

    if rows:
        strategy_score_repo.upsert_scores(pd.DataFrame(rows))

    elapsed = time.time() - started
    written = strategy_score_repo.row_count()
    logger.info("[strategy_score] DONE %d codes in %.1fs, table now has %d rows",
                total, elapsed, written)
    return written
