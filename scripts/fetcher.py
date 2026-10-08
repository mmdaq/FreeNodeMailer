"""数据源抓取：原地址 + GitHub 镜像改写链，多源并发、失败重试。"""
from __future__ import annotations

import base64
import binascii
import concurrent.futures as cf
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import requests

from util import CACHE_DIR, LOG

RAW_RE = re.compile(
    r"^https?://raw\.githubusercontent\.com/(?P<user>[^/]+)/(?P<repo>[^/]+)/(?P<ref>[^/]+)/(?P<path>.+)$"
)
GITHUB_RE = re.compile(
    r"^https?://github\.com/(?P<user>[^/]+)/(?P<repo>[^/]+)/(?:blob|raw)/(?P<ref>[^/]+)/(?P<path>.+)$"
)
JSDELIVR_RE = re.compile(
    r"^https?://cdn\.jsdelivr\.net/gh/(?P<user>[^/]+)/(?P<repo>[^/]+)@(?P<ref>[^/]+)/(?P<path>.+)$"
)


@dataclass
class Source:
    url: str
    name: str = ""

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        try:
            return "/".join(self.url.split("//", 1)[1].split("/")[:3])
        except IndexError:
            return self.url


@dataclass
class FetchResult:
    source: Source
    ok: bool = False
    text: str = ""
    via: str = ""
    bytes_len: int = 0
    elapsed: float = 0.0
    attempts: int = 0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.label,
            "url": self.source.url,
            "ok": self.ok,
            "via": self.via,
            "bytes": self.bytes_len,
            "elapsed": round(self.elapsed, 2),
            "attempts": self.attempts,
            "error": self.error,
        }


def parse_sources(path: Path) -> List[Source]:
    """读取 config/sources.txt。支持 `URL|显示名`。"""
    out: List[Source] = []
    if not path.exists():
        LOG.error("数据源文件不存在：%s", path)
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        url, _, name = line.partition("|")
        url = url.strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        out.append(Source(url=url, name=name.strip()))
    return out


def mirror_chain(url: str, use_mirrors: bool = True) -> List[Tuple[str, str]]:
    """返回 [(url, 说明)]，按尝试优先级排列。

    针对 raw.githubusercontent.com 生成镜像：
      1. 原地址
      2. cdn.jsdelivr.net/gh/user/repo@ref/path
      3. api.github.com/repos/user/repo/contents/path?ref=ref  (返回 base64)
    """
    chain: List[Tuple[str, str]] = [(url, "原始地址")]
    if not use_mirrors:
        return chain

    m = RAW_RE.match(url) or GITHUB_RE.match(url)
    if m:
        user, repo, ref, path = m.group("user"), m.group("repo"), m.group("ref"), m.group("path")
        chain.append(
            (f"https://cdn.jsdelivr.net/gh/{user}/{repo}@{ref}/{path}", "jsDelivr CDN")
        )
        chain.append(
            (
                f"https://api.github.com/repos/{user}/{repo}/contents/{path}?ref={ref}",
                "GitHub API(base64)",
            )
        )
        chain.append(
            (f"https://fastly.jsdelivr.net/gh/{user}/{repo}@{ref}/{path}", "jsDelivr Fastly")
        )
        chain.append(
            (f"https://gcore.jsdelivr.net/gh/{user}/{repo}@{ref}/{path}", "jsDelivr Gcore")
        )
    elif JSDELIVR_RE.match(url):
        user = JSDELIVR_RE.match(url).group("user")
        repo = JSDELIVR_RE.match(url).group("repo")
        ref = JSDELIVR_RE.match(url).group("ref")
        path = JSDELIVR_RE.match(url).group("path")
        chain.append(
            (f"https://raw.githubusercontent.com/{user}/{repo}/{ref}/{path}", "GitHub Raw")
        )
    return chain


def _decode_api_payload(resp: requests.Response) -> str:
    """处理 api.github.com/contents 的 JSON(base64) 响应。"""
    try:
        payload = resp.json()
    except ValueError:
        return resp.text
    if isinstance(payload, dict) and payload.get("encoding") == "base64" and payload.get("content"):
        try:
            return base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
        except (binascii.Error, ValueError):
            return resp.text
    return resp.text


def _looks_usable(text: str) -> bool:
    if not text or len(text.strip()) < 32:
        return False
    low = text.lower()
    if "<html" in low[:400] or "<!doctype" in low[:400]:
        return False
    if "404: not found" in low[:200]:
        return False
    return True


