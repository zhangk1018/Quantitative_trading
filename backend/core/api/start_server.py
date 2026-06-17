#!/usr/bin/env python3
"""
start_server.py - uvicorn 启动器（支持自动 workers 数量）

读取 UVICORN_WORKERS 环境变量：
  - 未设置 / "auto" → workers = CPU核数 * 2 + 1
  - 正整数         → 使用指定值
  - "1"            → 单 worker（debug 模式）

Usage（Dockerfile ENTRYPOINT）:
  ENTRYPOINT ["sh", "-c", "python /app/backend/core/api/start_server.py"]
"""
import os
import math
import subprocess
import sys


def get_workers_from_env() -> int:
    """从环境变量解析 workers 数量。"""
    val = os.environ.get("UVICORN_WORKERS", "auto").strip().lower()
    if val in ("", "auto"):
        # 公式：2 * CPU核数 + 1（标准 gunicorn/uvicorn 调优公式）
        cpu_count = os.cpu_count() or 1
        workers = 2 * cpu_count + 1
        print(f"[start_server] UVICORN_WORKERS=auto → CPU={cpu_count}核 → workers={workers}")
        return workers
    try:
        n = int(val)
        if n <= 0:
            raise ValueError("must be positive")
        print(f"[start_server] UVICORN_WORKERS={n}（用户指定）")
        return n
    except ValueError:
        print(f"[start_server] UVICORN_WORKERS={val!r} 无效，使用 auto")
        cpu_count = os.cpu_count() or 1
        return 2 * cpu_count + 1


def main():
    workers = get_workers_from_env()
    debug = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    log_level = os.environ.get("LOG_LEVEL", "info")

    # 构建 uvicorn 命令
    cmd = [
        "uvicorn",
        "backend.core.api.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--workers", str(workers),
        "--proxy-headers",
        "--forwarded-allow-ips", "*",
    ]

    # debug=True 时降级为单 worker + reload（方便本地开发）
    if debug:
        cmd[cmd.index("--workers") + 1] = "1"
        cmd.extend(["--reload", "--log-level", "debug"])
        print(f"[start_server] DEBUG=1 → 单 worker + reload 模式")
    else:
        cmd.extend(["--access-log", "--log-level", log_level])

    print(f"[start_server] 启动: {' '.join(cmd)}")
    sys.stdout.flush()
    sys.stderr.flush()
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
