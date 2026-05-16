# -*- coding: utf-8 -*-
"""core/ — infrastructure shared by every data source.

Module map:
  http_client : httpx-based async HTTP with rate-limit / retry / circuit / cookies
  ratelimit   : per-domain token bucket, adapts to 429/418/403
  retry       : tenacity decorator distinguishing transient vs fatal errors
  circuit     : per-source breaker (closed -> open -> half-open)
  headers     : User-Agent / Referer / Cookie pools
  proxy       : optional proxy pool from PROXY_POOL_URL
  browser     : playwright for JS-encrypted endpoints (opt-in)
  parser      : jsonp / json / dataframe helpers
  trace       : structlog logger + Prometheus metrics
"""
