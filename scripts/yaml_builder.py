"""生成可直接导入 Clash Verge 的 mihomo 配置（带日期 / 订阅两种）。"""
from __future__ import annotations

import ipaddress
import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from util import LOG
from parser import sanitize_name

# ------------------------------------------------------------------ 地区识别
REGION_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("香港", ["香港", "hk", "hongkong", "hong kong", "🇭🇰", "深港", "沪港", "京港"]),
    ("台湾", ["台湾", "台灣", "tw", "taiwan", "🇹🇼", "中华电信", "彰化", "新北"]),
    ("日本", ["日本", "jp", "japan", "🇯🇵", "东京", "大阪", "埼玉", "tokyo", "osaka"]),
    ("新加坡", ["新加坡", "狮城", "sg", "singapore", "🇸🇬"]),
    ("美国", ["美国", "美國", "us", "usa", "united states", "🇺🇸", "洛杉矶", "圣何塞",
              "硅谷", "西雅图", "芝加哥", "纽约", "达拉斯", "凤凰城", "波特兰", "迈阿密",
              "los angeles", "san jose", "seattle", "chicago", "new york"]),
    ("韩国", ["韩国", "韓國", "kr", "korea", "🇰🇷", "首尔", "seoul"]),
    ("英国", ["英国", "英國", "uk", "united kingdom", "🇬🇧", "伦敦", "london"]),
    ("德国", ["德国", "德國", "de", "germany", "🇩🇪", "法兰克福", "frankfurt"]),
    ("法国", ["法国", "法國", "fr", "france", "🇫🇷", "巴黎", "paris"]),
    ("荷兰", ["荷兰", "荷蘭", "nl", "netherlands", "🇳🇱", "阿姆斯特丹"]),
    ("俄罗斯", ["俄罗斯", "俄羅斯", "ru", "russia", "🇷🇺", "莫斯科"]),
    ("加拿大", ["加拿大", "ca", "canada", "🇨🇦", "多伦多", "蒙特利尔"]),
    ("澳大利亚", ["澳大利亚", "澳洲", "au", "australia", "🇦🇺", "悉尼", "墨尔本"]),
    ("土耳其", ["土耳其", "tr", "turkey", "🇹🇷", "伊斯坦布尔"]),
    ("印度", ["印度", "in", "india", "🇮🇳", "孟买"]),
    ("巴西", ["巴西", "br", "brazil", "🇧🇷"]),
    ("阿根廷", ["阿根廷", "ar", "argentina", "🇦🇷"]),
    ("越南", ["越南", "vn", "vietnam", "🇻🇳"]),
    ("马来西亚", ["马来西亚", "馬來西亞", "my", "malaysia", "🇲🇾", "吉隆坡"]),
    ("泰国", ["泰国", "泰國", "th", "thailand", "🇹🇭", "曼谷"]),
    ("菲律宾", ["菲律宾", "ph", "philippines", "🇵🇭"]),
    ("印尼", ["印尼", "印度尼西亚", "id", "indonesia", "🇮🇩", "雅加达"]),
    ("瑞士", ["瑞士", "ch", "switzerland", "🇨🇭"]),
    ("瑞典", ["瑞典", "se", "sweden", "🇸🇪"]),
    ("波兰", ["波兰", "pl", "poland", "🇵🇱"]),
    ("乌克兰", ["乌克兰", "ua", "ukraine", "🇺🇦"]),
    ("爱尔兰", ["爱尔兰", "ie", "ireland", "🇮🇪"]),
    ("西班牙", ["西班牙", "es", "spain", "🇪🇸"]),
    ("意大利", ["意大利", "it", "italy", "🇮🇹"]),
    ("芬兰", ["芬兰", "fi", "finland", "🇫🇮"]),
    ("挪威", ["挪威", "no", "norway", "🇳🇴"]),
    ("丹麦", ["丹麦", "dk", "denmark", "🇩🇰"]),
    ("奥地利", ["奥地利", "at", "austria", "🇦🇹"]),
    ("捷克", ["捷克", "cz", "czech", "🇨🇿"]),
    ("罗马尼亚", ["罗马尼亚", "ro", "romania", "🇷🇴"]),
    ("南非", ["南非", "za", "south africa", "🇿🇦"]),
    ("以色列", ["以色列", "il", "israel", "🇮🇱"]),
    ("阿联酋", ["阿联酋", "迪拜", "ae", "emirates", "dubai", "🇦🇪"]),
    ("沙特", ["沙特", "sa", "saudi", "🇸🇦"]),
    ("哈萨克", ["哈萨克", "kz", "kazakhstan", "🇰🇿"]),
    ("蒙古", ["蒙古", "mn", "mongolia", "🇲🇳"]),
]

