
import requests
import yaml
import logging
import time
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# 测速配置
SPEED_TEST_URL = "http://www.gstatic.com/generate_204"
SPEED_TEST_TIMEOUT = 3  # 每节点超时秒数
MAX_CONCURRENT_SPEEDTEST = 30  # 并发测速数量
MAX_NODE_COUNT = 200  # 最多测速节点（取前N个）

# GitHub 仓库信息
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

def test_node_speed(proxy: dict) -> dict:
    """测试单个节点的延迟（毫秒）"""
    server = proxy.get("server", "")
    port = proxy.get("port", 443)
    proxy_type = proxy.get("type", "vmess")
    
    # 根据类型构造测试 URL
    if proxy_type == "trojan":
        url = f"https://{server}:{port}"
    elif proxy_type in ("vmess", "vless"):
        url = f"https://{server}:{port}"
    elif proxy_type == "ss":
        url = f"https://{server}:{port}"
    else:
        url = f"http://{server}:{port}"
    
    try:
        session = requests.Session()
        proxies_for_req = {
            "http": url,
            "https": url
        }
        start = time.time()
        resp = session.get(SPEED_TEST_URL, timeout=SPEED_TEST_TIMEOUT, proxies=proxies_for_req, verify=False)
        delay = (time.time() - start) * 1000  # 转换为毫秒
        session.close()
        proxy["delay"] = round(delay, 2)
        return proxy
    except Exception as e:
        proxy["delay"] = -1  # 不可用
        return proxy

def speed_test_all(proxies: list) -> list:
    """对节点进行测速，返回按延迟排序的列表"""
    if not proxies:
        return []
    
    # 限制测速数量
    limited = proxies[:MAX_NODE_COUNT]
    logger.info(f"Starting speed test for {len(limited)} proxies...")
    
    result = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SPEEDTEST) as executor:
        future_to_proxy = {executor.submit(test_node_speed, p): p for p in limited}
        for future in as_completed(future_to_proxy, timeout=300):
            try:
                proxy = future.result()
                result.append(proxy)
            except Exception as e:
                logger.debug(f"Speed test error: {e}")
    
    # 按延迟排序（-1 表示不可用，放最后）
    def sort_key(p):
        d = p.get("delay", -1)
        return d if d > 0 else 99999
    
    result.sort(key=sort_key)
    
    # 统计
    available = sum(1 for p in result if p.get("delay", -1) > 0)
    avg_delay = sum(p.get("delay", 0) for p in result if p.get("delay", -1) > 0) / max(available, 1)
    logger.info(f"Speed test done: {available}/{len(result)} available, avg delay: {avg_delay:.1f}ms")
    
    return result

