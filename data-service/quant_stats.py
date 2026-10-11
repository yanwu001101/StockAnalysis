"""Shared, finite-only research statistics. Missing evidence is never zero."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
from scipy.stats import t as student_t


def finite_pairs(a: pd.Series, b: pd.Series) -> pd.DataFrame:
    return pd.concat([a.rename("factor"), b.rename("return")], axis=1, join="inner").apply(
        pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def ic_summary(values) -> dict:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    out = {"mean": None, "std": None, "icir": None, "positive_ratio": None,
           "negative_ratio": None, "t_stat": None, "p_value": None, "n": n,
           "status": "INSUFFICIENT_DATA" if n < 12 else "VALID",
           "p_method": "two-sided Student t, df=n-1; assumes independent periods"}
    if not n:
        return out
    mean = float(x.mean())
    std = float(x.std(ddof=1)) if n > 1 else None
    out.update(mean=round(mean, 8), std=round(std, 8) if std is not None else None,
               positive_ratio=float(np.mean(x > 0)), negative_ratio=float(np.mean(x < 0)))
    if std is not None and std > 1e-12:
        t_stat = mean / std * math.sqrt(n)
        out.update(icir=round(mean / std, 8), t_stat=round(t_stat, 8),
                   p_value=float(2 * student_t.sf(abs(t_stat), df=n - 1)))
    else:
        out["status"] = "INSUFFICIENT_DATA"
    return out


def chronological_validation(rows: list[dict], window: int = 60) -> dict:
    """70/30 chronological holdout; fit direction on training data only.

    This is a holdout diagnostic of a pre-specified factor, not a guarantee
    of independence after repeatedly choosing expressions on the same data.
    """
    valid = [r for r in rows if r.get("ic") is not None and np.isfinite(r["ic"])]
    split = int(len(valid) * 0.7)
    train, test = valid[:split], valid[split:]
    # Purge labels crossing the first holdout signal date (for overlapping labels).
    if test:
        boundary = test[0]["date"]
        train = [r for r in train if r.get("return_end", r["date"]) < boundary]
    train_summary = ic_summary([r["ic"] for r in train])
    test_summary = ic_summary([r["ic"] for r in test])
    mean = train_summary["mean"]
    sign = -1 if mean is not None and mean < 0 else 1
    normalized = ic_summary([r["ic"] * sign for r in test])
    consistent = None if mean is None or not test else (
        mean != 0 and test_summary["mean"] * sign > 0)
    rolling = []
    for i in range(window - 1, len(valid)):
        block = valid[i - window + 1:i + 1]
        summary = ic_summary([r["ic"] for r in block])
        rolling.append({"date": valid[i]["date"], "start": block[0]["date"], **summary})
    return {"split_ratio": 0.7, "direction_sign": sign, "direction_source": "TRAIN_ONLY",
            "train": {"start": train[0]["date"] if train else None,
                      "end": train[-1]["date"] if train else None, **train_summary},
            "test": {"start": test[0]["date"] if test else None,
                     "end": test[-1]["date"] if test else None, **test_summary},
            "normalized_test": normalized, "direction_consistent": consistent,
            "status": "VALID" if len(train) >= 24 and len(test) >= 12 else "INSUFFICIENT_DATA",
            "rolling_window": window, "rolling": rolling,
            "note": "按时间前70%确定方向、后30%验证；跨边界收益已剔除。反复挑选因子后不再是独立样本外。"}


def equal_weight_turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    """One-way turnover including cash; 100% replacement = 1, not Jaccard."""
    keys = previous.keys() | current.keys()
    cash_change = abs((1 - sum(previous.values())) - (1 - sum(current.values())))
    return 0.5 * (sum(abs(current.get(k, 0) - previous.get(k, 0)) for k in keys) + cash_change)


def cap_bucket_demean(scores: pd.Series, caps: pd.Series, buckets: int = 10) -> pd.Series:
    """Current-cap sensitivity only; callers must not use this as PIT evidence."""
    pairs = finite_pairs(scores, caps)
    pairs = pairs[pairs["return"] > 0]
    if len(pairs) < buckets * 2:
        return pd.Series(dtype=float)
    groups = pd.qcut(pairs["return"].rank(method="first"), buckets, labels=False)
    return pairs["factor"] - pairs["factor"].groupby(groups).transform("mean")
