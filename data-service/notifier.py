# -*- coding: utf-8 -*-
"""Webhook notifications: job failure alerts + daily summary push.

Config via environment:
  ALERT_WEBHOOK_URL   — 机器人/自定义 webhook 完整地址（空 = 关闭推送）
  ALERT_WEBHOOK_TYPE  — wecom | dingtalk | feishu | raw（空 = 按 URL 自动识别）

Supported channels:
  wecom    企业微信机器人   https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...
  dingtalk 钉钉机器人       https://oapi.dingtalk.com/robot/send?access_token=...
  feishu   飞书自定义机器人 https://open.feishu.cn/open-apis/bot/v2/hook/...
  raw      自定义接收器     POST {"title", "content"} JSON

Fail-safe by contract: 推送失败只打日志，绝不向上抛 — 通知问题不能影响任务本身。
"""
from __future__ import annotations
import json
import urllib.request

from config import settings
from core.trace import logger

_TIMEOUT_S = 6


def _detect_type(url: str) -> str:
    t = (getattr(settings, "alert", None) and settings.alert.webhook_type) or ""
    if t:
        return t
    u = url.lower()
    if "qyapi.weixin.qq.com" in u:
        return "wecom"
    if "oapi.dingtalk.com" in u:
        return "dingtalk"
    if "open.feishu.cn" in u:
        return "feishu"
    return "raw"


def _payload(kind: str, title: str, md: str) -> str:
    if kind == "wecom":
        return json.dumps({"msgtype": "markdown", "markdown": {"content": md}})
    if kind == "dingtalk":
        return json.dumps({"msgtype": "markdown", "markdown": {"title": title, "text": md}})
    if kind == "feishu":
        # 飞书文本消息不支持 markdown，退化为纯文本
        plain = md.replace("**", "").replace(">", "").replace("<font color=\"warning\">", "").replace("</font>", "")
        return json.dumps({"msg_type": "text", "content": {"text": f"{title}\n{plain}"}})
    return json.dumps({"title": title, "content": md})


def send_markdown(title: str, md: str) -> bool:
    """推送 markdown 消息到配置的 webhook。返回是否成功；绝不抛异常。"""
    url = (getattr(settings, "alert", None) and settings.alert.webhook_url) or ""
    if not url:
        logger.debug("[notifier] ALERT_WEBHOOK_URL not set — skip push: %s", title)
        return False
    try:
        kind = _detect_type(url)
        req = urllib.request.Request(
            url, data=_payload(kind, title, md).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
            ok = 200 <= r.status < 300
        if not ok:
            logger.warning("[notifier] push %s -> HTTP %s", title, r.status)
        return ok
    except Exception as e:
        logger.warning("[notifier] push failed: %s", e)
        return False


def job_failed(job: str, err: str) -> bool:
    """任务失败告警。"""
    return send_markdown(
        f"⚠️ 任务失败: {job}",
        f"**{job}** 执行失败\n> {err[:500]}\n\n请检查数据服务日志（docker logs stock-data-service）",
    )
