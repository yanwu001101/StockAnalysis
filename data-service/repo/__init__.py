# -*- coding: utf-8 -*-
"""Persistence layer.

Each repo wraps a single MySQL table with upsert + read helpers. All upserts
are idempotent (ON DUPLICATE KEY UPDATE). Reads return pandas DataFrames.
"""
