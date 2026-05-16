# -*- coding: utf-8 -*-
"""Metrics + health blueprint (Prometheus + circuit state)."""
from __future__ import annotations

from flask import Blueprint, Response, jsonify

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    _HAS_PROM = True
except Exception:
    _HAS_PROM = False

from core import circuit


bp = Blueprint("ops", __name__)


@bp.route("/metrics")
def metrics():
    if not _HAS_PROM:
        return Response("# prometheus_client not installed\n", mimetype="text/plain")
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@bp.route("/circuits")
def circuits():
    return jsonify(circuit.snapshot())
