"""Authenticate the Java gateway's research-job ownership context.

This is not a JWT supplied by a browser. The gateway signs authenticated owner,
timestamp, method, path and the exact wire body using a domain-separated key.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections.abc import Mapping

DOMAIN = b"research-jobs-v1"
PUBLIC_DEFAULT = "StockScreenerSecretKey2024MustBe256BitsLong!!"
MAX_CLOCK_SKEW_S = 60
MAX_BODY_BYTES = 256 * 1024
OWNER_HEADER = "X-Research-Owner"
TIME_HEADER = "X-Research-Timestamp"
SIGNATURE_HEADER = "X-Research-Signature"
CONFIG_ERROR = "研究任务鉴权未配置：两端 JWT_SECRET 必须相同、至少 32 字节且不是公共默认值"


class AuthUnavailable(RuntimeError):
    pass


class InvalidContext(ValueError):
    pass


def validate_secret(secret: str) -> bytes:
    if not isinstance(secret, str) or not secret.strip() or secret.strip() == PUBLIC_DEFAULT:
        raise AuthUnavailable(CONFIG_ERROR)
    raw = secret.encode("utf-8")
    if len(raw) < 32:
        raise AuthUnavailable(CONFIG_ERROR)
    return raw


def validate_owner(owner_id: int) -> int:
    if type(owner_id) is not int or not 0 < owner_id <= 2**63 - 1:
        raise InvalidContext("研究任务所有者无效")
    return owner_id


def parse_headers(headers: Mapping, *, now: float | None = None) -> tuple[int, int, str]:
    owner = headers.get(OWNER_HEADER, "")
    timestamp = headers.get(TIME_HEADER, "")
    signature = headers.get(SIGNATURE_HEADER, "")
    if (not re.fullmatch(r"[1-9][0-9]{0,18}", owner)
            or not re.fullmatch(r"[0-9]{1,12}", timestamp)
            or str(int(timestamp)) != timestamp
            or not re.fullmatch(r"[0-9a-f]{64}", signature)):
        raise InvalidContext("研究任务身份签名无效")
    owner_id = validate_owner(int(owner))
    timestamp_s = int(timestamp)
    if abs((time.time() if now is None else now) - timestamp_s) > MAX_CLOCK_SKEW_S:
        raise InvalidContext("研究任务身份签名已过期")
    return owner_id, timestamp_s, signature


def sign_context(secret: str, owner_id: int, timestamp: int, method: str, path: str, body: bytes) -> str:
    master = validate_secret(secret)
    validate_owner(owner_id)
    key = hmac.new(master, DOMAIN, hashlib.sha256).digest()
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{owner_id}\n{timestamp}\n{method.upper()}\n{path}\n{body_hash}".encode("utf-8")
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def verify_context(secret: str, headers: Mapping, method: str, path: str, body: bytes,
                   *, now: float | None = None) -> int:
    validate_secret(secret)
    owner, timestamp, signature = parse_headers(headers, now=now)
    expected = sign_context(secret, owner, timestamp, method, path, body)
    if not hmac.compare_digest(signature, expected):
        raise InvalidContext("研究任务身份签名无效")
    return owner
