"""节点解析：Clash YAML / base64 订阅 / 明文分享链接 → 统一 Clash proxy dict。"""
from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from util import LOG

PROXY_TYPES = {
    "ss", "ssr", "vmess", "vless", "trojan", "trojan-go", "hysteria", "hysteria2",
    "hy2", "tuic", "snell", "socks5", "http", "wireguard", "anytls", "mieru",
    "ssh", "vmess-http", "juicity", "shadowtls", "gost",
}

SUPPORTED_BY_MIHOMO = {
    "ss", "ssr", "vmess", "vless", "trojan", "hysteria", "hysteria2", "tuic",
    "snell", "socks5", "http", "wireguard", "anytls", "mieru", "ssh", "shadowtls",
    "juicity",
}

ALIASES = {
    "hy2": "hysteria2",
    "hysteria-2": "hysteria2",
    "trojan-go": "trojan",
    "vmess-http": "vmess",
    "socks": "socks5",
}

# 分享链接 scheme → clash type
SCHEME_MAP = {
    "ss": "ss", "ssr": "ssr", "vmess": "vmess", "vless": "vless",
    "trojan": "trojan", "hysteria": "hysteria", "hy2": "hysteria2",
    "hysteria2": "hysteria2", "tuic": "tuic", "socks5": "socks5",
    "socks": "socks5", "anytls": "anytls",
}

LINK_RE = re.compile(
    r"(?:ss|ssr|vmess|vless|trojan|hysteria2?|hy2|tuic|socks5?|anytls)://[^\s\"'<>\\]+",
    re.IGNORECASE,
)
B64_RE = re.compile(r"^[A-Za-z0-9+/=_\-\s]+$")

# 需要端口的类型
NEED_PORT = {"ss", "ssr", "vmess", "vless", "trojan", "hysteria", "hysteria2",
             "tuic", "socks5", "http", "snell", "anytls", "shadowtls", "juicity", "ssh"}

NETWORK_OK = {"", "tcp", "ws", "grpc", "h2", "http", "quic", "httpupgrade", "xhttp", "kcp"}


# ------------------------------------------------------------------ 基础
def _as_int(v: Any) -> Optional[int]:
    try:
        if v is None or v == "":
            return None
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _as_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _pick(d: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def maybe_b64_decode(text: str) -> Optional[str]:
    """若整段文本是 base64，返回解码结果，否则 None。"""
    s = re.sub(r"\s+", "", text)
    if len(s) < 16 or not B64_RE.match(s):
        return None
    pad = "=" * (-len(s) % 4)
    for cand in (s + pad, s.replace("-", "+").replace("_", "/") + pad):
        try:
            raw = base64.b64decode(cand, validate=False)
        except (binascii.Error, ValueError):
            continue
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if LINK_RE.search(decoded) or "proxies:" in decoded[:2000]:
            return decoded
    return None


# ------------------------------------------------------------------ v2ray 分享链接
def _parse_qs_pairs(query: str) -> Dict[str, str]:
    return {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items()}


_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9_\u4e00-\u9fff-]{1,63}(?<!-)"
    r"(?:\.(?!-)[A-Za-z0-9_\u4e00-\u9fff-]{1,63}(?<!-))*$"
)


def is_valid_host(host: str) -> bool:
    """主机合法性：域名或 IP（v4/v6）。"""
    host = (host or "").strip().strip("[]")
    if not host or len(host) > 253:
        return False
    if " " in host or "/" in host or "@" in host:
        return False
    try:
        import ipaddress
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    return bool(_HOSTNAME_RE.match(host))


def extract_authority(rest: str) -> Optional[Tuple[str, int]]:
    """从 `...@host:port[?query][#frag]` 里稳健地取出 host/port。

    v2ray 分享链接的 userinfo 里可能含有 `@`（例如某些机场把标题
    写进 uuid），所以必须用「最后一个 @」切分，并且只认最后一个
    冒号后面是纯数字的情况。
    """
    if not rest:
        return None
    body = rest.split("#", 1)[0].split("?", 1)[0]
    body = body.split("/", 1)[0]
    if "@" in body:
        body = body.rsplit("@", 1)[1]
    body = body.strip()
    if not body:
        return None
    if body.startswith("["):
        host, _, rest2 = body[1:].partition("]")
        port = _as_int(rest2.lstrip(":")) or 443
        return (host, port) if host else None
    if ":" in body:
        host, _, p = body.rpartition(":")
        port = _as_int(p)
        if port is None:
            return None
        return (host, port) if host else None
    return None


