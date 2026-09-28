
import requests
import yaml
import logging
import time
from pathlib import Path

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
            logger.info(f"  Got {len(proxies)} proxies from {url}")
            return proxies
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

def main():
    sources_file = Path("config/sources.txt")
    if not sources_file.exists():
        logger.error(f"Sources file not found: {sources_file}")
        return

    all_proxies = []
    for url in sources_file.read_text(encoding="utf8").splitlines():
        url = url.strip()
        if not url or url.startswith("#"):
            continue
        proxies = fetch_from_url(url)
        all_proxies.extend(proxies)

    # 去重
    unique_proxies = deduplicate(all_proxies)
    logger.info(f"Total unique proxies: {len(unique_proxies)}")

    # 保存输出
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # 保存 clash.yaml
    yaml_path = output_dir / "clash.yaml"
    with open(yaml_path, "w", encoding="utf8") as f:
        yaml.safe_dump({"proxies": unique_proxies}, f, allow_unicode=True)
    logger.info(f"Saved clash.yaml to {yaml_path}")

    # 保存 HTML 报告
    report_path = output_dir / "report.html"
    report_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>FreeNodeMailer Daily Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h2 {{ color: #333; }}
        .stat {{ margin: 10px 0; padding: 10px; background: #f5f5f5; border-radius: 4px; }}
        .count {{ font-size: 24px; color: #2196F3; font-weight: bold; }}
    </style>
</head>
<body>
    <h2>FreeNodeMailer Daily Report</h2>
    <div class="stat">
        <p>总节点数: <span class="count">{len(unique_proxies)}</span></p>
    </div>
    <p>生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p>请查看附件中的 clash.yaml 文件导入 Clash/ClashX/V2rayNG。</p>
</body>
</html>"""
    report_path.write_text(report_html, encoding="utf8")
    logger.info(f"Saved report to {report_path}")
    print(f"OK: {len(unique_proxies)} proxies saved")

if __name__ == "__main__":
    main()
