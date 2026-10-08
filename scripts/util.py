"""FreeNodeMailer 公共工具：路径、配置加载、日志。"""
from __future__ import annotations

import logging
import os
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict

import yaml

# ---------------------------------------------------------------- 路径
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"
CACHE_DIR = ROOT / ".cache"
LOG_DIR = ROOT / "logs"
CORE_DIR = CACHE_DIR / "core"
GEO_DIR = CACHE_DIR / "geo"
DATA_DIR = ROOT / "data"

LOG = logging.getLogger("fnm")


# ---------------------------------------------------------------- .env
def load_dotenv(path: Path | None = None) -> None:
    """极简 .env 读取：只填充「尚未存在」的环境变量。"""
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


# ---------------------------------------------------------------- 配置
def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# 环境变量 -> 配置路径的覆盖表
ENV_OVERRIDES = {
    "FNM_MAX_DELAY": ("test", "max_delay", int),
    "FNM_TIMEOUT_MS": ("test", "timeout_ms", int),
    "FNM_TEST_CONCURRENCY": ("test", "concurrency", int),
    "FNM_CORE_PATH": ("test", "core_path", str),
    "FNM_TEST_URL": ("test", "url", str),
    "FNM_MAX_NODES": ("select", "max_nodes", int),
    "FNM_MIN_NODES": ("select", "min_nodes", int),
    "FNM_FETCH_CONCURRENCY": ("fetch", "concurrency", int),
    "FNM_FETCH_TIMEOUT": ("fetch", "timeout", int),
    "FNM_MAIL_TO": ("mail", "to", str),
    "FNM_LOG_LEVEL": ("log", "level", str),
}


def load_settings(extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    settings: Dict[str, Any] = {}
    cfg = CONFIG_DIR / "settings.yaml"
    if cfg.exists():
        settings = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    if extra:
        settings = _deep_merge(settings, extra)
    for env_key, (sec, key, cast) in ENV_OVERRIDES.items():
        raw = os.environ.get(env_key)
        if raw is None or raw == "":
            continue
        try:
            settings.setdefault(sec, {})[key] = cast(raw)
        except (TypeError, ValueError):
            LOG.warning("环境变量 %s=%r 无法解析，已忽略", env_key, raw)
    settings.setdefault("fetch", {})
    settings.setdefault("test", {})
    settings.setdefault("select", {})
    settings.setdefault("output", {})
    settings.setdefault("mail", {})
    settings.setdefault("log", {})
    return settings


def settings_get(settings: Dict[str, Any], path: str, default: Any = None) -> Any:
    """settings_get(cfg, 'test.max_delay', 500)"""
    node: Any = settings
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return default if node is None else node


# ---------------------------------------------------------------- 日志
def setup_logging(settings: Dict[str, Any] | None = None, name: str = "fnm") -> logging.Logger:
    settings = settings or {}
    level = str(settings_get(settings, "log.level", env("FNM_LOG_LEVEL", "INFO"))).upper()
    log_dir = ROOT / str(settings_get(settings, "log.dir", "logs"))
    keep_days = int(settings_get(settings, "log.keep_days", 30))

    logger = logging.getLogger("fnm")
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = TimedRotatingFileHandler(
            log_dir / f"{name}.log", when="midnight", backupCount=keep_days, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError as exc:  # 只读环境（例如某些 CI）下忽略文件日志
        logger.warning("无法写入日志文件(%s)：%s", log_dir, exc)

    # 静音第三方库的噪音
    for noisy in ("urllib3", "requests", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logger


def prune_logs(keep_days: int = 30) -> int:
    """清理超期日志，返回删除数量。"""
    removed = 0
    if not LOG_DIR.exists():
        return 0
    cutoff = time.time() - keep_days * 86400
    for p in LOG_DIR.glob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def ensure_dirs() -> None:
    for d in (OUTPUT_DIR, CACHE_DIR, CORE_DIR, GEO_DIR, LOG_DIR, DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)


def human_ms(ms: float | int | None) -> str:
    if ms is None:
        return "-"
    return f"{int(ms)} ms"


def now_cn() -> str:
    """北京时间字符串。"""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def today_str() -> str:
    return time.strftime("%Y%m%d", time.localtime())
