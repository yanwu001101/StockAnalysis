"""Reject partial price-basis rewrites; never scale old prices using a guessed factor."""
from __future__ import annotations
import numpy as np
import pandas as pd


def needs_full_refresh(existing: pd.DataFrame, incoming: pd.DataFrame) -> bool:
    if existing.empty or incoming.empty:
        return False
    old = existing.set_index('trade_date')['close'].astype(float)
    new = incoming.set_index('trade_date')['close'].astype(float)
    old.index = pd.to_datetime(old.index).date
    new.index = pd.to_datetime(new.index).date
    old, new = old[~old.index.duplicated(keep='last')], new[~new.index.duplicated(keep='last')]
    overlap = old.index.intersection(new.index)
    if not len(overlap):
        # With no overlap we cannot verify an adjustment anchor for an existing series.
        return True
    a, b = old.loc[overlap], new.loc[overlap]
    valid = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
    if not valid.any():
        return True
    changed = ((a[valid] - b[valid]).abs() > np.maximum(.005, a[valid].abs() * .0005)).any()
    covered = set(old.index).issubset(set(new.index[np.isfinite(new) & (new > 0)]))
    return bool(changed and not covered)
