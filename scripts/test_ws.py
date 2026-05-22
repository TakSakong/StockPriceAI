#!/usr/bin/env python3
"""WebSocket 진행률 수신 테스트 (test_local.sh에서 호출)"""
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("ERROR: pip install websockets")
    sys.exit(1)

JOB_ID = sys.argv[1] if len(sys.argv) > 1 else ""
if not JOB_ID:
    print("사용법: python3 test_ws.py <job_id>")
    sys.exit(1)

URI = f"ws://localhost/ws/scanner/{JOB_ID}"
MAX_MESSAGES = 5
TIMEOUT = 15


async def watch():
    try:
        async with websockets.connect(URI, open_timeout=TIMEOUT) as ws:
            for _ in range(MAX_MESSAGES):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                    data = json.loads(raw)
                    status = data.get("status", "?")
                    done = data.get("done", 0)
                    total = data.get("total", "?")
                    print(f"[{status}] {done}/{total}")
                    if status in ("completed", "failed"):
                        break
                except asyncio.TimeoutError:
                    print("[timeout] 메시지 수신 대기 초과")
                    break
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


asyncio.run(watch())
