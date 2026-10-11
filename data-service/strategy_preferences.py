"""Explicit paper-account binding to a user's cloud weights; no global last-user wins."""
from __future__ import annotations

import json
import math
import os
from sqlalchemy import text
import db


def normalize_weights(payload: dict) -> dict[str, float]:
    config = payload.get("config")
    if not isinstance(config, dict):
        raise ValueError("invalid cloud weight configuration")
    result = {}
    for key, item in config.items():
        if not isinstance(item, dict) or not isinstance(item.get("enabled"), bool):
            raise ValueError("invalid strategy setting")
        value = item.get("weight")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1000:
            raise ValueError("invalid strategy weight")
        result[str(key)] = float(value) if item["enabled"] else 0.0
    return result


def paper_weights(defaults: dict[str, float]) -> dict[str, float]:
    """Unbound shared paper account stays on defaults. A broken binding fails closed."""
    owner = os.environ.get("PAPER_WEIGHT_USER_ID", "").strip()
    if not owner:
        return defaults
    if not owner.isdigit() or int(owner) <= 0:
        raise ValueError("PAPER_WEIGHT_USER_ID must be a positive user ID")
    engine = db.get_engine()
    if engine is None:
        raise RuntimeError("cloud weights unavailable; paper rebalance aborted")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT config_json FROM user_strategy_config WHERE user_id=:uid"),
                           {"uid": int(owner)}).fetchone()
    if not row:
        raise RuntimeError("bound user has no saved cloud weights; paper rebalance aborted")
    payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    saved = normalize_weights(payload)
    # Same as the UI: future/unknown strategies excluded, missing registered IDs retain defaults.
    # Cloud/UI weights are percentage points (12); registry weights are ratios (.12).
    # Convert before merging so a newly registered strategy keeps the same units.
    return {sid: saved[sid] / 100.0 if sid in saved else weight
            for sid, weight in defaults.items()}
