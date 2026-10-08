"""FreeNodeMailer 自检测试（不联网，验证解析 / 去重 / 命名 / 配置生成）。

运行：python scripts/selftest.py
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from parser import (  # noqa: E402
    dedupe, extract_nodes, normalize_all, parse_share_link, sanitize_name, unique_names,
)
from tester import NodeResult  # noqa: E402
import yaml_builder  # noqa: E402
from util import load_settings  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} {detail}")
        print(f"  ✗ {name}  {detail}")


def test_share_links() -> None:
    print("\n[1] v2ray 分享链接解析")

    # 关键回归：userinfo 里含 @（机场把标题塞进 uuid）
    n = parse_share_link(
        "vless://d2519b5e-495e-462e-9703-bbf68011d2f3@50.7.211.242:443"
        "?flow=xtls-rprx-vision&sid=b2b44805&pbk=8ENbaQRCWZk-wewSrdHq1_rVjJY4CrxqXUo_5vZNdi4"
        "&type=tcp&security=reality&sni=example.com#测试节点"
    )
    check("vless reality（userinfo 含 @）", bool(n) and n["server"] == "50.7.211.242"
          and n["port"] == 443 and n["uuid"].startswith("d2519b5e")
          and n["reality-opts"]["public-key"] == "8ENbaQRCWZk-wewSrdHq1_rVjJY4CrxqXUo_5vZNdi4",
          json.dumps(n, ensure_ascii=False)[:120] if n else "None")

    n = parse_share_link("vmess://" + base64.b64encode(json.dumps({
        "v": "2", "ps": "测试VMess", "add": "1.2.3.4", "port": "443", "id": "abc-123",
        "aid": "0", "scy": "auto", "net": "ws", "type": "none", "host": "a.com",
        "path": "/ws", "tls": "tls", "sni": "a.com",
    }).encode()).decode())
    check("vmess base64（ws+tls）", bool(n) and n["server"] == "1.2.3.4" and n["port"] == 443
          and n["network"] == "ws" and n["tls"] is True and n["path" if False else "ws-opts"]["path"] == "/ws",
          json.dumps(n, ensure_ascii=False)[:140] if n else "None")

    n = parse_share_link("ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ@1.2.3.4:8388#SS节点")
    check("ss（method:pass@host 形式）", bool(n) and n["cipher"] == "aes-256-gcm"
          and n["password"] == "password" and n["port"] == 8388,
          json.dumps(n, ensure_ascii=False)[:120] if n else "None")

    n = parse_share_link("ss://" + base64.urlsafe_b64encode(
        b"aes-256-gcm:pwd@5.6.7.8:8389").decode().rstrip("="))
    check("ss（整段 base64 形式）", bool(n) and n["server"] == "5.6.7.8" and n["port"] == 8389,
          json.dumps(n, ensure_ascii=False)[:120] if n else "None")

    n = parse_share_link("trojan://mypass@example.com:443?security=tls&sni=example.com#Trojan")
    check("trojan", bool(n) and n["server"] == "example.com" and n["password"] == "mypass"
          and n["tls"] is True, json.dumps(n, ensure_ascii=False)[:120] if n else "None")

    n = parse_share_link("hysteria2://auth123@1.1.1.1:8443?obfs=salamander&obfs-password=x#Hy2")
    check("hysteria2", bool(n) and n["type"] == "hysteria2" and n["port"] == 8443
          and n["obfs"] == "salamander", json.dumps(n, ensure_ascii=False)[:120] if n else "None")

    n = parse_share_link("socks5://user:pass@9.9.9.9:1080#Socks")
    check("socks5 带认证", bool(n) and n["username"] == "user" and n["password"] == "pass",
          json.dumps(n, ensure_ascii=False)[:120] if n else "None")

    # 非法输入必须被拒绝（否则会污染配置）
    check("拒绝无端口链接", parse_share_link("vless://uuid@host.com") is None)
    check("拒绝非法主机名", parse_share_link("vless://uuid@not a host:443") is None)
    check("拒绝非法端口", parse_share_link("trojan://x@host.com:999999") is None)


def test_yaml_and_normalize() -> None:
    print("\n[2] Clash YAML 解析与归一化")

    text = """
