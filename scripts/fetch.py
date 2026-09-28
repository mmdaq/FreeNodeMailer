
import requests
import yaml
import logging
import time
import json
from pathlib import Path
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

# GitHub 仓库信息（从环境变量读取，默认占位符）
GITHUB_REPO = "YOUR_USERNAME/FreeNodeMailer"
BRANCH = "main"

def fetch_from_url(url: str) -> list:
    """从单个 URL 抓取代理数据"""
    logger.info(f"Fetching from: {url}")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                logger.warning(f"HTTP {response.status_code} from {url} (attempt {attempt})")
                time.sleep(2)
                continue
            data = yaml.safe_load(response.text)
            if data is None:
                logger.warning(f"Empty data from {url}")
                return []
            # 兼容多种 YAML 结构
            proxies = (
                data.get("proxies", []) or
                data.get("clash", {}).get("proxies", []) or
                data.get("subscription-url", []) or
                data.get("proxy-providers", {}).values()
            )
            if isinstance(proxies, dict):
                proxies = list(proxies.values())
            # 过滤无效节点
            valid = [p for p in proxies if isinstance(p, dict) and p.get("server")]
            logger.info(f"  Got {len(valid)} valid proxies from {url}")
            return valid
        except Exception as e:
            logger.warning(f"Error fetching {url} (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(3)
    return []

def deduplicate(proxies: list) -> list:
    """去重，基于 server + port + uuid"""
    seen = set()
    out = []
    for p in proxies:
        key = (p.get("server", ""), p.get("port"), p.get("uuid", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out

def normalize_proxy(p: dict) -> dict:
    """标准化节点格式，确保包含必要字段"""
    # 常见字段映射
    name = p.get("name") or p.get("servername") or p.get("server")
    server = p.get("server") or p.get("host")
    port = p.get("port") or p.get("端口")
    
    # 返回标准化节点
    return {
        "name": name,
        "type": p.get("type", "vmess"),
        "server": server,
        "port": port,
        "cipher": p.get("cipher", "auto"),
        "password": p.get("password") or p.get("uuid", ""),
        **{k: v for k, v in p.items() if k not in ["name", "type", "server", "port", "cipher", "password"]}
    }

def generate_complete_config(proxies: list, github_repo: str, branch: str) -> dict:
    """生成完整的 Clash 配置文件（可直接使用 + 支持订阅）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 订阅 URL（Clash Meta 可通过此 URL 自动更新）
    sub_url = f"https://raw.githubusercontent.com/{github_repo}/{branch}/output/clash.yaml"
    
    config = {
        # 端口配置
        "mixed-port": 7890,
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        
        # DNS 配置
        "dns": {
            "enable": True,
            "listen": "127.0.0.1:1053",
            "enhanced-mode": "redir-host",
            "nameserver": ["https://223.5.5.5/dns-query", "https://dns.alidns.com/dns-query"],
            "fallback": ["https://8.8.8.8/dns-query"],
            "fallback-filter": {"geo-ip": False}
        },
        
        # 代理组配置
        "proxy-groups": [
            {
                "name": "🚀 节点选择",
                "type": "select",
                "proxies": ["♻️ 自动选择", "🇭🇰 香港节点", "🇯🇵 日本节点", "🇸🇬 新加坡节点", "🇺🇸 美国节点", "DIRECT"]
            },
            {
                "name": "♻️ 自动选择",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": ["ALL"]
            },
            {
                "name": "🐟 漏网之鱼",
                "type": "select",
                "proxies": ["🚀 节点选择", "DIRECT"]
            },
            {
                "name": "🇭🇰 香港节点",
                "type": "url-test",
                "filter": "港|hk|hongkong|HongKong",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "proxies": ["ALL"]
            },
            {
                "name": "🇯🇵 日本节点",
                "type": "url-test",
                "filter": "日|jp|japan|Tokyo",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "proxies": ["ALL"]
            },
            {
                "name": "🇸🇬 新加坡节点",
                "type": "url-test",
                "filter": "新|sg|singapore",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "proxies": ["ALL"]
            },
            {
                "name": "🇺🇸 美国节点",
                "type": "url-test",
                "filter": "美|us|unitedstates|america",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "proxies": ["ALL"]
            }
        ],
        
        # 规则配置
        "rules": [
            # 绕过大陆
            "GEOSITE,cn,DIRECT",
            "GEOIP,cn,DIRECT,no-resolve",
            # 节点选择
            "MATCH,🚀 节点选择"
        ],
        
        # 代理配置
        "proxies": proxies,
        
        # 元数据（订阅信息）
        "_meta": {
            "subcription-url": sub_url,
            "generated-at": now,
            "provider": "FreeNodeMailer"
        }
    }
    
    return config

def generate_providers_yaml(proxies: list, github_repo: str, branch: str) -> dict:
    """生成仅供 Clash Meta 订阅使用的 provider 格式"""
    sub_url = f"https://raw.githubusercontent.com/{github_repo}/{branch}/output/clash.yaml"
    
    return {
        "proxies": proxies,
        "_meta": {
            "subcription-url": sub_url,
            "generated-at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "provider": "FreeNodeMailer",
            "description": "每日免费节点自动推送"
        }
    }

def main():
    sources_file = Path("config/sources.txt")
    if not sources_file.exists():
        logger.error(f"Sources file not found: {sources_file}")
        return

    # 读取 GitHub 仓库信息
    repo_file = Path("config/github_repo.txt")
    if repo_file.exists():
        GITHUB_REPO = repo_file.read_text(encoding="utf8").strip()
    
    all_proxies = []
    failed_sources = []
    
    for url in sources_file.read_text(encoding="utf8").splitlines():
        url = url.strip()
        if not url or url.startswith("#"):
            continue
        proxies = fetch_from_url(url)
        if proxies:
            all_proxies.extend(proxies)
        else:
            failed_sources.append(url)

    # 去重
    unique_proxies = deduplicate(all_proxies)
    logger.info(f"Total unique proxies: {len(unique_proxies)}")

    # 保存输出
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # 1. 生成完整 Clash 配置文件（可直接使用）
    config = generate_complete_config(unique_proxies, GITHUB_REPO, BRANCH)
    yaml_path = output_dir / "clash.yaml"
    with open(yaml_path, "w", encoding="utf8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    logger.info(f"Saved complete config to {yaml_path}")

    # 2. 生成 provider 格式（Clash Meta 订阅用）
    providers = generate_providers_yaml(unique_proxies, GITHUB_REPO, BRANCH)
    provider_path = output_dir / "providers.yaml"
    with open(provider_path, "w", encoding="utf8") as f:
        yaml.safe_dump(providers, f, allow_unicode=True, sort_keys=False)
    logger.info(f"Saved providers to {provider_path}")

    # 3. 生成 HTML 报告
    report_path = output_dir / "report.html"
    report_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>FreeNodeMailer Daily Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; }}
        .stats {{ display: flex; gap: 20px; margin: 25px 0; }}
        .stat-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 12px; padding: 20px 30px; text-align: center; flex: 1; }}
        .stat-card.success {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }}
        .stat-card.warning {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }}
        .stat-num {{ font-size: 36px; font-weight: bold; }}
        .stat-label {{ font-size: 14px; opacity: 0.9; margin-top: 5px; }}
        .section {{ margin: 25px 0; padding: 20px; background: #f8f9fa; border-radius: 8px; }}
        .section h2 {{ margin-top: 0; color: #333; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #3498db; color: white; }}
        tr:hover {{ background: #f5f5f5; }}
        .success {{ color: #27ae60; }}
        .error {{ color: #e74c3c; }}
        .code {{ background: #f4f4f4; padding: 15px; border-radius: 6px; font-family: monospace; overflow-x: auto; }}
        .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; font-size: 12px; color: #999; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📬 FreeNodeMailer Daily Report</h1>
        <p><strong>生成时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="stats">
            <div class="stat-card success">
                <div class="stat-num">{len(unique_proxies)}</div>
                <div class="stat-label">可用节点</div>
            </div>
            <div class="stat-card">
                <div class="stat-num">{len([u for u in sources_file.read_text(encoding="utf8").splitlines() if u.strip() and not u.startswith('#')])}</div>
                <div class="stat-label">数据来源</div>
            </div>
            <div class="stat-card warning">
                <div class="stat-num">{len(failed_sources)}</div>
                <div class="stat-label">抓取失败</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📋 订阅方式</h2>
            <p><strong>Clash Verge / Clash Meta 用户：</strong></p>
            <div class="code">
# 在订阅列表中添加以下 URL：<br/>
https://raw.githubusercontent.com/{GITHUB_REPO}/{BRANCH}/output/clash.yaml
            </div>
            <p style="margin-top:15px"><strong>普通 Clash 用户：</strong>下载 <code>clash.yaml</code> 直接导入即可。</p>
        </div>
        
        <div class="section">
            <h2>📊 数据源状态</h2>
            <table>
                <tr><th>来源</th><th>状态</th></tr>
                {''.join(f'<tr><td>{u[:50]}...</td><td class="success">✓ OK</td></tr>' for u in [l.strip() for l in sources_file.read_text(encoding="utf8").splitlines() if l.strip() and not l.startswith('#') and u not in failed_sources])}
                {''.join(f'<tr><td>{u[:50]}...</td><td class="error">✗ 失败</td></tr>' for u in failed_sources)}
            </table>
        </div>
        
        <div class="footer">
            <p>FreeNodeMailer &mdash; 自动每日节点推送服务</p>
        </div>
    </div>
</body>
</html>"""
    report_path.write_text(report_html, encoding="utf8")
    logger.info(f"Saved report to {report_path}")
    
    # 输出摘要
    print(f"\n{'='*50}")
    print(f"📦 抓取完成")
    print(f"   可用节点: {len(unique_proxies)} 个")
    print(f"   完整配置: output/clash.yaml")
    print(f"   Provider: output/providers.yaml")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
