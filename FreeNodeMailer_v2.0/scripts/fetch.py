
import requests,yaml
from pathlib import Path
proxies=[]
for url in Path("config/sources.txt").read_text().splitlines():
    if not url: continue
    try:
        data=yaml.safe_load(requests.get(url,timeout=20).text)
        proxies.extend(data.get("proxies",[]))
    except Exception: pass
seen=set(); out=[]
for p in proxies:
    k=(p.get("server"),p.get("port"),p.get("uuid",""))
    if k in seen: continue
    seen.add(k); out.append(p)
Path("output").mkdir(exist_ok=True)
yaml.safe_dump({"proxies":out}, open("output/clash.yaml","w",encoding="utf8"), allow_unicode=True)
Path("output/report.html").write_text(f"<h2>今日节点</h2><p>{len(out)} 个</p>", encoding="utf8")
print("saved", len(out))
