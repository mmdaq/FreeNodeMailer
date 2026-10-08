"""定时任务专用入口：强制 UTF-8 输出，避免中文日志在 cmd 重定向时乱码。

Task Scheduler 调用 run.bat → `python scripts/runner.py`，
本脚本用 utf-8 重新包装 stdout/stderr，并记录进程退出码到日志尾部。
"""
from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _force_utf8() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        buf = getattr(stream, "buffer", None)
        if buf is not None:
            setattr(sys, name, io.TextIOWrapper(buf, encoding="utf-8", errors="replace",
                                                line_buffering=True))


def main() -> int:
    _force_utf8()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        import main as app
    except ImportError as exc:  # 依赖缺失时给出明确提示
        print(f"[FATAL] 无法导入主程序：{exc}")
        print("请先执行：pip install -r requirements.txt")
        return 1
    started = time.time()
    try:
        rc = app.main(sys.argv[1:])
    except KeyboardInterrupt:
        print("[FATAL] 被用户中断")
        rc = 130
    except Exception as exc:  # noqa: BLE001 - 兜底，保证退出码可读
        import traceback
        traceback.print_exc()
        print(f"[FATAL] 未捕获异常：{type(exc).__name__}: {exc}")
        rc = 99
    print(f"[runner] 退出码 {rc}，总耗时 {time.time() - started:.1f}s")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
