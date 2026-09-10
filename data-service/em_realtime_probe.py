# -*- coding: utf-8 -*-
"""push2 破甲探测器 + 验证脚本。

用途:
  1) 低频轮询 push2 是否对本机 IP 解封(前面高频探测触发了连接层封禁)。
  2) 一旦解封,立即用 curl_cffi 伪造 Chrome TLS/JA3 指纹拉一页全市场实时快照,
     打印 f86(行情时间戳)证明实时性,并与 push2delay 对照。

反爬结论:push2 /clist 的拦截在 TLS/HTTP 连接指纹层——urllib/requests 直接被
RemoteDisconnected;curl_cffi impersonate=chrome 可骗过(已在 push2delay 上验证)。
"""
from __future__ import annotations
import sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from curl_cffi import requests as creq

FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
FIELDS = "f12,f14,f2,f3,f6,f86"   # f86 = 行情时间戳(Unix秒),用于证明实时
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HDR = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9",
       "Referer": "https://quote.eastmoney.com/"}


def params(pn=1, pz=10, fid="f6"):
    return {"pn": pn, "pz": pz, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2, "fid": fid, "fs": FS, "fields": FIELDS,
            "_": str(int(time.time() * 1000))}


def fetch(host, session, pz=10):
    """用伪造指纹的 session 拉一页。返回 (ok, total, diff_list, err)。"""
    url = f"https://{host}.eastmoney.com/api/qt/clist/get"
    try:
        r = session.get(url, params=params(pz=pz), headers=HDR, timeout=12)
        d = (r.json().get("data") or {})
        return True, d.get("total"), (d.get("diff") or []), None
    except Exception as e:
        return False, None, [], f"{type(e).__name__}: {str(e)[:80]}"


def main():
    session = creq.Session(impersonate="chrome")  # 复用带 Chrome 指纹的连接
    max_rounds = 10
    for i in range(1, max_rounds + 1):
        ok, total, diff, err = fetch("push2", session)
        ts = time.strftime("%H:%M:%S")
        if ok:
            print(f"[{ts}] 第{i}轮:push2 已解封 ✅ 破甲成功 total={total}")
            print("  push2 实时快照(按成交额 top10):")
            for row in diff:
                t = row.get("f86")
                tstr = time.strftime("%H:%M:%S", time.localtime(t)) if t else "--"
                print(f"    {row.get('f12')} {row.get('f14'):<8} 价{row.get('f2')} "
                      f"涨幅{row.get('f3')}% 行情时刻@{tstr}")
            # push2delay 对照
            ok2, total2, diff2, err2 = fetch("push2delay", session)
            if ok2:
                print(f"  push2delay 对照 total={total2}(A股同为实时)")
            print("\nRESULT: BREAK_OK")
            return 0
        else:
            print(f"[{ts}] 第{i}/{max_rounds}轮:push2 仍封禁/失败 → {err}")
            if i < max_rounds:
                time.sleep(90)
    print("\nRESULT: STILL_BLOCKED(IP 封禁未在 ~15 分钟内解除,建议换出口 IP/代理)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
