"""FreeNodeMailer 内核级配置校验（联网下载内核/geodata，较慢但最权威）。

用途：验证 yaml_builder 生成的配置能被真实 mihomo 内核接受。
这是「确保 .yaml 可以正常使用」的最终依据——比任何自写校验都可靠。

运行：python scripts/config_check.py [--offline]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from util import GEO_DIR, LOG, OUTPUT_DIR, ensure_dirs, load_settings, setup_logging  # noqa: E402
from tester import (  # noqa: E402
    GEO_FILES, MihomoCore, NodeResult, build_probe_config, ensure_core, ensure_geo,
    free_port, geo_paths, test_config_file,
)
import yaml_builder  # noqa: E402

# 覆盖各种协议的代表性样本（字段必须合法，否则内核会拒绝）
SAMPLE_NODES = [
    {"name": "香港 vless reality", "type": "vless", "server": "1.2.3.4", "port": 443,
     "uuid": "d2519b5e-495e-462e-9703-bbf68011d2f3", "tls": True, "udp": True,
     "servername": "a.com", "flow": "xtls-rprx-vision",
     "reality-opts": {"public-key": "8ENbaQRCWZk-wewSrdHq1_rVjJY4CrxqXUo_5vZNdi4",
                      "short-id": "b2b44805"}},
    {"name": "日本 vmess ws", "type": "vmess", "server": "5.6.7.8", "port": 443,
     "uuid": "abc-123", "alterId": 0, "cipher": "auto", "tls": True,
     "network": "ws", "ws-opts": {"path": "/ws", "headers": {"Host": "b.com"}}},
    {"name": "美国 trojan", "type": "trojan", "server": "9.9.9.9", "port": 443,
     "password": "pw", "udp": True, "tls": True, "skip-cert-verify": True},
    {"name": "新加坡 ss", "type": "ss", "server": "10.0.0.1", "port": 8388,
     "cipher": "aes-256-gcm", "password": "pw", "udp": True},
    {"name": "韩国 hysteria2", "type": "hysteria2", "server": "10.0.0.2", "port": 8443,
     "password": "pw", "skip-cert-verify": True},
    {"name": "德国 anytls", "type": "anytls", "server": "10.0.0.3", "port": 443,
     "password": "pw", "tls": True},
    {"name": "台湾 grpc vmess", "type": "vmess", "server": "10.0.0.4", "port": 443,
     "uuid": "abc-456", "alterId": 0, "cipher": "auto", "tls": True,
     "network": "grpc", "grpc-opts": {"grpc-service-name": "gs"}},
    {"name": "英国 ssr", "type": "ssr", "server": "10.0.0.5", "port": 8080,
     "cipher": "aes-256-cfb", "password": "pw", "protocol": "origin", "obfs": "plain"},
]


def main() -> int:
    ap = argparse.ArgumentParser("config_check")
    ap.add_argument("--offline", action="store_true", help="不下载内核/geodata，缺失即失败")
    args = ap.parse_args()

    settings = load_settings()
    setup_logging(settings)
    ensure_dirs()

    results = [NodeResult(name=n["name"], type=n["type"], server=n["server"],
                          port=n["port"], delay=100 + i * 20, node=n)
               for i, n in enumerate(SAMPLE_NODES)]
    picked = yaml_builder.filter_nodes(results, settings)
    if not picked:
        print("FAIL: 样本节点全部被过滤（检查 select.exclude_insecure 等设置）")
        return 1

    cfg = yaml_builder.build_config(picked, settings)
    removed = yaml_builder.check_removed_keys(cfg)
    print(f"[1] 内核已移除字段检查 : {'PASS' if not removed else 'FAIL ' + str(removed)}")
    if removed:
        return 1

    text = yaml_builder.config_to_yaml(dict(cfg))
    target = OUTPUT_DIR / "config_check.yaml"
    target.write_text(text, encoding="utf-8")
    print(f"[2] 生成校验用配置     : {target} ({len(text)} 字节, {len(cfg['proxies'])} 节点)")
    if "global-client-fingerprint" in text:
        print("FAIL: 配置中仍含 global-client-fingerprint")
        return 1
    print("    不含 global-client-fingerprint : PASS")

    try:
        exe = ensure_core(settings)
        ensure_geo()
    except Exception as exc:  # noqa: BLE001
        print(f"[3] 内核准备失败: {exc}")
        return 1 if not args.offline else 0

    with tempfile.TemporaryDirectory(prefix="fnm_cc_") as tmp:
        wd = Path(tmp)
        for name in GEO_FILES:
            p = GEO_DIR / name
            if p.exists():
                try:
                    os.link(p, wd / name)
                except OSError:
                    shutil.copy2(p, wd / name)

        ok, out = test_config_file(exe, wd, target)
        print(f"[3] mihomo -t 校验      : {'PASS' if ok else 'FAIL'}")
        if not ok:
            print("    ---- 内核输出 ----")
            print("\n".join(out.strip().splitlines()[-15:]))
            return 1
        print("    " + (out.strip().splitlines()[-1] if out.strip() else ""))

        probe = build_probe_config([n for n, _r, _d in picked], free_port(), "cc", settings)
        probe = geo_paths(probe)
        (wd / "p.yaml").write_text(
            yaml.safe_dump(probe, allow_unicode=True, sort_keys=False), encoding="utf-8")
        core = MihomoCore(exe, wd, probe, controller_port=free_port(), secret="cc")
        try:
            core.start()
            avail = core.api_proxies()
            want = [n["name"] for n, _r, _d in picked]
            missing = [n for n in want if n not in avail]
            print(f"[4] 内核加载节点       : {len(want) - len(missing)}/{len(want)}"
                  f" → {'PASS' if not missing else 'FAIL ' + str(missing)}")
            groups = [g["name"] for g in cfg["proxy-groups"]]
            print(f"[5] 代理组数量         : {len(groups)} → {groups}")
            if missing:
                return 1
        finally:
            core.stop()

    print("\n结论：生成的配置可被 Clash Verge / mihomo 正常导入 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