def _split_host_port(netloc: str, default_port: int = 443) -> Tuple[str, int]:
    netloc = (netloc or "").strip()
    if netloc.startswith("["):  # IPv6
        host, _, rest = netloc[1:].partition("]")
        port = _as_int(rest.lstrip(":")) or default_port
        return host, port
    if ":" in netloc:
        host, _, p = netloc.rpartition(":")
        port = _as_int(p) or default_port
        return host, port
    return netloc, default_port


def _tls_from_query(q: Dict[str, str], default: bool) -> bool:
    sec = (q.get("security") or "").lower()
    if sec in {"tls", "reality", "xtls"}:
        return True
    if q.get("tls") is not None:
        return str(q["tls"]).lower() in {"1", "true", "tls"}
    if q.get("allowInsecure") is not None:
        return True
    return default


def _transport_from_query(q: Dict[str, str]) -> Dict[str, Any]:
    net = (q.get("type") or q.get("network") or "tcp").lower()
    out: Dict[str, Any] = {}
    if net in {"", "tcp", "raw"}:
        if (q.get("headerType") or "").lower() == "http":
            out["network"] = "http"
            out["http-opts"] = {"path": [q.get("path", "/")]}
        return out
    out["network"] = "httpupgrade" if net == "httpupgrade" else net
    if net == "ws":
        out["ws-opts"] = {
            "path": unquote(q.get("path", "/")) or "/",
            "headers": {"Host": q.get("host") or q.get("sni") or ""},
        }
        out["ws-opts"]["headers"] = {k: v for k, v in out["ws-opts"]["headers"].items() if v}
    elif net == "grpc":
        out["grpc-opts"] = {"grpc-service-name": q.get("serviceName", "") or q.get("path", "")}
    elif net == "h2":
        out["h2-opts"] = {
            "path": unquote(q.get("path", "/")) or "/",
            "host": [h for h in [q.get("host")] if h],
        }
    elif net in {"http", "httpupgrade", "xhttp"}:
        out["network"] = "http" if net == "xhttp" else net
        if net != "http":
            out[f"{net}-opts"] = {
                "path": unquote(q.get("path", "/")) or "/",
                "headers": {k: v for k, v in {"Host": q.get("host", "")}.items() if v},
            }
    return out


def _apply_ss_plugin(node: Dict[str, Any], q: Dict[str, str]) -> None:
    """处理 ss 的 plugin / udp-over-tcp 参数。"""
    plugin = q.get("plugin")
    if plugin:
        pname, _, opts = plugin.partition(";")
        node["plugin"] = pname
        if opts:
            node["plugin-opts"] = {
                p.split("=", 1)[0]: (p.split("=", 1)[1] if "=" in p else "true")
                for p in opts.split(";") if p
            }
    if _as_bool(q.get("udp-over-tcp")):
        node["udp-over-tcp"] = True


