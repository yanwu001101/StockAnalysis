"""Shared snapshot-to-universe rules for maintenance jobs.

top_n <= 0 means all eligible stocks, never pandas.head(0). A positive limit
requires market-cap data so an arbitrary provider order cannot masquerade as
the largest-N universe. If an amount column is present, activity requires a
finite positive value; without that column, activity remains unverified.
"""
from __future__ import annotations

import pandas as pd


def select_codes(snapshot: pd.DataFrame | None, top_n: int = 0) -> list[str]:
    if snapshot is None or snapshot.empty:
        return []
    code_col = next((c for c in ("code", "代码") if c in snapshot.columns), None)
    if code_col is None:
        raise ValueError("行情快照缺少股票代码列")
    data = snapshot.copy()
    data["_code"] = (data[code_col].astype("string").str.strip()
                     .str.replace(r"\.0$", "", regex=True).str.zfill(6))
    data = data[data["_code"].str.fullmatch(r"\d{6}", na=False)]
    amount_col = next((c for c in ("amount", "成交额") if c in data.columns), None)
    if amount_col:
        amount = pd.to_numeric(data[amount_col], errors="coerce")
        data = data[(amount > 0) & (amount < float("inf"))]
    cap_col = next((c for c in ("market_cap_yi", "market_cap", "总市值_亿", "总市值")
                    if c in data.columns), None)
    if cap_col:
        data["_cap"] = pd.to_numeric(data[cap_col], errors="coerce").replace(
            [float("inf"), -float("inf")], float("nan"))
        data = data.sort_values(["_cap", "_code"], ascending=[False, True], na_position="last")
    elif top_n > 0:
        raise ValueError("行情快照缺少市值列，无法按市值限制股票池")
    else:
        data = data.sort_values("_code")
    codes = data["_code"].drop_duplicates().tolist()
    return codes[:top_n] if top_n > 0 else codes
