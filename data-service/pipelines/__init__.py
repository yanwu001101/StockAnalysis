# -*- coding: utf-8 -*-
"""Pipelines orchestrate `sources/` -> validate -> `repo/`.

Each pipeline module exposes `run()` (or `run_batch(codes)` for code-scoped feeds)
that the scheduler can call independently.
"""