def parse_share_link(link: str) -> Optional[Dict[str, Any]]:
    link = link.strip().rstrip(",")
    if not link or "://" not in link:
        return None
    scheme = link.split("://", 1)[0].lower()
    ptype = SCHEME_MAP.get(scheme)
    if not ptype:
        return None

    # ss 先把 body 规范化成唯一的明文形式 method:password@host:port，
    # 之后的通用解析逻辑就能正确处理（urlparse 无法处理 base64 与
    # userinfo 内含冒号的情况）。
    if ptype == "ss":
        body = link.split("://", 1)[1]
        head_all, _, tail = body.partition("#")
        ss_q = _parse_qs_pairs(head_all.split("?", 1)[1]) if "?" in head_all else {}
        head = head_all.split("?", 1)[0].strip()
        frag = ("#" + tail) if tail else ""

        if "@" in head:
            ui_raw = head.split("@", 1)[0]
            hostpart = head.split("@", 1)[1]
            ui_plain = unquote(ui_raw)
            if ":" not in ui_plain:
                dec_ui = _b64_try(ui_plain)
                if dec_ui and ":" in dec_ui:
                    ui_plain = dec_ui
        else:
            dec = _b64_try(head)
            if not dec or "@" not in dec:
                return None
            ui_plain, _, hostpart = dec.partition("@")
            hostpart = hostpart.split("?", 1)[0]

        if ":" not in ui_plain or not hostpart:
            return None
        link = f"ss://{ui_plain}@{hostpart}{frag}"
        u = urlparse(link)
        q = ss_q
    else:
        try:
            u = urlparse(link)
        except ValueError:
            return None
        q = _parse_qs_pairs(u.query)
    userinfo = unquote(u.username or "")
    password = unquote(u.password or "")

    if ptype == "ss":
        # 用规范化后的字符串重新取 userinfo，避免 urlparse 对
        # "method:password" 里含冒号/非法的处理差异
        ss_ui = link.split("://", 1)[1].split("@", 1)[0]
        if "#" in ss_ui:
            ss_ui = ss_ui.split("#", 1)[0]
        method, _, pw = unquote(ss_ui).partition(":")
        if not method:
            return None
        auth = extract_authority(link.split("://", 1)[1])
        if not auth:
            return None
        host, port = auth
        if not is_valid_host(host) or not port:
            return None
        node = {"name": unquote(u.fragment) or f"{host}:{port}", "type": "ss",
                "server": host, "port": port, "cipher": method, "password": pw}
        _apply_ss_plugin(node, q)
        return node

    if ptype == "ssr":
        dec = maybe_b64_decode(link.split("://", 1)[1]) or _b64_try(link.split("://", 1)[1])
        if not dec:
            return None
        main, _, tail = dec.partition("/?")
        parts = main.split(":")
        if len(parts) < 6:
            return None
        host, port, proto, method, obfs = parts[0], _as_int(parts[1]), parts[2], parts[3], parts[4]
        pwd_b64 = ":".join(parts[5:])
        pwd = _b64_try(pwd_b64) or pwd_b64
        if not host or not port:
            return None
        tq = _parse_qs_pairs(tail)
        node = {"name": f"{host}:{port}", "type": "ssr", "server": host, "port": port,
                "cipher": method, "password": pwd, "protocol": proto, "obfs": obfs}
        rem = tq.get("remarks")
        if rem:
            node["name"] = _b64_try(rem) or rem
        for src, dst in (("protoparam", "protocol-param"), ("obfsparam", "obfs-param")):
            if tq.get(src):
                node[dst] = _b64_try(tq[src]) or tq[src]
        return node

    if ptype == "vmess":
        body = link.split("://", 1)[1]
        dec = maybe_b64_decode(body) or _b64_try(body)
        if not dec:
            return None
        try:
            j = json.loads(dec)
        except ValueError:
            return None
        host = str(j.get("add", "")).strip()
        port = _as_int(j.get("port"))
        if not host or not port:
            return None
        node: Dict[str, Any] = {
            "name": str(j.get("ps") or f"{host}:{port}"),
            "type": "vmess",
            "server": host,
            "port": port,
            "uuid": str(j.get("id", "")).strip(),
            "alterId": _as_int(j.get("aid")) or 0,
            "cipher": str(j.get("scy") or "auto") or "auto",
        }
        if not node["uuid"]:
            return None
        if str(j.get("tls", "")).lower() in {"tls", "true", "1", "reality"}:
            node["tls"] = True
        net = str(j.get("net", "tcp") or "tcp").lower()
        if net and net != "tcp":
            node["network"] = net
        if net == "ws":
            node["ws-opts"] = {
                "path": str(j.get("path") or "/"),
                "headers": {k: v for k, v in {"Host": j.get("host")}.items() if v},
            }
        elif net == "grpc":
            node["grpc-opts"] = {"grpc-service-name": str(j.get("path") or "")}
        elif net == "h2":
            node["h2-opts"] = {"path": str(j.get("path") or "/"),
                               "host": [j["host"]] if j.get("host") else []}
        sni = j.get("sni") or j.get("host")
        if sni:
            node["servername"] = str(sni)
        if str(j.get("tls", "")).lower() == "reality":
            node["reality-opts"] = {
                "public-key": str(j.get("pbk", "")),
                "short-id": str(j.get("sid", "")),
            }
        if _as_bool(j.get("allowInsecure")) or _as_bool(j.get("skip-cert-verify")):
            node["skip-cert-verify"] = True
        return node

    # vless / trojan / hysteria / hysteria2 / tuic / socks5 / anytls
    # 注意：userinfo 里可能含 `@`，urlparse 会误判 hostname，
    # 所以优先用「最后一个 @」自行解析 authority。
    authority = extract_authority(link.split("://", 1)[1])
    if authority is None:
        if not u.hostname:
            return None
        host, port = _split_host_port(u.netloc, 443)
    else:
        host, port = authority
    if not is_valid_host(host):
        return None
    if not (port and 0 < port < 65536):
        return None
    name = unquote(u.fragment) or f"{host}:{port}"
    tls = _tls_from_query(q, default=ptype in {"vless", "trojan", "hysteria2", "anytls"})

    if ptype == "vless":
        if not userinfo:
            return None
        node = {"name": name, "type": "vless", "server": host, "port": port, "uuid": userinfo,
                "udp": True}
    elif ptype == "trojan":
        if not (userinfo or password):
            return None
        node = {"name": name, "type": "trojan", "server": host, "port": port,
                "password": userinfo or password, "udp": True}
    elif ptype == "hysteria2":
        auth = userinfo or password
        node = {"name": name, "type": "hysteria2", "server": host, "port": port, "password": auth}
        if q.get("obfs"):
            node["obfs"] = q["obfs"]
            node["obfs-password"] = q.get("obfs-password", "")
        if q.get("insecure") or q.get("allowInsecure"):
            node["skip-cert-verify"] = True
    elif ptype == "hysteria":
        node = {"name": name, "type": "hysteria", "server": host, "port": port,
                "auth-str": userinfo or q.get("auth", ""), "protocol": q.get("protocol", "udp")}
        if q.get("peer") or q.get("sni"):
            node["sni"] = q.get("peer") or q.get("sni")
        if q.get("obfs"):
            node["obfs"] = q["obfs"]
        if q.get("upmbps"):
            node["up"] = q["upmbps"]
        if q.get("downmbps"):
            node["down"] = q["downmbps"]
        if q.get("alpn"):
            node["alpn"] = [a for a in q["alpn"].split(",") if a]
        if q.get("insecure"):
            node["skip-cert-verify"] = True
    elif ptype == "tuic":
        node = {"name": name, "type": "tuic", "server": host, "port": port,
                "uuid": userinfo, "password": password}
        node["udp-relay-mode"] = q.get("udp_relay_mode", "native")
        if q.get("congestion_control"):
            node["congestion-controller"] = q["congestion_control"]
        if q.get("alpn"):
            node["alpn"] = [a for a in q["alpn"].split(",") if a]
        if q.get("allow_insecure") or q.get("insecure"):
            node["skip-cert-verify"] = True
    elif ptype == "socks5":
        node = {"name": name, "type": "socks5", "server": host, "port": port,
                "username": userinfo, "password": password}
        if tls:
            node["tls"] = True
    elif ptype == "anytls":
        node = {"name": name, "type": "anytls", "server": host, "port": port,
                "password": userinfo or password}
    else:
        return None

    if ptype in {"vless", "trojan", "anytls"}:
        node["tls"] = tls
    if q.get("sni") or q.get("peer") or q.get("host"):
        node["servername"] = q.get("sni") or q.get("peer") or q.get("host")
    if q.get("alpn") and "alpn" not in node and ptype != "hysteria":
        node["alpn"] = [a for a in q["alpn"].split(",") if a]
    if q.get("fp"):
        node["client-fingerprint"] = q["fp"]
    if q.get("flow"):
        node["flow"] = q["flow"]
    if ptype == "vless" and q.get("security", "").lower() == "reality":
        node["reality-opts"] = {"public-key": q.get("pbk", ""), "short-id": q.get("sid", "")}
        node["client-fingerprint"] = q.get("fp", "chrome")
    if (q.get("allowInsecure") or q.get("insecure") or q.get("allow_insecure")) and ptype != "hysteria2":
        node["skip-cert-verify"] = True
    node.update(_transport_from_query(q))
    if "network" in node and node["network"] not in NETWORK_OK:
        node.pop("network", None)
    return node