def generate_complete_config(proxies: list, github_repo: str, branch: str) -> dict:
    """生成完整的 Clash 配置文件（可直接使用 + 支持订阅）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 订阅 URL
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
            "GEOSITE,cn,DIRECT",
            "GEOIP,cn,DIRECT,no-resolve",
            "MATCH,🚀 节点选择"
        ],
        
        # 代理配置（含延迟信息）
        "proxies": proxies,
        
        # 元数据
        "_meta": {
            "subcription-url": sub_url,
            "generated-at": now,
            "provider": "FreeNodeMailer",
            "speed-test": {
                "url": SPEED_TEST_URL,
                "timeout": SPEED_TEST_TIMEOUT,
                "max_concurrent": MAX_CONCURRENT_SPEEDTEST
            }
        }
    }
    
    return config

def main():
    sources_file = Path("config/sources.txt")
    if not sources_file.exists():
        logger.error(f"Sources file not found: {sources_file}")
        return

    # 读取 GitHub 仓库信息
    repo_file = Path("config/github_repo.txt")
    if repo_file.exists():
        global GITHUB_REPO
        GITHUB_REPO = repo_file.read_text(encoding="utf8").strip()
    
    all_proxies = []
    failed_sources = []
    
    # 1. 抓取节点
    logger.info("="*50)
    logger.info("Step 1: Fetching proxies from sources...")
    logger.info("="*50)
    
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
    logger.info(f"Total unique proxies after dedup: {len(unique_proxies)}")

    # 2. 测速
    logger.info("="*50)
    logger.info("Step 2: Speed testing proxies...")
    logger.info("="*50)
    
    timed_proxies = speed_test_all(unique_proxies)
    
    # 统计
    available = sum(1 for p in timed_proxies if p.get("delay", -1) > 0)
    avg_delay = sum(p.get("delay", 0) for p in timed_proxies if p.get("delay", -1) > 0) / max(available, 1)
    min_delay = min((p.get("delay", 99999) for p in timed_proxies if p.get("delay", -1) > 0), default=0)
    max_delay = max((p.get("delay", 0) for p in timed_proxies if p.get("delay", -1) > 0), default=0)
    
    logger.info(f"Speed test summary:")
    logger.info(f"  Available: {available}/{len(timed_proxies)}")
    logger.info(f"  Avg delay: {avg_delay:.1f}ms")
    logger.info(f"  Min delay: {min_delay:.1f}ms")
    logger.info(f"  Max delay: {max_delay:.1f}ms")

    # 3. 保存输出
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # 完整配置
    config = generate_complete_config(timed_proxies, GITHUB_REPO, BRANCH)
    yaml_path = output_dir / "clash.yaml"
    with open(yaml_path, "w", encoding="utf8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    logger.info(f"Saved complete config to {yaml_path}")

    # Provider 格式
    provider_path = output_dir / "providers.yaml"
    with open(provider_path, "w", encoding="utf8") as f:
        yaml.safe_dump({"proxies": timed_proxies}, f, allow_unicode=True, sort_keys=False)
    logger.info(f"Saved providers to {provider_path}")

    # HTML 报告
    report_path = output_dir / "report.html"
    report_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>FreeNodeMailer Daily Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; }}
        .stats {{ display: flex; gap: 15px; margin: 25px 0; flex-wrap: wrap; }}
        .stat-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 12px; padding: 20px; text-align: center; flex: 1; min-width: 120px; }}
        .stat-card.success {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }}
        .stat-card.warning {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }}
        .stat-card.info {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }}
        .stat-num {{ font-size: 28px; font-weight: bold; }}
        .stat-label {{ font-size: 13px; opacity: 0.9; margin-top: 5px; }}
        .section {{ margin: 25px 0; padding: 20px; background: #f8f9fa; border-radius: 8px; }}
        .section h2 {{ margin-top: 0; color: #333; font-size: 18px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #3498db; color: white; }}
        tr:hover {{ background: #f5f5f5; }}
        .delay-good {{ color: #27ae60; font-weight: bold; }}
        .delay-ok {{ color: #f39c12; }}
        .delay-bad {{ color: #e74c3c; }}
        .success {{ color: #27ae60; }}
        .error {{ color: #e74c3c; }}
        .code {{ background: #f4f4f4; padding: 15px; border-radius: 6px; font-family: monospace; overflow-x: auto; font-size: 13px; }}
        .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; font-size: 12px; color: #999; text-align: center; }}
        .top-nodes {{ max-height: 200px; overflow-y: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📬 FreeNodeMailer Daily Report</h1>
        <p><strong>生成时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="stats">
            <div class="stat-card success">
                <div class="stat-num">{len(timed_proxies)}</div>
                <div class="stat-label">总节点</div>
            </div>
            <div class="stat-card">
                <div class="stat-num">{available}</div>
                <div class="stat-label">可用节点</div>
            </div>
            <div class="stat-card info">
                <div class="stat-num">{avg_delay:.0f}ms</div>
                <div class="stat-label">平均延迟</div>
            </div>
            <div class="stat-card warning">
                <div class="stat-num">{len(failed_sources)}</div>
                <div class="stat-label">源失败</div>
            </div>
        </div>
        
        <div class="section">
            <h2>🏆 延迟最低 TOP 10</h2>
            <table>
                <tr><th>排名</th><th>名称</th><th>类型</th><th>服务器</th><th>延迟</th></tr>
                {''.join([f'<tr><td>{i+1}</td><td>{p.get("name","")}</td><td>{p.get("type","")}</td><td>{p.get("server","")}:{p.get("port","")}</td><td class="delay-good">{p.get("delay","-")}ms</td></tr>' for i,p in enumerate(timed_proxies[:10]) if p.get("delay",-1) > 0])}
            </table>
        </div>
        
        <div class="section">
            <h2>📋 订阅方式</h2>
            <p><strong>Clash Verge / Clash Meta 用户：</strong></p>
            <div class="code">
https://raw.githubusercontent.com/{GITHUB_REPO}/{BRANCH}/output/clash.yaml
            </div>
            <p style="margin-top:15px"><strong>普通 Clash 用户：</strong>下载 <code>clash.yaml</code> 直接导入即可。</p>
        </div>
        
        <div class="section">
            <h2>📊 数据源状态</h2>
            <table>
                <tr><th>来源</th><th>状态</th></tr>
                {''.join([f'<tr><td>{url[:40]}...</td><td class="success">✓ OK</td></tr>' for url in [line.strip() for line in sources_file.read_text(encoding="utf8").splitlines() if line.strip() and not line.startswith('#')] if url not in failed_sources])}
                {''.join([f'<tr><td>{url[:40]}...</td><td class="error">✗ 失败</td></tr>' for url in failed_sources])}
            </table>
        </div>
        
        <div class="footer">
            <p>FreeNodeMailer &mdash; 自动每日节点推送服务 | 测速延迟已包含在各节点中</p>
        </div>
    </div>
</body>
</html>"""
    report_path.write_text(report_html, encoding="utf8")
    logger.info(f"Saved report to {report_path}")
    
    # 输出摘要
    print("\n" + "="*50)
    print("抓取完成")
    print(f"可用节点: {len(timed_proxies)} 个 (可用: {available})")
    print(f"平均延迟: {avg_delay:.1f}ms")
    print("完整配置: output/clash.yaml")
    print("="*50)

if __name__ == "__main__":
    main()