REGION_FLAGS = {
    "香港": "🇭🇰", "台湾": "🇹🇼", "日本": "🇯🇵", "新加坡": "🇸🇬", "美国": "🇺🇸",
    "韩国": "🇰🇷", "英国": "🇬🇧", "德国": "🇩🇪", "法国": "🇫🇷", "荷兰": "🇳🇱",
    "俄罗斯": "🇷🇺", "加拿大": "🇨🇦", "澳大利亚": "🇦🇺", "土耳其": "🇹🇷",
    "印度": "🇮🇳", "巴西": "🇧🇷", "阿根廷": "🇦🇷", "越南": "🇻🇳", "马来西亚": "🇲🇾",
    "泰国": "🇹🇭", "菲律宾": "🇵🇭", "印尼": "🇮🇩", "瑞士": "🇨🇭", "瑞典": "🇸🇪",
    "波兰": "🇵🇱", "乌克兰": "🇺🇦", "爱尔兰": "🇮🇪", "西班牙": "🇪🇸", "意大利": "🇮🇹",
    "芬兰": "🇫🇮", "挪威": "🇳🇴", "丹麦": "🇩🇰", "奥地利": "🇦🇹", "捷克": "🇨🇿",
    "罗马尼亚": "🇷🇴", "南非": "🇿🇦", "以色列": "🇮🇱", "阿联酋": "🇦🇪", "沙特": "🇸🇦",
    "哈萨克": "🇰🇿", "蒙古": "🇲🇳",
}

# 常用机房 IP 段 → 地区（粗粒度补充，仅当名称无法判断时使用）
IP_HINTS: List[Tuple[str, str]] = [
    ("104.28.", "美国"), ("172.64.", "美国"), ("172.67.", "美国"), ("104.16.", "美国"),
    ("162.159.", "美国"), ("188.114.", "美国"), ("198.41.", "美国"),
]


def detect_region(node: Dict[str, Any]) -> str:
    name = str(node.get("name", ""))
    low = name.lower()
    # 优先级：名称里 emoji / 中文关键词
    for region, keys in REGION_KEYWORDS:
        for k in keys:
            if k.isascii():
                if re.search(rf"(^|[^a-z]){re.escape(k)}([^a-z]|$)", low):
                    return region
            elif k in name:
                return region
    server = str(node.get("server", ""))
    for prefix, region in IP_HINTS:
        if server.startswith(prefix):
            return region
    return "其他"


# ------------------------------------------------------------------ 配置构建
INSECURE_TYPES = {"http", "socks5"}

# 新版 mihomo 已移除的配置字段名：写进配置会导致内核直接启动失败。
# 这里做黑名单防护，避免以后又手滑加回去。
REMOVED_CONFIG_KEYS = {"global-client-fingerprint"}


def check_removed_keys(cfg: Dict[str, Any]) -> List[str]:
    """返回配置中出现的新版内核已移除字段（应为空）。"""
    bad: List[str] = []
    for key in cfg:
        if key in REMOVED_CONFIG_KEYS:
            bad.append(str(key))
    return bad


