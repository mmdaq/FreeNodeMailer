import requests,yaml,logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SPEED_TEST_URL = "http://www.gstatic.com/generate_204"
SPEED_TEST_TIMEOUT = 5
MAX_CONCURRENT = 50
MAX_DELAY = 500  # 毫秒，超过此延迟的节点将被过滤

# 获取日期
today = datetime.now().strftime('%Y%m%d')
date_str = datetime.now().strftime('%Y年%m月%d日')

proxies=[]
failed_sources = []
successful_sources = []
for url in Path("config/sources.txt").read_text().splitlines():
    if not url: continue
    try:
        data=yaml.safe_load(requests.get(url,headers=HEADERS,timeout=20).text)
        proxies.extend(data.get("proxies",[]))
        successful_sources.append(url)
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        failed_sources.append(url)

# 去重
seen=set(); out=[]
for p in proxies:
    k=(p.get("server"),p.get("port"),p.get("uuid",""))
    if k in seen: continue
    seen.add(k); out.append(p)

# 测速
def test_speed(proxy):
    server = proxy.get("server","")
    port = proxy.get("port",443)
    try:
        session = requests.Session()
        proxies_for_req = {"http": f"http://{server}:{port}", "https": f"https://{server}:{port}"}
        start = time.time()
        resp = session.get(SPEED_TEST_URL, timeout=SPEED_TEST_TIMEOUT, proxies=proxies_for_req, verify=False)
        delay = (time.time() - start) * 1000
        session.close()
        proxy["delay"] = round(delay, 1)
        return proxy
    except:
        proxy["delay"] = -1
        return proxy

logger.info(f"Testing {len(out)} proxies...")
timed_proxies = []
with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
    results = list(executor.map(test_speed, out))
    timed_proxies = [p for p in results if p.get("delay", -1) > 0]

# 过滤延迟超过阈值的节点
filtered_proxies = [p for p in timed_proxies if p.get("delay", 0) <= MAX_DELAY]
if len(timed_proxies) != len(filtered_proxies):
    logger.info(f"Filtered {len(timed_proxies) - len(filtered_proxies)} proxies with delay > {MAX_DELAY}ms")
timed_proxies = filtered_proxies

# 统计
timed_proxies.sort(key=lambda x: x.get("delay", 9999))
available = len(timed_proxies)
avg_delay = sum(p.get("delay",0) for p in timed_proxies) / available if available > 0 else 0
min_delay = min((p.get("delay",9999) for p in timed_proxies), default=0)

# 按地区分组
def get_region(name):
    if not name: return "其他"
    if "🇯🇵" in name or "日本" in name: return "🇯🇵 日本"
    if "🇺🇸" in name or "美国" in name: return "🇺🇸 美国"
    if "🇭🇰" in name or "香港" in name: return "🇭🇰 香港"
    if "🇸🇬" in name or "新加坡" in name: return "🇸🇬 新加坡"
    if "🇬🇧" in name or "英国" in name: return "🇬🇧 英国"
    if "🇩🇪" in name or "德国" in name: return "🇩🇪 德国"
    if "🇫🇷" in name or "法国" in name: return "🇫🇷 法国"
    if "🇰🇷" in name or "韩国" in name: return "🇰🇷 韩国"
    if "🇹🇼" in name or "台湾" in name: return "🇹🇼 台湾"
    if "🇹🇭" in name or "泰国" in name: return "🇹🇭 泰国"
    if "🇨🇦" in name or "加拿大" in name: return "🇨🇦 加拿大"
    if "🇦🇺" in name or "澳大利亚" in name: return "🇦🇺 澳大利亚"
    if "🇳🇱" in name or "荷兰" in name: return "🇳🇱 荷兰"
    if "🇮🇳" in name or "印度" in name: return "🇮🇳 印度"
    if "🇧🇷" in name or "巴西" in name: return "🇧🇷 巴西"
    if "🇷🇺" in name or "俄罗斯" in name: return "🇷🇺 俄罗斯"
    return "🌍 其他"

regions = {}
for p in timed_proxies:
    r = get_region(p.get("name",""))
    regions.setdefault(r, []).append(p)

# 生成可直接导入 Clash/Clash Verge 的配置
yaml_data = {
    "mixed-port": 7890,
    "allow-lan": True,
    "mode": "rule",
    "log-level": "info",
    "proxies": timed_proxies,
    "proxy-groups": [
        {
            "name": "🚀 节点选择",
            "type": "select",
            "proxies": ["♻️ 自动选择", "🇯🇵 日本", "🇺🇸 美国", "🇭🇰 香港", "🇸🇬 新加坡", "🇬🇧 英国", "🇩🇪 德国", "🇫🇷 法国", "🇰🇷 韩国", "🇹🇼 台湾", "🇹🇭 泰国", "🇨🇦 加拿大", "🇦🇺 澳大利亚", "🇳🇱 荷兰", "🇮🇳 印度", "🇧🇷 巴西", "🇷🇺 俄罗斯", "🌍 其他"]
        },
        {
            "name": "♻️ 自动选择",
            "type": "url-test",
            "url": SPEED_TEST_URL,
            "interval": 300,
            "tolerance": 50,
            "proxies": ["🇯🇵 日本", "🇺🇸 美国", "🇭🇰 香港", "🇸🇬 新加坡", "🇬🇧 英国", "🇩🇪 德国", "🇫🇷 法国", "🇰🇷 韩国", "🇹🇼 台湾", "🇹🇭 泰国", "🇨🇦 加拿大", "🇦🇺 澳大利亚", "🇳🇱 荷兰", "🇮🇳 印度", "🇧🇷 巴西", "🇷🇺 俄罗斯", "🌍 其他"]
        },
        {"name": "🌐 全球代理", "type": "select", "proxies": ["🚀 节点选择", "DIRECT"]},
        {"name": "🐟 漏网之鱼", "type": "select", "proxies": ["🚀 节点选择", "🌐 全球代理", "DIRECT"]},
    ] + [{"name": r, "type": "select", "proxies": [p.get("name","") for p in ps]} for r, ps in regions.items()],
    "rules": [
        "GEODATA,cn,DIRECT",
        "MATCH,🐟 漏网之鱼"
    ]
}

