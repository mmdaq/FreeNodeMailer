"""真实内核测速：用 mihomo 内核起一个 HTTP 代理，通过 REST API 实测每个节点延迟。

这是本项目「测速」的核心。为什么不用 socket TCP 握手？
  TCP 连得上 != 能翻墙。免费节点大量存在「端口活着但握手失败 /
  证书过期 / 密码错误 / 挂了 CF 黑洞」的情况。只有让真实内核
  跑完整协议握手 + 真实 HTTP 请求（generate_204），才算测通。
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

from util import CACHE_DIR, CORE_DIR, GEO_DIR, LOG

# 优先尝试直接复用本机 Clash Verge 自带的同款内核
LOCAL_CORE_CANDIDATES = [
    r"D:\Clash Verge\verge-mihomo.exe",
    r"C:\Program Files\Clash Verge\verge-mihomo.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Clash Verge\verge-mihomo.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\clash-verge\verge-mihomo.exe"),
    "/usr/local/bin/mihomo",
    "/usr/bin/mihomo",
]

LOCAL_GEO_CANDIDATES = [
    r"D:\Clash Verge\resources",
    r"C:\Program Files\Clash Verge\resources",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Clash Verge\resources"),
]

GEO_FILES = ["geoip.metadb", "geoip.dat", "geosite.dat", "Country.mmdb", "ASN.mmdb"]

# GitHub Release 国内可用加速镜像（实测 gh-proxy.com / ghfast.top 可用）
RELEASE_MIRRORS = [
    "https://gh-proxy.com/{url}",
    "https://ghfast.top/{url}",
    "https://ghproxy.cc/{url}",
    "{url}",
]


@dataclass
class NodeResult:
    name: str
    type: str
    server: str
    port: Optional[int]
    delay: Optional[int] = None          # 最终延迟(ms)，None = 不可用
    delays: List[int] = field(default_factory=list)
    error: str = ""
    rounds: int = 0
    tcp_ok: Optional[bool] = None        # 直连 TCP 预检结果（仅参考）
    node: Dict[str, Any] = field(default_factory=dict)   # 原始节点定义

    @property
    def ok(self) -> bool:
        return self.delay is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "type": self.type, "server": self.server, "port": self.port,
            "delay": self.delay, "delays": self.delays, "error": self.error,
            "rounds": self.rounds, "tcp_ok": self.tcp_ok,
        }


class CoreError(RuntimeError):
    pass


# --------------------------------------------------------------- 内核准备
def find_local_core(explicit: str = "") -> Optional[Path]:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
        LOG.warning("指定的内核路径不存在：%s", explicit)
    for cand in LOCAL_CORE_CANDIDATES:
        p = Path(cand)
        if p.exists():
            return p
    return None


def _download(url: str, dest: Path, timeout: int = 180) -> bool:
    for tpl in RELEASE_MIRRORS:
        real = tpl.format(url=url)
        try:
            with requests.get(real, stream=True, timeout=timeout,
                              headers={"User-Agent": "Mozilla/5.0"}) as r:
                if r.status_code != 200:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".part")
                got = 0
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 16):
                        fh.write(chunk)
                        got += len(chunk)
                if got < 1_000_000:
                    tmp.unlink(missing_ok=True)
                    continue
                tmp.replace(dest)
                LOG.info("内核下载成功：%s (%.1f MB, via %s)", dest.name, got / 1e6,
                         real.split("/")[2])
                return True
        except requests.RequestException as exc:
            LOG.debug("镜像失败 %s: %s", real.split("/")[2], exc)
            continue
    return False


def ensure_core(settings: Dict[str, Any]) -> Path:
    """确保 .cache/core/mihomo.exe 存在，返回路径。"""
    test_cfg = settings.get("test", {})
    CORE_DIR.mkdir(parents=True, exist_ok=True)
    exe_name = "mihomo.exe" if os.name == "nt" else "mihomo"
    target = CORE_DIR / exe_name

    explicit = str(test_cfg.get("core_path") or "")
    # 1) 显式指定
    if explicit and Path(explicit).exists():
        return Path(explicit)
    # 2) 已缓存
    if target.exists() and target.stat().st_size > 1_000_000:
        return target
    # 3) 复用本机 Clash Verge 内核（最快）
    local = find_local_core()
    if local:
        try:
            shutil.copy2(local, target)
            LOG.info("已复用本机内核：%s → %s", local, target)
            return target
        except OSError as exc:
            LOG.warning("复制本机内核失败：%s", exc)
    # 4) 自动下载
    if not bool(test_cfg.get("auto_download_core", True)):
        raise CoreError("未找到可用内核且已禁用自动下载（test.auto_download_core=false）")

    for cand in LOCAL_CORE_CANDIDATES:
        p = Path(cand)
        if p.exists():
            return p

    LOG.info("本地未找到 mihomo 内核，开始自动下载（Release 镜像）…")
    # 查最新版本
    ver = "v1.19.32"
    try:
        meta = requests.get("https://api.github.com/repos/MetaCubeX/mihomo/releases/latest",
                            timeout=30, headers={"User-Agent": "ps"}).json()
        ver = meta.get("tag_name") or ver
    except (requests.RequestException, ValueError):
        pass
    asset = f"mihomo-windows-amd64-compatible-{ver}.zip"
    if os.name != "nt":
        asset = f"mihomo-linux-amd64-compatible-{ver}.gz"
    url = f"https://github.com/MetaCubeX/mihomo/releases/download/{ver}/{asset}"
    zpath = CORE_DIR / asset
    if not _download(url, zpath):
        raise CoreError("内核下载失败：所有 Release 镜像均不可用")
    if asset.endswith(".zip"):
        with zipfile.ZipFile(zpath) as zf:
            member = next((n for n in zf.namelist() if n.endswith(".exe")), None)
            if not member:
                raise CoreError("内核压缩包内未找到可执行文件")
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    else:
        import gzip
        with gzip.open(zpath, "rb") as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    zpath.unlink(missing_ok=True)
    if os.name != "nt":
        target.chmod(0o755)
    return target


def ensure_geo() -> None:
    """准备 geodata（geodata-mode 需要 geoip.metadb / geosite.dat）。"""
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    missing = [f for f in ("geoip.metadb", "geosite.dat") if not (GEO_DIR / f).exists()]
    if not missing:
        return
    for src_dir in LOCAL_GEO_CANDIDATES:
        d = Path(src_dir)
        if not d.exists():
            continue
        for name in GEO_FILES:
            src = d / name
            if src.exists() and not (GEO_DIR / name).exists():
                try:
                    shutil.copy2(src, GEO_DIR / name)
                except OSError:
                    pass
        break
    missing = [f for f in ("geoip.metadb", "geosite.dat") if not (GEO_DIR / f).exists()]
    if not missing:
        LOG.info("geodata 已就绪（复用本机 Clash Verge 数据文件）")
        return

    LOG.info("geodata 缺失 %s，尝试下载…", missing)
    sources = {
        "geoip.metadb": [
            "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.metadb",
            "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/release/geoip.metadb",
        ],
        "geosite.dat": [
            "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite.dat",
            "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/release/geosite.dat",
        ],
        "geoip.dat": [
            "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.dat",
        ],
        "Country.mmdb": [
            "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/Country.mmdb",
        ],
    }
    for name in missing:
        for url in sources.get(name, []):
            try:
                r = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200 and len(r.content) > 100_000:
                    (GEO_DIR / name).write_bytes(r.content)
                    LOG.info("已下载 %s (%.1f MB)", name, len(r.content) / 1e6)
                    break
            except requests.RequestException:
                continue


# --------------------------------------------------------------- 配置生成
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def build_probe_config(proxies: List[Dict[str, Any]], controller_port: int, secret: str,
                       settings: Dict[str, Any]) -> Dict[str, Any]:
    test_cfg = settings.get("test", {})
    ipv6 = bool(test_cfg.get("ipv6", True))
    mixed = free_port()
    cfg: Dict[str, Any] = {
        "mixed-port": mixed,
        "allow-lan": False,
        "bind-address": "127.0.0.1",
        "mode": "rule",
        "log-level": str(test_cfg.get("log_level", "warning")),
        "ipv6": ipv6,
        "geodata-mode": True,
        "geodata-loader": "standard",
        "geo-auto-update": False,
        "unified-delay": True,
        "tcp-concurrent": True,
        "find-process-mode": "off",
        "external-controller": f"127.0.0.1:{controller_port}",
        "secret": secret,
        "profile": {"store-selected": False, "store-fake-ip": False},
        "dns": {
            "enable": True,
            "listen": "127.0.0.1:0",
            "ipv6": ipv6,
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.1/16",
            "fake-ip-filter": ["*.lan", "*.local", "localhost.ptlogin2.qq.com"],
            "default-nameserver": ["223.5.5.5", "119.29.29.29"],
            "nameserver": [
                "https://223.5.5.5/dns-query",
                "https://1.12.12.12/dns-query",
                "tls://8.8.8.8:853",
            ],
            "proxy-server-nameserver": ["https://223.5.5.5/dns-query", "223.5.5.5"],
        },
        "proxies": proxies,
        "proxy-groups": [
            {"name": "PROBE", "type": "select", "proxies": ["DIRECT"] + [p["name"] for p in proxies]}
        ],
        "rules": ["MATCH,DIRECT"],
    }
    return cfg


def geo_paths(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """把 geodata 路径写成绝对路径，避免依赖工作目录。"""
    out = dict(cfg)
    out["geox-url"] = {
        "geoip": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.dat",
        "geosite": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite.dat",
        "mmdb": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/Country.mmdb",
        "asn": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/ASN.mmdb",
    }
    return out


# --------------------------------------------------------------- 内核进程
class MihomoCore:
    """启动一个临时的 mihomo 进程，供测速/校验使用。"""

    def __init__(self, exe: Path, workdir: Path, config: Dict[str, Any],
                 controller_port: int = 0, secret: str = "fnm", log_level: str = "warning"):
        self.exe = exe
        self.workdir = workdir
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.secret = secret
        self.controller_port = controller_port or free_port()
        self.config = dict(config)
        self.config["external-controller"] = f"127.0.0.1:{self.controller_port}"
        self.config["secret"] = self.secret
        self.config_path = workdir / "config.yaml"
        self.log_path = workdir / "core.log"
        self.proc: Optional[subprocess.Popen] = None
        self._log_fh = None
        self._write_config()

    def _write_config(self) -> None:
        self.config_path.write_text(
            yaml.safe_dump(self.config, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.controller_port}"

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.secret}"}

    def __enter__(self) -> "MihomoCore":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()

    def start(self, ready_timeout: float = 40.0) -> None:
        if not self.exe.exists():
            raise CoreError(f"内核不存在：{self.exe}")
        self._log_fh = open(self.log_path, "w", encoding="utf-8", errors="replace")
        creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.proc = subprocess.Popen(
                [str(self.exe), "-d", str(self.workdir), "-f", str(self.config_path)],
                cwd=str(self.workdir),
                stdout=self._log_fh,
                stderr=subprocess.STDOUT,
                creationflags=creation,
            )
        except OSError as exc:
            raise CoreError(f"内核启动失败：{exc}") from exc

        deadline = time.time() + ready_timeout
        last = ""
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise CoreError(f"内核提前退出(code={self.proc.returncode})：\n{self.tail_log()}")
            try:
                r = requests.get(f"{self.base_url}/version", headers=self.headers, timeout=2)
                if r.status_code == 200:
                    LOG.debug("内核就绪：%s", r.json().get("version"))
                    return
                last = f"HTTP {r.status_code}"
            except requests.RequestException as exc:
                last = type(exc).__name__
            time.sleep(0.4)
        raise CoreError(f"内核 {ready_timeout:.0f}s 内未就绪（{last}）")

    def tail_log(self, lines: int = 25) -> str:
        try:
            content = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(content[-lines:])
        except OSError:
            return "(无内核日志)"

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=8)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self.proc.kill()
                except OSError:
                    pass
        if self._log_fh:
            try:
                self._log_fh.close()
            except OSError:
                pass
            self._log_fh = None

    # ---------------- API ----------------
    def api_proxies(self) -> Dict[str, Any]:
        r = requests.get(f"{self.base_url}/proxies", headers=self.headers, timeout=10)
        r.raise_for_status()
        return (r.json() or {}).get("proxies", {}) or {}

    def delay(self, name: str, url: str, timeout_ms: int) -> Tuple[Optional[int], str]:
        try:
            r = requests.get(
                f"{self.base_url}/proxies/{requests.utils.quote(name, safe='')}/delay",
                params={"url": url, "timeout": timeout_ms},
                headers=self.headers,
                timeout=(timeout_ms / 1000.0) + 6,
            )
        except requests.RequestException as exc:
            return None, type(exc).__name__
        if r.status_code == 200:
            try:
                val = int((r.json() or {}).get("delay", 0))
                return (val if val > 0 else None), ""
            except (ValueError, TypeError):
                return None, "bad_json"
        msg = ""
        try:
            msg = str((r.json() or {}).get("message", ""))
        except ValueError:
            msg = (r.text or "")[:120]
        return None, f"HTTP {r.status_code} {msg}".strip()

    def reload(self, config: Dict[str, Any]) -> None:
        """热重载配置（PUT /configs?force=true）。"""
        body = {"path": str(self.config_path)}
        self.config = dict(config)
        self.config["external-controller"] = f"127.0.0.1:{self.controller_port}"
        self.config["secret"] = self.secret
        self._write_config()
        r = requests.put(f"{self.base_url}/configs", params={"force": "true"},
                         headers=self.headers, json=body, timeout=15)
        r.raise_for_status()


def test_config_file(exe: Path, workdir: Path, config_path: Path) -> Tuple[bool, str]:
    """用 `mihomo -t` 校验配置文件语法/字段（这是最权威的校验）。"""
    creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            [str(exe), "-t", "-d", str(workdir), "-f", str(config_path)],
            cwd=str(workdir), capture_output=True, timeout=180,
            creationflags=creation,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"内核校验执行失败：{exc}"

    # 内核输出可能是 UTF-8 或系统本地编码（中文 Windows 为 GBK），逐个尝试
    std = (proc.stdout or b"") + b"\n" + (proc.stderr or b"")
    out = ""
    for enc in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            out = std.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        out = std.decode("utf-8", errors="replace")
    out = out.strip()

    low = out.lower()
    ok = proc.returncode == 0 and ("configuration file" in low or "test is successful" in low)
    # 内核在 level=error 时即使 exit=0 也说明配置有问题，必须视为失败
    if "level=error" in low or "level=fatal" in low:
        ok = False
    # 部分版本把致命错误写在最后一行而不带 level 前缀
    for bad_marker in ("parse config error", "is the duplicate name", "invalid config"):
        if bad_marker in low:
            ok = False
    return ok, out


# --------------------------------------------------------------- TCP 预检
def tcp_precheck(nodes: List[Dict[str, Any]], concurrency: int = 100,
                 timeout: float = 2.0) -> Dict[str, bool]:
    """对「主机名/IP」做一次 TCP 连通预检，仅用于报告统计与失败原因分析。"""
    out: Dict[str, bool] = {}

    def probe(node: Dict[str, Any]) -> Tuple[str, bool]:
        host, port = node.get("server", ""), node.get("port")
        if not host or not port:
            return node.get("name", ""), False
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return node["name"], True
        except (OSError, ValueError):
            return node.get("name", ""), False

    with cf.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for name, ok in pool.map(probe, nodes):
            out[name] = ok
    return out


# --------------------------------------------------------------- 主流程
def run_speed_test(nodes: List[Dict[str, Any]], settings: Dict[str, Any],
                   progress=None) -> List[NodeResult]:
    """对节点列表做真实内核测速，返回与输入等长的结果列表。

    两阶段设计（免费节点可用率通常只有 2%~6%，必须控制耗时）：
      阶段 A  TCP 预筛：高并发 socket 连一下 host:port，秒级排除死主机。
              仅用于「省时间」，不作为「可用」依据。
      阶段 B  内核实测：对存活候选跑真实的 mihomo 延迟测试；失败节点
              在后续轮次里用更长的超时复测（免费节点常见冷启动失败）。
    """
    test_cfg = settings.get("test", {})
    url = str(test_cfg.get("url", "http://www.gstatic.com/generate_204"))
    cap = int(test_cfg.get("max_delay", 500))
    timeout_ms = int(test_cfg.get("timeout_ms", 3000))
    retest_timeout = int(test_cfg.get("retest_timeout_ms", 8000))
    retest_rounds = int(test_cfg.get("retest_rounds", 3))
    concurrency = int(test_cfg.get("concurrency", 48))
    keep_retested = bool(test_cfg.get("keep_retested", True))
    precheck = bool(test_cfg.get("tcp_precheck", True))
    precheck_timeout = float(test_cfg.get("tcp_precheck_timeout", 1.5))
    test_budget = float(test_cfg.get("test_budget", 0) or 0)

    if not nodes:
        return []

    started = time.time()
    exe = ensure_core(settings)
    ensure_geo()

    # 去重名称，建立 name -> node 映射
    results: Dict[str, NodeResult] = {}
    for n in nodes:
        results[n["name"]] = NodeResult(
            name=n["name"], type=n["type"], server=n.get("server", ""), port=n.get("port"),
            node=n,
        )

    # ---------------- 阶段 A：TCP 预筛 ----------------
    survivors = list(nodes)
    if precheck and len(nodes) > 50:
        t0 = time.time()
        tcp = tcp_precheck(nodes, concurrency=400, timeout=precheck_timeout)
        alive = [n for n in nodes if tcp.get(n["name"])]
        for n in nodes:
            results[n["name"]].tcp_ok = tcp.get(n["name"])
        # 若可达数量过少（网络整体受限），预筛不可靠，则退化为全量测速
        if len(alive) >= max(20, int(len(nodes) * 0.02)):
            survivors = alive
            LOG.info("阶段A TCP 预筛：%d/%d 主机可达，淘汰 %d 个死主机，用时 %.1fs",
                     len(alive), len(nodes), len(nodes) - len(alive), time.time() - t0)
        else:
            LOG.warning("阶段A TCP 可达仅 %d/%d，预筛结果不可靠，改为全量内核测速",
                        len(alive), len(nodes))

    # ---------------- 阶段 B：内核实测 ----------------
    controller_port = int(test_cfg.get("controller_port", 0)) or free_port()
    secret = f"fnm{int(time.time())}"
    cfg = build_probe_config(survivors, controller_port, secret, settings)
    cfg = geo_paths(cfg)

    with tempfile.TemporaryDirectory(prefix="fnm_probe_") as tmp:
        workdir = Path(tmp)
        _link_geo(workdir)

        core = MihomoCore(exe, workdir, cfg, controller_port=controller_port,
                          secret=secret, log_level=str(test_cfg.get("log_level", "warning")))
        LOG.info("阶段B 内核测速：%d 个候选，并发 %d，阈值 %dms，地址 %s",
                 len(survivors), concurrency, cap, url)
        try:
            core.start()
            available = core.api_proxies()
            unknown = [n["name"] for n in survivors if n["name"] not in available]
            if unknown:
                LOG.warning("%d 个节点未被内核接受（字段不兼容），将剔除：%s",
                            len(unknown), ", ".join(unknown[:5]))

            def measure(node: Dict[str, Any], tmo: int) -> Tuple[Optional[int], str]:
                if node["name"] not in available:
                    return None, "内核对节点字段不兼容"
                delay, err = core.delay(node["name"], url, tmo)
                return delay, err

            def round_of(items: List[Dict[str, Any]], tmo: int, tag: str) -> None:
                if not items:
                    return
                done = 0
                with cf.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
                    futs = {pool.submit(measure, n, tmo): n for n in items}
                    for fut in cf.as_completed(futs):
                        node = futs[fut]
                        res = results[node["name"]]
                        try:
                            delay, err = fut.result()
                        except Exception as exc:  # noqa: BLE001
                            delay, err = None, type(exc).__name__
                        res.rounds += 1
                        if delay is not None:
                            res.delays.append(delay)
                            if res.delay is None or delay < res.delay:
                                res.delay = delay
                            res.error = ""
                        elif not res.error:
                            res.error = err
                        done += 1
                        if progress and done % 25 == 0:
                            progress(done, len(items), tag)
                if progress:
                    progress(len(items), len(items), tag)

            # 第 1 轮：严格超时
            round_of(survivors, timeout_ms, "首轮")
            ok1 = sum(1 for r in results.values() if r.ok)
            LOG.info("首轮完成：%d/%d 可用，用时 %.1fs", ok1, len(survivors),
                     time.time() - started)

            # 第 2..N 轮：失败节点用更长超时复测（克制冷启动误杀）
            for i in range(max(0, retest_rounds)):
                if test_budget and (time.time() - started) > test_budget:
                    LOG.warning("已达测速时限 %.0fs，停止复测", test_budget)
                    break
                failed = [n for n in survivors if not results[n["name"]].ok]
                if not failed:
                    break
                tmo = min(retest_timeout, timeout_ms * (i + 2))
                LOG.info("第 %d 轮复测：%d 个失败节点，超时放宽至 %dms",
                         i + 2, len(failed), tmo)
                round_of(failed, tmo, f"复测{i + 2}")

            # 阈值过滤
            for r in results.values():
                if not r.ok or r.delay is None:
                    continue
                if r.delay <= cap:
                    continue
                if keep_retested and len(r.delays) > 1 and min(r.delays) <= cap:
                    continue
                r.error = f"延迟 {r.delay}ms 超过阈值 {cap}ms"
                r.delay = None
        finally:
            core.stop()
            LOG.debug("内核日志尾部：\n%s", core.tail_log(12))

    final_ok = sum(1 for r in results.values() if r.ok)
    LOG.info("测速结束：%d/%d 节点可用（阈值 %dms），总用时 %.1fs",
             final_ok, len(nodes), cap, time.time() - started)
    return [results[n["name"]] for n in nodes]


def _link_geo(workdir: Path) -> None:
    """把 geodata 以硬链接（失败则复制）放进内核工作目录。"""
    for name in GEO_FILES:
        p = GEO_DIR / name
        if not p.exists():
            continue
        dst = workdir / name
        if dst.exists():
            continue
        try:
            os.link(p, dst)
        except OSError:
            try:
                shutil.copy2(p, dst)
            except OSError:
                pass


def preflight_filter(nodes: List[Dict[str, Any]], settings: Dict[str, Any],
                     batch_size: int = 400) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """把候选节点交给内核 `-t` 校验，剔除导致配置无法加载的节点。

    这是关键安全网：只要有一个节点字段不兼容，整份配置都会加载失败。

    实现要点：3900 个候选一次性校验太慢，所以按 batch_size 分批校验：
      - 某批通过 → 整批保留（大多数情况，一批只要 1 次内核调用）
      - 某批失败 → 从报错里定位问题节点；定位不到就把这批二分递归
    最后再对「全部保留节点」做一次整体校验，确保没有跨批冲突（如重名）。

    返回 (保留节点, 被剔除节点)。
    """
    if not nodes:
        return [], []
    exe = ensure_core(settings)
    ensure_geo()
    removed: List[Dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="fnm_pre_") as tmp:
        workdir = Path(tmp)
        _link_geo(workdir)
        cfg_path = workdir / "pre.yaml"
        call_count = 0

        def validate(items: List[Dict[str, Any]]) -> Tuple[bool, str]:
            nonlocal call_count
            call_count += 1
            cfg = build_probe_config(items, free_port(), "pre", settings)
            cfg = geo_paths(cfg)
            cfg_path.write_text(
                yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
            return test_config_file(exe, workdir, cfg_path)

        def handle_batch(batch: List[Dict[str, Any]], depth: int = 0) -> List[Dict[str, Any]]:
            """返回该批中可保留的节点。"""
            ok, output = validate(batch)
            if ok:
                return batch
            bad = _locate_bad_nodes(output, batch)
            if bad:
                bad_names = {b["name"] for b in bad}
                removed.extend(bad)
                rest = [n for n in batch if n["name"] not in bad_names]
                LOG.warning("预校验剔除 %d 个不兼容节点：%s",
                            len(bad), ", ".join(sorted(bad_names))[:200])
                return handle_batch(rest, depth + 1) if rest else []
            if len(batch) == 1:
                removed.extend(batch)
                LOG.warning("预校验剔除节点（无法定位原因）：%s", batch[0]["name"])
                return []
            if depth >= 4:
                removed.extend(batch)
                LOG.warning("预校验：一批 %d 个节点反复失败，整批剔除", len(batch))
                return []
            mid = len(batch) // 2
            LOG.info("预校验无法定位问题节点，二分排查（%d/%d）", len(batch), len(nodes))
            return handle_batch(batch[:mid], depth + 1) + handle_batch(batch[mid:], depth + 1)

        kept: List[Dict[str, Any]] = []
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i + batch_size]
            kept.extend(handle_batch(batch))
            LOG.info("预校验进度：%d/%d 候选已检查，累计保留 %d，剔除 %d",
                     min(i + batch_size, len(nodes)), len(nodes), len(kept), len(removed))

        # 整体复检（防跨批冲突：重名、组名冲突等）
        if kept:
            ok, output = validate(kept)
            if not ok:
                LOG.warning("整体复检未通过，改用二分定位：%s", output.strip()[-300:])
                kept = handle_batch(kept)
                removed = [n for n in nodes if n not in kept]

    LOG.info("候选配置预校验完成：保留 %d，剔除 %d（内核调用 %d 次）",
             len(kept), len(removed), call_count)
    return kept, removed


def _locate_bad_nodes(output: str, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从内核报错文本中定位问题节点。"""
    bad: List[Dict[str, Any]] = []
    seen = set()

    def add(node: Dict[str, Any]) -> None:
        if node and node["name"] not in seen:
            seen.add(node["name"])
            bad.append(node)

    # 1) 报错里直接出现了节点名
    for n in nodes:
        if n["name"] and n["name"] in output:
            add(n)

    # 2) "proxy 12: ..." 形式的下标（内核按 proxies 顺序编号）
    for m in re.finditer(r"proxy\s+(\d+)\s*[:：]", output, re.IGNORECASE):
        idx = int(m.group(1))
        if 0 <= idx < len(nodes):
            add(nodes[idx])
    # 有些版本是 1-based
    for m in re.finditer(r"proxy\s+(\d+)\s*[:：]", output, re.IGNORECASE):
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(nodes):
            add(nodes[idx])
    # 3) "initial proxy N" / "proxy N is not a valid"
    for m in re.finditer(r"proxies?\[(\d+)\]", output):
        idx = int(m.group(1))
        if 0 <= idx < len(nodes):
            add(nodes[idx])
    return bad


def validate_final_yaml(exe: Path, workdir: Path, yaml_path: Path) -> Tuple[bool, str]:
    """校验最终交付的 YAML：内核 -t 语法校验。"""
    return test_config_file(exe, workdir, yaml_path)