def _b64_try(s: str) -> Optional[str]:
    s = re.sub(r"\s+", "", s or "")
    if not s:
        return None
    pad = "=" * (-len(s) % 4)
    for cand in (s + pad, s.replace("-", "+").replace("_", "/") + pad):
        try:
            return base64.b64decode(cand, validate=False).decode("utf-8", errors="strict")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
    return None


# ------------------------------------------------------------------ Clash YAML
def parse_clash_yaml(text: str) -> List[Dict[str, Any]]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        LOG.debug("YAML 解析失败：%s", exc)
        return []
    if not isinstance(data, dict):
        return []
    proxies = data.get("proxies") or data.get("Proxy") or []
    if not isinstance(proxies, list):
        return []
    return [p for p in proxies if isinstance(p, dict)]


def parse_provider(text: str) -> List[Dict[str, Any]]:
    """Clash provider 格式（顶层直接是节点数组）。"""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict) and "server" in p]
    if isinstance(data, dict) and isinstance(data.get("proxies"), list):
        return [p for p in data["proxies"] if isinstance(p, dict)]
    return []


# ------------------------------------------------------------------ 归一化
def normalize_proxy(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ptype = str(_pick(raw, "type", "protocol") or "").lower().strip()
    ptype = ALIASES.get(ptype, ptype)
    if ptype not in SUPPORTED_BY_MIHOMO:
        return None

    server = str(_pick(raw, "server", "address", "host") or "").strip()
    if server.startswith("[") and server.endswith("]"):
        server = server[1:-1]
    port = _as_int(_pick(raw, "port", "server_port"))
    if not is_valid_host(server):
        return None
    if ptype in NEED_PORT and not (port and 0 < port < 65536):
        return None

    node: Dict[str, Any] = {"name": str(raw.get("name") or f"{server}:{port}").strip(),
                            "type": ptype, "server": server}
    if port:
        node["port"] = port

    if ptype in {"ss", "ssr"}:
        cipher = _pick(raw, "cipher", "method", "encrypt-method")
        pwd = _pick(raw, "password", "passwd")
        if not cipher or pwd in (None, ""):
            return None
        node["cipher"] = str(cipher)
        node["password"] = str(pwd)
        if ptype == "ssr":
            node["protocol"] = str(_pick(raw, "protocol") or "origin")
            node["obfs"] = str(_pick(raw, "obfs") or "plain")
            for src, dst in (("protocol-param", "protocol-param"),
                             ("protocolparam", "protocol-param"),
                             ("obfs-param", "obfs-param"), ("obfsparam", "obfs-param")):
                if raw.get(src) not in (None, ""):
                    node[dst] = str(raw[src])
    elif ptype in {"vmess", "vless"}:
        uuid = _pick(raw, "uuid", "id", "password")
        if not uuid:
            return None
        node["uuid"] = str(uuid).strip()
        if ptype == "vmess":
            node["alterId"] = _as_int(_pick(raw, "alterId", "alterid", "aid")) or 0
            node["cipher"] = str(_pick(raw, "cipher", "scy") or "auto")
    elif ptype in {"trojan", "anytls", "hysteria2"}:
        pwd = _pick(raw, "password", "auth", "auth-str", "auth_str")
        if ptype == "hysteria2":
            if pwd in (None, ""):
                return None
            node["password"] = str(pwd)
        else:
            if pwd in (None, ""):
                return None
            node["password"] = str(pwd)
    elif ptype == "snell":
        psk = _pick(raw, "psk", "password")
        if not psk:
            return None
        node["psk"] = str(psk)
        node["version"] = _as_int(raw.get("version")) or 1
    elif ptype in {"socks5", "http"}:
        if raw.get("username") not in (None, ""):
            node["username"] = str(raw["username"])
        if raw.get("password") not in (None, ""):
            node["password"] = str(raw["password"])

    # 通用可选字段透传
    passthrough = (
        "tls", "udp", "network", "ws-opts", "grpc-opts", "h2-opts", "http-opts",
        "httpupgrade-opts", "reality-opts", "servername", "sni", "skip-cert-verify",
        "alpn", "client-fingerprint", "flow", "obfs", "obfs-password", "up", "down",
        "protocol", "congestion-controller", "udp-relay-mode", "reduce-rtt",
        "plugin", "plugin-opts", "udp-over-tcp", "ports", "hop-interval",
        "fingerprint", "ip-version", "max-udp-relay-packet-size", "auth", "auth-str",
        "recv-window-conn", "recv-window", "disable-sni", "ca", "ca-str", "interface-name",
        "routing-mark", "tfo", "mptcp", "health-check", "ecn", "packet-encoding",
        "smux", "brutal-opts", "heartbeat-interval", "idle-session-check-interval",
        "idle-session-timeout", "min-idle-session", "bandwidth", "cc", "ss-opts",
    )
    for key in passthrough:
        if key in raw and raw[key] not in (None, ""):
            node[key] = raw[key]

    # sni / servername 归一
    if "sni" in node and "servername" not in node:
        node["servername"] = node.pop("sni")
    if ptype == "hysteria" and "servername" in node and "sni" not in node:
        node["sni"] = node.pop("servername")

    # 数值型字段归一
    for k in ("alterId", "port", "up", "down"):
        if k in node:
            v = _as_int(node[k])
            if v is not None and k in ("alterId", "port"):
                node[k] = v
    for k in ("tls", "udp", "skip-cert-verify", "udp-over-tcp", "tfo", "mptcp", "reduce-rtt"):
        if k in node:
            node[k] = _as_bool(node[k])
    if isinstance(node.get("alpn"), str):
        node["alpn"] = [a.strip() for a in node["alpn"].split(",") if a.strip()]

    # 名称只做基础清理（去换行/控制字符），不做截断——
    # 截断会造成重名，而 mihomo 对重名节点是致命错误。
    # 唯一的截断与去重在 yaml_builder.unique_names 里统一处理。
    node["name"] = re.sub(r"[\x00-\x1f\x7f]", "", node["name"]).strip() or f"{server}:{port}"
    return node


def extract_nodes(text: str) -> List[Dict[str, Any]]:
    """从任意订阅文本中提取节点（YAML + 分享链接 + base64）。"""
    found: List[Dict[str, Any]] = []

    # 1) 先试 YAML（Clash / provider）
    if "proxies:" in text[:5000] or text.lstrip().startswith(("---", "proxies", "Proxy")):
        found.extend(parse_clash_yaml(text))
    if not found:
        found.extend(parse_provider(text))

    # 2) 分享链接（含 base64 解包）
    body = text
    if not LINK_RE.search(body):
        dec = maybe_b64_decode(text)
        if dec:
            body = dec
    for m in LINK_RE.finditer(body):
        node = parse_share_link(m.group(0))
        if node:
            found.append(node)

    return found


def normalize_all(raws: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """归一化 + 统计被丢弃的原因。"""
    stats = {"total": 0, "kept": 0, "unsupported_type": 0, "bad_field": 0}
    out: List[Dict[str, Any]] = []
    for raw in raws:
        stats["total"] += 1
        ptype = str(_pick(raw, "type", "protocol") or "").lower().strip()
        ptype = ALIASES.get(ptype, ptype)
        node = normalize_proxy(raw)
        if node is None:
            if ptype and ptype not in SUPPORTED_BY_MIHOMO:
                stats["unsupported_type"] += 1
            else:
                stats["bad_field"] += 1
            continue
        out.append(node)
    stats["kept"] = len(out)
    return out, stats


def dedupe(nodes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """按 (type, server, port, 关键凭据) 去重，保留字段更完整的一个。"""
    best: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        cred = n.get("uuid") or n.get("password") or n.get("psk") or ""
        key = f"{n['type']}|{n.get('server','').lower()}|{n.get('port')}|{cred}"
        prev = best.get(key)
        if prev is None or len(n) > len(prev):
            best[key] = n
    uniq = list(best.values())
    return uniq, len(nodes) - len(uniq)


_NAME_UNSAFE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_name(name: str, fallback: str = "node") -> str:
    """把节点名洗成安全字符串。

    清理控制字符 / 换行；`#` 会被 YAML 当成注释起始，必须去掉。
    冒号、逗号等由 yaml.safe_dump 自动加引号处理，保留可读性。
    """
    s = re.sub(r"[\x00-\x1f\x7f]", " ", str(name or ""))
    s = s.replace("#", " ")
    s = re.sub(r"\s+", " ", s).strip(" -_.")
    return s[:48] or fallback


def unique_names(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """确保节点名称唯一且安全（mihomo 对重名节点直接 fatal）。"""
    seen: Dict[str, int] = {}
    for i, n in enumerate(nodes):
        base = sanitize_name(n.get("name", ""), f"{n.get('server', 'node')}:{n.get('port', '')}")
        candidate = base
        if candidate in seen:
            seen[candidate] += 1
            candidate = f"{base} ·{seen[base]}"
            while candidate in seen:
                seen[base] += 1
                candidate = f"{base} ·{seen[base]}"
        seen[candidate] = 1
        n = dict(n)
        n["name"] = candidate
        nodes[i] = n
    return nodes
