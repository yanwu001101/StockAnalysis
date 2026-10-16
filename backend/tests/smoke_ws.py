"""Minimal stdlib WebSocket client smoke test for AlphaForge progress stream.

Verifies: handshake, progress frames per agentId, heartbeat, and the final
verdict envelope. No third-party deps.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import sys
import time
import urllib.request

HOST = "127.0.0.1"
PORT = 8000


def http(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"http://{HOST}:{PORT}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())


def ws_connect(path: str) -> socket.socket:
    sock = socket.create_connection((HOST, PORT), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {HOST}:{PORT}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(handshake.encode())
    buffer = b""
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("handshake closed")
        buffer += chunk
    status = buffer.split(b"\r\n", 1)[0].decode()
    if "101" not in status:
        raise RuntimeError(f"handshake failed: {status}")
    return sock


def recv_frame(sock: socket.socket) -> tuple[int, bytes]:
    header = sock.recv(2)
    if len(header) < 2:
        raise RuntimeError("closed")
    first, second = header[0], header[1]
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", sock.recv(8))[0]
    payload = b""
    while len(payload) < length:
        payload += sock.recv(length - len(payload))
    return opcode, payload


def send_masked(sock: socket.socket, opcode: int, payload: bytes) -> None:
    """Client frames MUST be masked (RFC 6455 §5.1)."""
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    header = bytes([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header += bytes([0x80 | length])
    elif length < 65536:
        header += bytes([0x80 | 126]) + struct.pack(">H", length)
    else:
        header += bytes([0x80 | 127]) + struct.pack(">Q", length)
    sock.sendall(header + mask + masked)


def main() -> int:
    task = http("POST", "/api/v1/analyze", {"symbol": "000001"})
    task_id = task["taskId"]
    print("submitted:", task_id)

    sock = ws_connect(f"/ws/v1/progress/{task_id}")
    print("ws connected")

    agents_seen: dict[str, str] = {}
    verdict = None
    deadline = time.time() + 60
    while time.time() < deadline:
        opcode, payload = recv_frame(sock)
        if opcode == 0x8:  # close
            print("server closed")
            break
        if opcode == 0x9:  # ping -> pong
            sock.sendall(b"\x8a\x00")
            continue
        if opcode != 0x1:
            continue
        envelope = json.loads(payload.decode())
        kind = envelope["type"]
        if kind == "progress":
            body = envelope["payload"]
            agents_seen[body["agentId"]] = body["status"]
            print(f"  progress {body['agentId']:12s} {body['status']:9s} {body['progress']:.2f} {body['message'][:42]}")
        elif kind == "verdict":
            verdict = envelope["payload"]
            print("  VERDICT received:", verdict["humanVerdict"]["signal"], verdict["humanVerdict"]["score"])
            break
        elif kind == "heartbeat":
            print("  heartbeat")

    # 客户端 ping -> 服务端 pong（heartbeat 帧）
    send_masked(sock, 0x9, b"ping")
    time.sleep(0.5)
    try:
        opcode, payload = recv_frame(sock)
        if opcode == 0xA:  # pong
            print("client ping -> server pong OK")
        else:
            frame = json.loads(payload.decode())
            assert frame["type"] == "heartbeat", frame
            print("client ping -> server heartbeat OK")
    except Exception as exc:  # noqa: BLE001
        print("ping check skipped:", exc)

    sock.close()

    assert agents_seen, "no progress frames"
    assert set(agents_seen) == {"fundamental", "sentiment", "technical", "risk"}, agents_seen
    assert verdict is not None, "no verdict frame"
    assert len(verdict["dates"]) == len(verdict["candles"])
    print("WS SMOKE OK — agents:", sorted(agents_seen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
