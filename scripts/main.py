"""FreeNodeMailer 主流程。

用法：
  python scripts/main.py                 # 完整流程：抓取 → 测速 → 生成 → 校验 → 发邮件
  python scripts/main.py --dry-run       # 不发邮件，只生成文件
  python scripts/main.py --no-test       # 跳过测速（调试用）
  python scripts/main.py --verify-mail   # 只测试邮箱配置
  python scripts/main.py --doctor        # 环境自检
  python scripts/main.py --limit 200     # 限制测速节点数（调试）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

# 允许以 `python scripts/main.py` 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent))

from util import (  # noqa: E402
    CACHE_DIR, GEO_DIR, OUTPUT_DIR, ROOT, ensure_dirs, env, load_dotenv,
    load_settings, LOG, prune_logs, setup_logging, today_str,
)
from fetcher import fetch_all, parse_sources  # noqa: E402
from parser import dedupe, extract_nodes, normalize_all, unique_names  # noqa: E402
import mailer  # noqa: E402
import report  # noqa: E402
import tester  # noqa: E402
import yaml_builder  # noqa: E402


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser("FreeNodeMailer", description="每日免费节点测速推送")
    ap.add_argument("--dry-run", action="store_true", help="只生成文件，不发送邮件")
    ap.add_argument("--no-test", action="store_true", help="跳过测速（仅调试）")
    ap.add_argument("--verify-mail", action="store_true", help="只测试邮箱配置并发送测试邮件")
    ap.add_argument("--doctor", action="store_true", help="环境自检")
    ap.add_argument("--limit", type=int, default=0, help="限制参与测速的节点数（0=自动）")
    ap.add_argument("--min-nodes", type=int, default=0, help="覆盖最少可用节点数要求")
    ap.add_argument("--max-delay", type=int, default=0, help="覆盖延迟阈值(ms)")
    ap.add_argument("--no-mail", action="store_true", help="与 --dry-run 相同")
    ap.add_argument("--json", action="store_true", help="把统计结果以 JSON 输出到 stdout 末尾")
    return ap.parse_args(argv)


# ------------------------------------------------------------------ 主流程
def run_pipeline(args: argparse.Namespace) -> int:
    load_dotenv()
    settings = load_settings()
    if args.max_delay:
        settings["test"]["max_delay"] = args.max_delay
    if args.min_nodes:
        settings["select"]["min_nodes"] = args.min_nodes
    setup_logging(settings)
    ensure_dirs()
    prune_logs(int(settings.get("log", {}).get("keep_days", 30)))

    started = time.time()
    LOG.info("=" * 62)
    LOG.info("FreeNodeMailer 启动 —— %s", ROOT)
    LOG.info("=" * 62)

    min_nodes = int(settings.get("select", {}).get("min_nodes", 5))
    max_delay = int(settings.get("test", {}).get("max_delay", 500))

    # ---------------- 1. 抓取 ----------------
    srcs = parse_sources(ROOT / "config" / "sources.txt")
    if not srcs:
        LOG.error("没有配置任何数据源，退出")
        return 2
    fetch_results = fetch_all(srcs, settings)

    raw_nodes: List[Dict[str, Any]] = []
    source_stats: List[Dict[str, Any]] = []
    for fr in fetch_results:
        nodes_raw = extract_nodes(fr.text) if fr.ok else []
        norm, nstats = normalize_all(nodes_raw)
        source_stats.append({
            **fr.to_dict(),
            "nodes": len(norm),
            "raw_nodes": len(nodes_raw),
            "dropped": nstats.get("unsupported_type", 0) + nstats.get("bad_field", 0),
        })
        if fr.ok:
            raw_nodes.extend(norm)

    if not raw_nodes:
        LOG.error("所有数据源均未解析出节点，终止（不发空邮件）")
        return 3

    total_raw = len(raw_nodes)
    uniq, dup_count = dedupe(raw_nodes)
    uniq = unique_names(uniq)
    LOG.info("节点汇总：解析 %d → 去重 %d（去掉重复 %d）", total_raw, len(uniq), dup_count)

    # ---------------- 2. 预校验（剔除内核不接受的节点）----------------
    exe = None
    removed_preflight: List[Dict[str, Any]] = []
    if not args.no_test:
        try:
            uniq, removed_preflight = tester.preflight_filter(uniq, settings)
        except tester.CoreError as exc:
            LOG.error("内核预校验失败：%s", exc)
            return 4

    # ---------------- 3. 测速（全量候选，内部两阶段控时）----------------
    if args.limit and args.limit > 0:
        candidates = uniq[:args.limit]
        LOG.info("--limit %d：只用前 %d 个候选测速", args.limit, len(candidates))
    else:
        candidates = uniq
    LOG.info("进入测速的候选节点：%d 个（去重后全量）", len(candidates))

    if args.no_test:
        LOG.warning("--no-test：跳过测速，全部候选节点视为可用（仅供调试）")
        results = [tester.NodeResult(name=n["name"], type=n["type"], server=n["server"],
                                     port=n.get("port"), delay=100, node=n) for n in candidates]
    else:
        try:
            results = tester.run_speed_test(candidates, settings)
        except tester.CoreError as exc:
            LOG.error("测速内核异常：%s", exc)
            return 4

    available = [r for r in results if r.ok]
    LOG.info("测速结果：%d/%d 可用（阈值 %d ms）", len(available), len(candidates), max_delay)

    # ---------------- 4. 生成配置 ----------------
    picked = yaml_builder.filter_nodes(results, settings)
    stats: Dict[str, Any] = {}
    if not picked:
        LOG.error("没有可用节点，跳过生成与发送（避免推送空配置）")
        _write_run_stats(started, source_stats, stats)
        return 5

    results_by_name = {r.name: r for r in results}
    statuses = {}
    for r in available:
        tag = f"{r.rounds} 轮"
        if r.delays and len(r.delays) > 1:
            tag += f" / 波动 {min(r.delays)}-{max(r.delays)}ms"
        statuses[r.name] = tag

    dist = {"<100 ms": 0, "100-200 ms": 0, "200-350 ms": 0, "350-500 ms": 0, ">500 ms": 0}
    for n, _region, d in picked:
        if d < 100:
            dist["<100 ms"] += 1
        elif d < 200:
            dist["100-200 ms"] += 1
        elif d < 350:
            dist["200-350 ms"] += 1
        elif d <= 500:
            dist["350-500 ms"] += 1
        else:
            dist[">500 ms"] += 1
    types: Dict[str, int] = {}
    for n, _region, _d in picked:
        types[n["type"]] = types.get(n["type"], 0) + 1

    region_of = {n["name"]: r for n, r, _d in picked}
    today = today_str()
    cfg = yaml_builder.build_config(picked, settings, stats=None, dated=True)
    files = yaml_builder.write_outputs(cfg, OUTPUT_DIR, settings, today)

    # ---------------- 5. 校验交付 YAML ----------------
    validation: Dict[str, Any] = {"ok": False, "detail": "未校验"}
    if not args.no_test:
        try:
            exe = tester.ensure_core(settings)
            tester.ensure_geo()
            with tempfile.TemporaryDirectory(prefix="fnm_val_") as tmp:
                wd = Path(tmp)
                for name in tester.GEO_FILES:
                    p = GEO_DIR / name
                    if p.exists():
                        try:
                            os.link(p, wd / name)
                        except OSError:
                            shutil.copy2(p, wd / name)
                ok, detail = tester.validate_final_yaml(exe, wd, files["dated"])
                # 二次校验：确认每个节点都被内核接受
                extra = ""
                if ok:
                    try:
                        names_picked = [n["name"] for n, _r, _d in picked]
                        probe_cfg = tester.build_probe_config(
                            [n for n, _r, _d in picked], tester.free_port(), "val", settings)
                        probe_cfg = tester.geo_paths(probe_cfg)
                        (wd / "verify.yaml").write_text(
                            yaml.safe_dump(probe_cfg, allow_unicode=True,
                                           sort_keys=False), encoding="utf-8")
                        core = tester.MihomoCore(exe, wd, probe_cfg,
                                                 controller_port=tester.free_port(),
                                                 secret="val")
                        core.start()
                        try:
                            avail = core.api_proxies()
                            missing = [n for n in names_picked if n not in avail]
                            loaded = sum(1 for n in names_picked if n in avail)
                            extra = (f"内核加载 {loaded}/{len(names_picked)} 个节点，全部就绪"
                                     if not missing else
                                     f"警告：{len(missing)} 个节点内核未加载：{missing[:5]}")
                            if missing:
                                ok = False
                        finally:
                            core.stop()
                    except tester.CoreError as exc:
                        extra = f"二次校验异常：{exc}"
                        ok = False
                    except Exception as exc:  # noqa: BLE001
                        extra = f"二次校验异常：{type(exc).__name__}: {exc}"
                validation = {"ok": ok, "detail": (detail + "\n" + extra).strip()}
        except tester.CoreError as exc:
            validation = {"ok": False, "detail": f"校验内核异常：{exc}"}

    LOG.info("配置校验：%s | %s", "通过" if validation["ok"] else "失败",
             validation["detail"].replace("\n", " ")[:300])

    if not validation["ok"]:
        LOG.error("交付 YAML 未通过校验，为安全起见不发送邮件")
        _write_run_stats(started, source_stats, {"validation": validation})
        return 6

    # ---------------- 6. 报告 + 邮件 ----------------
    file_names = {
        "dated": files["dated"].name,
        "subscription": files["subscription"].name,
        "dated_path": str(files["dated"]),
    }
    stats = {
        "candidates": total_raw,
        "dedup": len(uniq),
        "tested": len(candidates),
        "available": len(available),
        "max_delay": max_delay,
        "dist": dist,
        "types": types,
        "results_by_name": results_by_name,
        "statuses": statuses,
        "preflight_removed": len(removed_preflight),
        "elapsed": round(time.time() - started, 1),
    }

    html = report.build_html_report(stats, picked, region_of, validation,
                                    source_stats, file_names, settings)
    text = report.build_text_report(stats, len(picked), validation, file_names)
    (OUTPUT_DIR / "report.html").write_text(html, encoding="utf-8")
    LOG.info("已生成报告：%s", OUTPUT_DIR / "report.html")

    mail_result: Dict[str, Any] = {"ok": False, "skipped": True}
    dry = args.dry_run or args.no_mail
    if dry:
        LOG.info("--dry-run：跳过发送邮件")
        (OUTPUT_DIR / "report.txt").write_text(text, encoding="utf-8")
    else:
        if len(picked) < min_nodes:
            LOG.error("可用节点 %d 少于要求的 %d，按配置不发送邮件", len(picked), min_nodes)
            if not bool(settings.get("mail", {}).get("send_on_failure", False)):
                _write_run_stats(started, source_stats, stats)
                return 7
        attachments = []
        if bool(settings.get("mail", {}).get("attach_dated", True)):
            attachments.append(files["dated"])
        if bool(settings.get("mail", {}).get("attach_subscription", True)):
            attachments.append(files["subscription"])
        subject = f"{today[:4]}-{today[4:6]}-{today[6:]} 可用节点 {len(picked)} 个（延迟≤{max_delay}ms）"
        mail_result = mailer.send_mail(settings, subject, html, text, attachments)
        if not mail_result.get("ok"):
            LOG.error("邮件发送失败：%s", mail_result.get("error"))
            _write_run_stats(started, source_stats, stats)
            return 8

    stats["mail"] = mail_result
    _write_run_stats(started, source_stats, stats)
    LOG.info("=" * 62)
    LOG.info("完成：入选 %d 个节点，用时 %.1fs", len(picked), time.time() - started)
    LOG.info("带日期配置：%s", files["dated"])
    LOG.info("=" * 62)
    if args.json:
        print(json.dumps({"stats": {k: v for k, v in stats.items()
                                    if k not in ("results_by_name", "statuses")},
                          "files": {k: str(v) for k, v in files.items()},
                          "mail": mail_result}, ensure_ascii=False))
    return 0


def _write_run_stats(started: float, source_stats: List[Dict[str, Any]],
                     stats: Dict[str, Any]) -> None:
    slim = {k: v for k, v in stats.items() if k not in ("results_by_name", "statuses")}
    payload = {
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed": round(time.time() - started, 1),
        "sources": source_stats,
        "stats": slim,
    }
    try:
        (OUTPUT_DIR / "last_run.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


# ------------------------------------------------------------------ doctor
def doctor() -> int:
    load_dotenv()
    settings = load_settings()
    setup_logging(settings)
    ensure_dirs()
    ok = True
    print("=" * 62)
    print("FreeNodeMailer 环境自检")
    print("=" * 62)
    print(f"项目目录     : {ROOT}")
    print(f"Python       : {sys.version.split()[0]}")
    print(f"输出目录     : {OUTPUT_DIR}")

    # 依赖
    try:
        import requests, yaml  # noqa: F401
        print(f"依赖         : requests OK, PyYAML OK")
    except ImportError as exc:
        ok = False
        print(f"依赖         : 缺失 {exc} → 执行 pip install -r requirements.txt")

    # 内核
    try:
        exe = tester.ensure_core(settings)
        import subprocess
        v = subprocess.run([str(exe), "-v"], capture_output=True, text=True, timeout=30)
        print(f"内核         : {exe}")
        print(f"内核版本     : {(v.stdout or v.stderr).strip().splitlines()[0] if (v.stdout or v.stderr) else '?'}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"内核         : 失败 {exc}")

    # geo
    have = [f for f in ("geoip.metadb", "geosite.dat") if (GEO_DIR / f).exists()]
    print(f"geodata      : {GEO_DIR} → {have or '缺失（首次运行会自动下载）'}")

    # 数据源
    srcs = parse_sources(ROOT / "config" / "sources.txt")
    print(f"数据源数量   : {len(srcs)}")

    # 邮箱
    try:
        c = mailer.load_mail_credentials(settings)
        mailer.check_credentials(settings)
        print(f"邮箱配置     : {c['sender']} → {', '.join(c['to'])}（{c['host']}:{c['port']}）")
        print(f"授权码       : 已配置（{len(c['auth'])} 位）")
    except mailer.MailError as exc:
        ok = False
        print(f"邮箱配置     : 未完成\n{exc}")

    print("-" * 62)
    print("结论         :", "全部就绪 ✅" if ok else "存在待处理项 ⚠️")
    return 0 if ok else 1


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if args.doctor:
        return doctor()
    if args.verify_mail:
        load_dotenv()
        settings = load_settings()
        setup_logging(settings)
        try:
            res = mailer.send_test_mail(settings)
        except mailer.MailError as exc:
            print(f"❌ {exc}")
            return 1
        print("✅ 测试邮件已发送" if res.get("ok") else f"❌ 发送失败：{res.get('error')}")
        return 0 if res.get("ok") else 1
    return run_pipeline(args)


if __name__ == "__main__":
    raise SystemExit(main())