Path("output").mkdir(exist_ok=True)

# 生成带日期的文件名
clash_file = f"output/{today}clash.yaml"
yaml.safe_dump(yaml_data, open(clash_file,"w",encoding="utf8"), allow_unicode=True)

# 同时生成一个无日期的副本用于订阅
yaml.safe_dump(yaml_data, open("output/clash.yaml","w",encoding="utf8"), allow_unicode=True)

# 验证输出（如果有的话）
if available > 0:
    assert all(p.get("delay", 9999) <= MAX_DELAY for p in timed_proxies), "存在延迟超标的节点!"

# 生成 HTML 报告
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>FreeNodeMailer 每日报告</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #f5f5f5; }}
  .container {{ background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 15px; }}
  .stats {{ display: flex; gap: 15px; margin: 25px 0; flex-wrap: wrap; }}
  .stat {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 10px; padding: 20px; text-align: center; flex: 1; min-width: 100px; }}
  .stat-num {{ font-size: 28px; font-weight: bold; }}
  .stat-label {{ font-size: 13px; opacity: 0.9; margin-top: 5px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 14px; }}
  th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
  th {{ background: #3498db; color: white; }}
  tr:hover {{ background: #f5f5f5; }}
  .region {{ background: #e8f4fd; font-weight: bold; }}
  .delay-good {{ color: #27ae60; font-weight: bold; }}
  .delay-ok {{ color: #f39c12; }}
  .delay-bad {{ color: #e74c3c; }}
  .success {{ color: #27ae60; font-weight: bold; }}
  .error {{ color: #e74c3c; }}
  .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; font-size: 12px; color: #999; text-align: center; }}
  .code {{ background: #f4f4f4; padding: 15px; border-radius: 6px; font-family: monospace; overflow-x: auto; font-size: 13px; }}
  .subscribe {{ background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 20px 0; }}
</style>
</head>
<body>
<div class="container">
  <h1>📬 FreeNodeMailer 每日报告</h1>
  <p><strong>生成时间:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
  
  <div class="stats">
    <div class="stat">
      <div class="stat-num">{available}</div>
      <div class="stat-label">可用节点</div>
    </div>
    <div class="stat">
      <div class="stat-num">{avg_delay:.1f}ms</div>
      <div class="stat-label">平均延迟</div>
    </div>
    <div class="stat">
      <div class="stat-num">{min_delay:.1f}ms</div>
      <div class="stat-label">最快延迟</div>
    </div>
    <div class="stat">
      <div class="stat-num">{len(regions)}</div>
      <div class="stat-label">覆盖地区</div>
    </div>
  </div>
  
  <div class="subscribe">
    <strong>📥 订阅方式:</strong><br>
    直接点击链接导入 Clash / Clash Verge:<br>
    <code style="font-size:12px;word-break:break-all;">https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/output/{today}clash.yaml</code>
  </div>
  
  <h2>📋 节点列表</h2>
  <table>
    <tr><th>节点名称</th><th>类型</th><th>延迟</th><th>地址</th></tr>
"""

for region, nodes in sorted(regions.items()):
    html += f'    <tr class="region"><td colspan="4">{region} ({len(nodes)})</td></tr>\n'
    for p in nodes[:10]:
        name = p.get("name", "")
        ptype = p.get("type", "").upper()
        delay = p.get("delay", 0)
        server = p.get("server", "")
        port = p.get("port", "")
        delay_class = "delay-good" if delay < 200 else ("delay-ok" if delay < 500 else "delay-bad")
        html += f'    <tr><td>{name}</td><td>{ptype}</td><td class="{delay_class}">{delay:.0f} ms</td><td>{server}:{port}</td></tr>\n'

html += f"""  </table>

  <h2>📡 数据源状态</h2>
  <table>
    <tr><th>来源</th><th>状态</th></tr>
"""
for url in successful_sources:
    short_url = url[:40] + "..." if len(url) > 40 else url
    html += f'    <tr><td>{short_url}</td><td class="success">✓ OK</td></tr>\n'
for url in failed_sources:
    short_url = url[:40] + "..." if len(url) > 40 else url
    html += f'    <tr><td>{short_url}</td><td class="error">✗ 失败</td></tr>\n'

html += f"""  </table>
  
  <div class="footer">
    <p>FreeNodeMailer &mdash; 自动每日节点推送服务 | {date_str}</p>
    <p>所有节点延迟 &le; {MAX_DELAY}ms | 可直接导入 Clash/Clash Verge</p>
  </div>
</div>
</body>
</html>"""

Path("output/report.html").write_text(html, encoding="utf8")

print(f"Saved {available} proxies (delay <= {MAX_DELAY}ms)")
print(f"Avg delay: {avg_delay:.1f}ms, Min delay: {min_delay:.1f}ms")
print(f"Regions: {len(regions)}")
print(f"Output: {clash_file}")
if available == 0:
    logger.warning("Warning: No proxies available!")
else:
    print(f"✅ All {available} proxies verified: delay <= {MAX_DELAY}ms")