def _cache_path(source: Source) -> Path:
    key = base64.urlsafe_b64encode(source.url.encode()).decode().rstrip("=")[:80]
    return CACHE_DIR / "sources" / f"{key}.txt"


def _cache_write(source: Source, text: str) -> None:
    try:
        p = _cache_path(source)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    except OSError:
        pass


def _cache_read(source: Source) -> str:
    try:
        p = _cache_path(source)
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    return ""


def fetch_source(
    source: Source,
    session: requests.Session,
    timeout: int = 25,
    retries: int = 3,
    use_mirrors: bool = True,
    user_agent: str = "",
) -> FetchResult:
    res = FetchResult(source=source)
    start = time.time()
    chain = mirror_chain(source.url, use_mirrors)
    last_err = ""
    headers = {"User-Agent": user_agent or "Mozilla/5.0", "Accept": "*/*"}
    if "api.github.com" in source.url:
        headers["Accept"] = "application/vnd.github.v3+json"

    for attempt in range(1, max(1, retries) + 1):
        for url, via in chain:
            res.attempts += 1
            try:
                hdr = dict(headers)
                if "api.github.com" in url:
                    hdr["Accept"] = "application/vnd.github.v3+json"
                resp = session.get(url, timeout=timeout, headers=hdr, allow_redirects=True)
                if resp.status_code != 200:
                    last_err = f"{via} HTTP {resp.status_code}"
                    continue
                text = _decode_api_payload(resp) if "api.github.com" in url else resp.text
                if not _looks_usable(text):
                    last_err = f"{via} 内容异常(len={len(text)})"
                    continue
                res.ok = True
                res.text = text
                res.via = via
                res.bytes_len = len(resp.content)
                res.elapsed = time.time() - start
                _cache_write(source, text)
                return res
            except requests.RequestException as exc:
                last_err = f"{via} {type(exc).__name__}"
                continue
        if attempt < retries:
            time.sleep(min(2.0 * attempt, 6.0))

    res.error = last_err or "未知错误"
    res.elapsed = time.time() - start
    cached = _cache_read(source)
    if cached:
        res.ok = True
        res.text = cached
        res.via = "本地缓存"
        res.bytes_len = len(cached)
        res.error = f"{res.error} → 已回退本地缓存"
        LOG.warning("[%s] 抓取失败(%s)，使用本地缓存", source.label, last_err)
    else:
        LOG.error("[%s] 抓取失败：%s", source.label, res.error)
    return res


def fetch_all(sources: Iterable[Source], settings: Dict[str, Any]) -> List[FetchResult]:
    cfg = settings.get("fetch", {})
    concurrency = int(cfg.get("concurrency", 8))
    timeout = int(cfg.get("timeout", 25))
    retries = int(cfg.get("retries", 3))
    use_mirrors = bool(cfg.get("use_mirrors", True))
    ua = str(cfg.get("user_agent", ""))
    deadline = float(cfg.get("deadline", 420))

    sources = list(sources)
    results: List[FetchResult] = []
    LOG.info("开始抓取 %d 个数据源（并发 %d，镜像链 %s）", len(sources), concurrency, use_mirrors)
    started = time.time()

    with requests.Session() as session:
        with cf.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {
                pool.submit(
                    fetch_source, s, session, timeout, retries, use_mirrors, ua
                ): s
                for s in sources
            }
            for fut in cf.as_completed(futures, timeout=None):
                src = futures[fut]
                try:
                    r = fut.result()
                except Exception as exc:  # noqa: BLE001 - 保底，单源异常不影响整体
                    r = FetchResult(source=src, error=f"{type(exc).__name__}: {exc}")
                results.append(r)
                flag = "OK " if r.ok else "FAIL"
                LOG.info(
                    "  [%s] %-28s %-14s %6dB %5.1fs %s",
                    flag,
                    src.label,
                    r.via or "-",
                    r.bytes_len,
                    r.elapsed,
                    "" if r.ok else r.error,
                )
                if time.time() - started > deadline:
                    LOG.warning("抓取超过总时限 %.0fs，放弃剩余源", deadline)
                    for f2 in futures:
                        f2.cancel()
                    break

    ok = sum(1 for r in results if r.ok)
    LOG.info("抓取完成：%d/%d 个源成功，用时 %.1fs", ok, len(sources), time.time() - started)
    return results