def filter_nodes(results: Iterable[Any], settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把测速结果整理成待写入 YAML 的节点（含地区与评分）。"""
    select_cfg = settings.get("select", {})
    max_nodes = int(select_cfg.get("max_nodes", 200))
    max_per_region = int(select_cfg.get("max_per_region", 40))
    max_per_server = int(select_cfg.get("max_per_server", 2))
    exclude_insecure = bool(select_cfg.get("exclude_insecure", True))
    sort_by_delay = bool(select_cfg.get("sort_by_delay", True))

    pool = [r for r in results if getattr(r, "ok", False) and r.delay is not None]
    if exclude_insecure:
        skipped = [r for r in pool if r.type in INSECURE_TYPES]
        pool = [r for r in pool if r.type not in INSECURE_TYPES]
        if skipped:
            LOG.info("按 exclude_insecure 排除 %d 个明文代理（http/socks5）", len(skipped))
    if sort_by_delay:
        pool.sort(key=lambda r: r.delay)
    else:
        pool.sort(key=lambda r: (detect_region(r.node), r.delay))

    per_region: Dict[str, int] = {}
    per_server: Dict[str, int] = {}
    picked: List[Tuple[Dict[str, Any], str, int]] = []
    for r in pool:
        region = detect_region(r.node)
        server = str(r.node.get("server", "")).lower()
        if per_region.get(region, 0) >= max_per_region:
            continue
        if max_per_server > 0 and per_server.get(server, 0) >= max_per_server:
            continue
        per_region[region] = per_region.get(region, 0) + 1
        per_server[server] = per_server.get(server, 0) + 1
        picked.append((r.node, region, int(r.delay)))
        if len(picked) >= max_nodes:
            break
    return picked


def _dedupe_names(items: List[Tuple[Dict[str, Any], str, int]]) -> List[Tuple[Dict[str, Any], str, int]]:
    """兜底：确保写入 YAML 的节点名称唯一且 YAML 安全。"""
    seen: Dict[str, int] = {}
    out = []
    for node, region, delay in items:
        base = sanitize_name(node.get("name", ""),
                             f"{node.get('server', 'node')}:{node.get('port', '')}")
        candidate = base
        if candidate in seen:
            seen[candidate] += 1
            candidate = f"{base} ·{seen[base]}"
            while candidate in seen:
                seen[base] += 1
                candidate = f"{base} ·{seen[base]}"
        seen[candidate] = 1
        node = dict(node)
        node["name"] = candidate
        out.append((node, region, delay))
    return out


def build_config(picked: List[Tuple[Dict[str, Any], str, int]],
                 settings: Dict[str, Any], stats: Dict[str, Any] | None = None,
                 dated: bool = True) -> Dict[str, Any]:
    out_cfg = settings.get("output", {})
    picked = _dedupe_names(picked)
    proxies = [_apply_fingerprint(p) for p, _r, _d in picked]
    names = [p["name"] for p in proxies]

    by_region: "OrderedDict[str, List[str]]" = OrderedDict()
    for node, region, _delay in picked:
        by_region.setdefault(region, []).append(node["name"])

    main = str(out_cfg.get("main_group", "🚀 节点选择"))
    auto = str(out_cfg.get("auto_group", "♻️ 自动选择"))
    fallback = str(out_cfg.get("fallback_group", "🔁 故障转移"))

    # 组内成员顺序：延迟从低到高（picked 已排序）
    seq = ["DIRECT"] + ([auto] if len(names) > 1 else []) + \
          ([fallback] if len(names) > 1 else []) + \
          [f"{REGION_FLAGS.get(r, '🏳️')} {r}" for r, _ in by_region.items() if len(by_region[r]) >= 1] + \
          names

    groups: List[Dict[str, Any]] = []

    if len(names) > 1:
        groups.append({
            "name": auto, "type": "url-test", "proxies": names,
            "url": str(settings.get("test", {}).get("url", "http://www.gstatic.com/generate_204")),
            "interval": 300, "tolerance": 50, "lazy": False,
        })
        groups.append({
            "name": fallback, "type": "fallback", "proxies": names,
            "url": str(settings.get("test", {}).get("url", "http://www.gstatic.com/generate_204")),
            "interval": 300,
        })

    groups.append({"name": main, "type": "select", "proxies": _uniq_keep_order(seq)})

    # 地区组
    for region, members in by_region.items():
        groups.append({
            "name": f"{REGION_FLAGS.get(region, '🏳️')} {region}",
            "type": "url-test",
            "proxies": members,
            "url": str(settings.get("test", {}).get("url", "http://www.gstatic.com/generate_204")),
            "interval": 300, "tolerance": 50,
        })

    # 场景组
    groups.append({
        "name": "🌍 国外媒体", "type": "select",
        "proxies": _uniq_keep_order([main, auto, fallback] if len(names) > 1 else [main, "DIRECT"]),
    })
    groups.append({
        "name": "🤖 AI服务", "type": "select",
        "proxies": _uniq_keep_order([main, auto, fallback] if len(names) > 1 else [main, "DIRECT"]),
    })
    groups.append({
        "name": "📲 电报消息", "type": "select",
        "proxies": _uniq_keep_order([main, auto, fallback] if len(names) > 1 else [main, "DIRECT"]),
    })
    groups.append({"name": "🎯 全球直连", "type": "select", "proxies": ["DIRECT", main]})
    groups.append({"name": "🛑 广告拦截", "type": "select", "proxies": ["REJECT", "DIRECT"]})
    groups.append({"name": "🐟 漏网之鱼", "type": "select",
                   "proxies": _uniq_keep_order([main, "DIRECT"])})

    cfg: "OrderedDict[str, Any]" = OrderedDict()
    title = "FreeNodeMailer 每日可用节点"
    cfg["#"] = f"{title} | 生成时间(北京时间) {time.strftime('%Y-%m-%d %H:%M:%S')}"
    cfg["mixed-port"] = int(out_cfg.get("mixed_port", 7890))
    cfg["allow-lan"] = bool(out_cfg.get("allow_lan", False))
    cfg["bind-address"] = "*" if out_cfg.get("allow_lan") else "127.0.0.1"
    cfg["mode"] = str(out_cfg.get("mode", "rule"))
    cfg["log-level"] = "info"
    cfg["ipv6"] = bool(settings.get("test", {}).get("ipv6", True))
    cfg["unified-delay"] = True
    cfg["tcp-concurrent"] = True
    cfg["find-process-mode"] = "strict"
    # 注意：新版 mihomo 已移除 `global-client-fingerprint`（写了会导致配置加载失败）。
    # 指纹改为按节点写 `client-fingerprint`，见 _apply_fingerprint()。
    cfg["external-controller"] = "127.0.0.1:9097"
    cfg["geodata-mode"] = True
    cfg["geodata-loader"] = "standard"
    cfg["geo-auto-update"] = True
    cfg["geo-update-interval"] = 168
    cfg["profile"] = {"store-selected": True, "store-fake-ip": True}
    cfg["sniffer"] = {
        "enable": True,
        "sniff": {"HTTP": {"ports": [80, "8080-8880"], "override-destination": True},
                  "TLS": {"ports": [443, 8443]},
                  "QUIC": {"ports": [443, 8443]}},
        "skip-domain": ["Mijia Cloud", "+.push.apple.com"],
    }
    cfg["dns"] = {
        "enable": True,
        "listen": "127.0.0.1:1053",
        "ipv6": bool(settings.get("test", {}).get("ipv6", True)),
        "respect-rules": True,
        "enhanced-mode": "fake-ip",
        "fake-ip-range": "198.18.0.1/16",
        "fake-ip-filter": ["*.lan", "*.local", "+.msftconnecttest.com", "+.msftncsi.com",
                           "localhost.ptlogin2.qq.com", "+.qq.com", "+.wechat.com"],
        "default-nameserver": ["223.5.5.5", "119.29.29.29"],
        "nameserver": ["https://223.5.5.5/dns-query", "https://1.12.12.12/dns-query"],
        "proxy-server-nameserver": ["https://223.5.5.5/dns-query", "223.5.5.5"],
        "nameserver-policy": {
            "geosite:cn,private": ["https://223.5.5.5/dns-query", "223.5.5.5"],
            "geosite:geolocation-!cn": ["https://1.12.12.12/dns-query", "tls://8.8.8.8:853"],
        },
    }

    if bool(out_cfg.get("enable_rules", True)):
        cfg["proxies"] = proxies
        cfg["proxy-groups"] = groups
        cfg["rules"] = default_rules()
    else:
        cfg["proxies"] = proxies
        cfg["proxy-groups"] = groups
        cfg["rules"] = ["MATCH," + main]

    if stats:
        cfg["#stats"] = stats
    return cfg


def _apply_fingerprint(node: Dict[str, Any]) -> Dict[str, Any]:
    """给需要 TLS 指纹的节点补上 client-fingerprint。

    取代已被新版 mihomo 移除的 `global-client-fingerprint`。
    """
    n = dict(node)
    if n.get("client-fingerprint"):
        return n
    ptype = n.get("type")
    needs = ptype in {"vless", "vmess", "trojan", "anytls", "shadowtls", "juicity"} or \
        bool(n.get("tls")) or bool(n.get("reality-opts"))
    if needs:
        n["client-fingerprint"] = "chrome"
    return n


def _uniq_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for i in items:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def default_rules() -> List[str]:
    return [
        "GEOSITE,category-ads-all,🛑 广告拦截",
        "GEOIP,private,DIRECT,no-resolve",
        "GEOSITE,private,DIRECT",
        "GEOSITE,cn,DIRECT",
        "GEOIP,cn,DIRECT",
        "GEOSITE,openai,🤖 AI服务",
        "GEOSITE,anthropic,🤖 AI服务",
        "GEOSITE,google-gemini,🤖 AI服务",
        "GEOSITE,category-ai-chat-!cn,🤖 AI服务",
        "GEOSITE,youtube,🌍 国外媒体",
        "GEOSITE,netflix,🌍 国外媒体",
        "GEOSITE,disney,🌍 国外媒体",
        "GEOSITE,hbo,🌍 国外媒体",
        "GEOSITE,spotify,🌍 国外媒体",
        "GEOSITE,bilibili,🎯 全球直连",
        "GEOSITE,telegram,📲 电报消息",
        "GEOSITE,twitter,🚀 节点选择",
        "GEOSITE,google,🚀 节点选择",
        "GEOSITE,github,🚀 节点选择",
        "GEOSITE,geolocation-!cn,🚀 节点选择",
        "GEOIP,telegram,📲 电报消息,no-resolve",
        "MATCH,🐟 漏网之鱼",
    ]


def config_to_yaml(cfg: Dict[str, Any]) -> str:
    head = ""
    if "#" in cfg:
        head = f"# {cfg.pop('#')}\n"
    if "#stats" in cfg:
        st = cfg.pop("#stats")
        try:
            head += "# " + yaml.safe_dump(st, allow_unicode=True, default_flow_style=True).strip() + "\n"
        except yaml.YAMLError:
            pass
    body = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, width=4096,
                          default_flow_style=False)
    return head + body


def write_outputs(cfg: Dict[str, Any], out_dir: Path, settings: Dict[str, Any],
                  today: str) -> Dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    text = config_to_yaml(dict(cfg))
    dated = out_dir / f"{today}clash.yaml"
    plain = out_dir / "clash.yaml"
    dated.write_text(text, encoding="utf-8")
    plain.write_text(text, encoding="utf-8")
    LOG.info("已生成配置：%s (%d 节点, %.1f KB)", dated.name,
             len(cfg.get("proxies", [])), len(text.encode("utf-8")) / 1024)
    return {"dated": dated, "subscription": plain}