proxies:
  - {name: "干净节点", type: ss, server: 1.1.1.1, port: 443, cipher: aes-256-gcm, password: p}
  - {name: "缺字段", type: ss, server: 2.2.2.2, port: 443}
  - {name: "不支持协议", type: snellx, server: 3.3.3.3, port: 443}
  - {name: "坏主机", type: trojan, server: "bad host", port: 443, password: p}
"""
    nodes = extract_nodes(text)
    check("YAML 解析出 4 条原始记录", len(nodes) == 4, f"got {len(nodes)}")
    norm, stats = normalize_all(nodes)
    check("归一化保留 1 条合法节点", len(norm) == 1, f"got {len(norm)} stats={stats}")
    check("丢弃原因分类正确",
          stats["unsupported_type"] >= 1 and stats["bad_field"] >= 1, str(stats))

    # base64 订阅
    b64 = base64.b64encode(
        b"trojan://pw@a.com:443#A\nvless://u@b.com:443?security=tls#B\n"
    ).decode()
    nodes = extract_nodes(b64)
    check("base64 订阅解包出 2 个节点", len(nodes) == 2, f"got {len(nodes)}")


def test_dedupe_and_names() -> None:
    print("\n[3] 去重与命名安全（mihomo 重名会 fatal）")

    raw = [
        {"name": "dup", "type": "ss", "server": "1.1.1.1", "port": 443,
         "cipher": "aes-256-gcm", "password": "p"},
        {"name": "dup", "type": "ss", "server": "1.1.1.1", "port": 443,
         "cipher": "aes-256-gcm", "password": "p", "udp": True},   # 字段更全，应保留
        {"name": "dup", "type": "ss", "server": "1.1.1.2", "port": 443,
         "cipher": "aes-256-gcm", "password": "p"},
    ]
    norm, _ = normalize_all(raw)
    uniq, dropped = dedupe(norm)
    check("去重后剩 2 个", len(uniq) == 2, f"got {len(uniq)}")
    check("保留字段更完整的那条", any(n.get("udp") is True for n in uniq))

    dupes = [
        {"name": "same name", "type": "ss", "server": "1.1.1.1", "port": 443,
         "cipher": "aes-256-gcm", "password": "p"},
        {"name": "same name", "type": "ss", "server": "1.1.1.2", "port": 443,
         "cipher": "aes-256-gcm", "password": "p"},
        {"name": "same name", "type": "ss", "server": "1.1.1.3", "port": 443,
         "cipher": "aes-256-gcm", "password": "p"},
    ]
    norm, _ = normalize_all(dupes)
    named = unique_names(norm)
    names = [n["name"] for n in named]
    check("重名被消除", len(names) == len(set(names)), str(names))

    check("过滤 YAML 注释符 #", "#" not in sanitize_name("节点 #1"))
    check("过滤换行", "\n" not in sanitize_name("节点\n第二行"))
    check("空名称有兜底", sanitize_name("") != "")
    check("保留可读冒号（交由 YAML 加引号）", sanitize_name("节点: 香港") == "节点: 香港",
          repr(sanitize_name("节点: 香港")))


def test_config_build() -> None:
    print("\n[4] Clash Verge 配置生成")

    settings = load_settings()
    nodes = []
    results = []
    regions = ["香港", "日本", "美国", "香港", "日本"]
    for i, region in enumerate(regions):
        node = {"name": f"{region}节点{i}", "type": "trojan", "server": f"10.0.0.{i + 1}",
                "port": 443, "password": "p", "udp": True}
        nr = NodeResult(name=node["name"], type="trojan", server=node["server"],
                        port=443, delay=100 + i * 60, node=node)
        results.append(nr)
        nodes.append(node)

    picked = yaml_builder.filter_nodes(results, settings)
    check("filter_nodes 产出节点", len(picked) == 5, f"got {len(picked)}")
    check("按延迟升序", [d for _n, _r, d in picked] == sorted(d for _n, _r, d in picked))

    cfg = yaml_builder.build_config(picked, settings)
    check("包含 proxies", len(cfg.get("proxies", [])) == 5)
    check("包含自动选择组",
          any(g["type"] == "url-test" and "自动" in g["name"] for g in cfg["proxy-groups"]))
    check("包含故障转移组",
          any(g["type"] == "fallback" for g in cfg["proxy-groups"]))
    check("包含主选择组",
          any(g["name"] == settings["output"]["main_group"] for g in cfg["proxy-groups"]))
    check("包含地区组", any("香港" in g["name"] for g in cfg["proxy-groups"]))
    check("包含规则", len(cfg.get("rules", [])) > 5)
    check("包含 DNS 防污染配置", cfg.get("dns", {}).get("enhanced-mode") == "fake-ip")

    # 所有组引用的名字都必须存在（否则 Clash Verge 报错）
    all_names = {p["name"] for p in cfg["proxies"]}
    all_groups = {g["name"] for g in cfg["proxy-groups"]}
    builtin = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE"}
    bad_refs = []
    for g in cfg["proxy-groups"]:
        for member in g["proxies"]:
            if member not in all_names and member not in all_groups and member not in builtin:
                bad_refs.append(f"{g['name']} → {member}")
    check("代理组引用无悬空", not bad_refs, "; ".join(bad_refs[:5]))

    def rule_target(rule: str) -> str:
        parts = [p.strip() for p in rule.split(",")]
        if parts[-1].lower() == "no-resolve":
            parts = parts[:-1]
        return parts[-1]

    bad_rules = [r for r in cfg["rules"]
                 if not r.startswith("MATCH") and rule_target(r) not in all_groups
                 and rule_target(r) not in builtin]
    check("规则引用的组都存在", not bad_rules, str(bad_rules[:3]))

    text = yaml_builder.config_to_yaml(dict(cfg))
    reloaded = __import__("yaml").safe_load(text.split("\n", 1)[1])
    check("生成的 YAML 可被重新解析", isinstance(reloaded, dict) and "proxies" in reloaded)
    check("YAML 中无 # 注释污染节点名", "#1" not in text or "节点 #" not in text)

    # 回归：新版 mihomo 已移除 global-client-fingerprint，
    # 写进配置会让内核直接启动失败（本项目踩过这个坑）
    check("不含内核已移除的字段", not yaml_builder.check_removed_keys(cfg),
          str(yaml_builder.check_removed_keys(cfg)))
    check("YAML 文本中不含 global-client-fingerprint",
          "global-client-fingerprint" not in text)
    check("TLS 节点被补上 client-fingerprint",
          all(p.get("client-fingerprint") for p in cfg["proxies"]
              if p.get("tls") or p["type"] in {"vless", "trojan", "anytls"}))

    # 单节点场景（不生成 url-test 组，避免空组）
    one = yaml_builder.filter_nodes(results[:1], settings)
    cfg1 = yaml_builder.build_config(one, settings)
    check("单节点也能生成合法配置",
          len(cfg1["proxies"]) == 1 and cfg1["proxy-groups"][0]["name"] ==
          settings["output"]["main_group"])


def test_region_detect() -> None:
    print("\n[5] 地区识别")
    cases = [
        ({"name": "🇭🇰 香港 01", "server": "1.1.1.1"}, "香港"),
        ({"name": "JP-Tokyo-01", "server": "1.1.1.1"}, "日本"),
        ({"name": "美国 洛杉矶", "server": "1.1.1.1"}, "美国"),
        ({"name": "random node", "server": "104.28.1.1"}, "美国"),
        ({"name": "未知节点", "server": "1.1.1.1"}, "其他"),
    ]
    for node, expect in cases:
        got = yaml_builder.detect_region(node)
        check(f"{node['name']} → {expect}", got == expect, f"got {got}")


def main() -> int:
    print("=" * 62)
    print("FreeNodeMailer 自检测试")
    print("=" * 62)
    test_share_links()
    test_yaml_and_normalize()
    test_dedupe_and_names()
    test_config_build()
    test_region_detect()
    print("\n" + "=" * 62)
    print(f"结果：通过 {PASS} 项，失败 {FAIL} 项")
    if FAILURES:
        print("失败列表：")
        for f in FAILURES:
            print(f"  - {f}")
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
