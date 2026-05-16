# -*- coding: utf-8 -*-
"""Unified response parsers: jsonp / json / dataframe utilities.

Most A-share data endpoints return either JSON wrapped in a JSONP callback or
raw JSON. This module gives a single resilient entry point so source adapters
don't each reinvent regex stripping.
"""
from __future__ import annotations
import json
import re
from typing import Any

import pandas as pd

try:
    import orjson
    def _loads(b: bytes | str) -> Any:
        if isinstance(b, str):
            b = b.encode("utf-8")
        return orjson.loads(b)
except Exception:
    def _loads(b: bytes | str) -> Any:
        if isinstance(b, bytes):
            b = b.decode("utf-8", errors="replace")
        return json.loads(b)


_JSONP_RE = re.compile(r"^[^=({\[]*[=({]\s*", re.DOTALL)


def parse_jsonp(text: str) -> Any:
    """Strip `callback(...)` / `var x = ...;` JSONP wrappers and return parsed JSON.

    Returns None when the body is not valid after stripping.
    """
    if not text:
        return None
    body = text.strip()
    # Quick path: starts with { or [
    if body and body[0] in "{[":
        try:
            return _loads(body)
        except Exception:
            pass
    # Slow path: strip leading `name(` or `var x =` and trailing `);` / `;`
    m = _JSONP_RE.match(body)
    if m:
        body = body[m.end():]
    body = body.rstrip("; \t\r\n")
    if body.endswith(")"):
        body = body[:-1]
    try:
        return _loads(body)
    except Exception:
        return None


def parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return _loads(text)
    except Exception:
        return None


def empty_df() -> pd.DataFrame:
    return pd.DataFrame()


def to_numeric_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Coerce listed columns to numeric, leaving missing cols untouched."""
    if df is None or df.empty:
        return df
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(
                df[c].astype(str)
                     .str.replace("%", "", regex=False)
                     .str.replace(",", "", regex=False),
                errors="coerce",
            )
    return df


def normalize_code(value: Any) -> str:
    s = str(value or "").strip()
    digits = re.sub(r"\D", "", s)
    return digits.zfill(6)[-6:]
