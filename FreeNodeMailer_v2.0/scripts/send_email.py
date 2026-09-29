
import os, sys, logging, smtplib, ssl
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
import yaml

# ─── Logging setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("send_email")

# ─── Config ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("output")
CLASH_YAML = OUTPUT_DIR / "clash.yaml"
REPORT_HTML = OUTPUT_DIR / "report.html"

# SMTP config: primary (QQ) and backup (163)
SMTP_CONFIGS = [
    # QQ SMTP (SSL on 465)
    {
        "host": "smtp.qq.com",
        "port": 465,
        "use_ssl": True,
        "env_user": "QQ_EMAIL",
        "env_pwd": "QQ_AUTH",
        "name": "QQ",
    },
    # 163 SMTP (SSL on 465, TLS on 25/587)
    {
        "host": "smtp.163.com",
        "port": 465,
        "use_ssl": True,
        "env_user": "163_EMAIL",
        "env_pwd": "163_AUTH",
        "name": "163",
    },
    {
        "host": "smtp.163.com",
        "port": 25,
        "use_ssl": False,
        "env_user": "163_EMAIL",
        "env_pwd": "163_AUTH",
        "name": "163-tls",
    },
]

CONN_TIMEOUT = 30   # socket connect timeout (seconds)
SMTP_TIMEOUT = 60   # smtplib timeout (seconds)


def load_credentials():
    """Load sender credentials from environment. Returns (email, auth_code)."""
    # Try QQ first
    qq_email = os.getenv("QQ_EMAIL")
    qq_auth = os.getenv("QQ_AUTH")
    if qq_email and qq_auth:
        return qq_email, qq_auth, "QQ"

    # Fallback to 163
    _163_email = os.getenv("163_EMAIL")
    _163_auth = os.getenv("163_AUTH")
    if _163_email and _163_auth:
        return _163_email, _163_auth, "163"

    raise RuntimeError(
        "No email credentials found. Set QQ_EMAIL + QQ_AUTH or 163_EMAIL + 163_AUTH."
    )


def build_html_report(proxy_count: int, sources: list, errors: list) -> str:
    """Build an HTML report with statistical summary."""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    error_rows = "".join(
        f'<tr><td style="color:red;">{err}</td></tr>' for err in errors[:10]
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
  h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
  .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
  .stat-card {{ background: #f8f9fa; border-radius: 8px; padding: 15px 25px;
                text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  .stat-num {{ font-size: 32px; font-weight: bold; color: #3498db; }}
  .stat-label {{ font-size: 14px; color: #666; margin-top: 5px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
  th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
  th {{ background: #3498db; color: white; }}
  tr:hover {{ background: #f5f5f5; }}
  .error-list {{ background: #fff3f3; border-left: 4px solid #e74c3c;
                 padding: 10px; margin-top: 10px; }}
  .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee;
             font-size: 12px; color: #999; text-align: center; }}
</style>
</head>
<body>
  <h1>&#x1F4E5; FreeNodeMailer Daily Report</h1>
  <p><strong>生成时间:</strong> {today}</p>

  <div class="stats">
    <div class="stat-card">
      <div class="stat-num">{proxy_count}</div>
      <div class="stat-label">可用节点</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{len(sources)}</div>
      <div class="stat-label">数据来源</div>
    </div>
    <div class="stat-card">
      <div class="stat-num" style="color:{'#e74c3c' if errors else '#27ae60'}">{len(errors)}</div>
      <div class="stat-label">抓取失败</div>
    </div>
  </div>

  <h2>&#x1F4CB; 数据源状态</h2>
  <table>
    <tr><th>来源</th><th>状态</th></tr>
    {''.join(f'<tr><td>{s}</td><td style="color:green;">&#10003; OK</td></tr>' for s in sources)}
    {''.join(f'<tr><td>{e.split(" | ")[0]}</td><td style="color:red;">&#10007; 失败</td></tr>' for e in errors)}
  </table>

  {'<div class="error-list"><strong>错误详情:</strong><ul>' +
   ''.join(f'<li>{e}</li>' for e in errors[:5]) + '</ul></div>' if errors else ''}

  <div class="footer">
    <p>FreeNodeMailer &mdash; 自动每日节点推送服务</p>
  </div>
</body>
</html>"""
    return html


def send_with_smtp(cfg, sender, password, msg):
    """Send email using given SMTP config. Returns True on success."""
    host, port, use_ssl = cfg["host"], cfg["port"], cfg["use_ssl"]
    log.info(f"Connecting to {host}:{port} ...")

    if use_ssl:
        ctx = ssl.create_default_context()
        server = smtplib.SMTP_SSL(host, port, timeout=CONN_TIMEOUT, context=ctx)
    else:
        server = smtplib.SMTP(host, port, timeout=CONN_TIMEOUT)
        server.starttls()

    server.set_debuglevel(0)
    server.login(sender, password)
    server.send_message(msg)
    server.quit()
    log.info(f"Email sent successfully via {cfg['name']} ({host}:{port})")
    return True


def main():
    # 1. Validate output files
    if not CLASH_YAML.exists():
        log.error(f"Output file not found: {CLASH_YAML}")
        sys.exit(1)
    if not REPORT_HTML.exists():
        log.error(f"Report file not found: {REPORT_HTML}")
        sys.exit(1)

    # 2. Load credentials
    try:
        sender, password, cred_source = load_credentials()
        log.info(f"Using credentials from {cred_source}")
    except RuntimeError as e:
        log.error(str(e))
        sys.exit(1)

    # 3. Read output
    proxy_count = 0
    try:
        data = yaml.safe_load(CLASH_YAML.read_text(encoding="utf8"))
        proxies = data.get("proxies", []) if isinstance(data, dict) else []
        proxy_count = len(proxies)
        log.info(f"Loaded {proxy_count} proxies from {CLASH_YAML}")
    except Exception as e:
        log.warning(f"Failed to parse clash.yaml: {e}")
        proxy_count = 0

    report_html = REPORT_HTML.read_text(encoding="utf8")

    # 4. Build message
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"FreeNodeMailer Daily — {datetime.now().strftime('%Y-%m-%d')} — {proxy_count} nodes"
    msg["From"] = sender
    msg["To"] = sender

    # HTML body with stats
    sources = [line.strip() for line in Path("config/sources.txt").read_text(encoding="utf8").splitlines() if line.strip()]
    # Parse errors from log or use empty list (errors would be in fetch log)
    errors = []

    html_body = build_html_report(proxy_count, sources, errors)
    msg.attach(MIMEText(html_body, "html", "utf8"))

    # Attachment
    try:
        att = MIMEApplication(
            CLASH_YAML.read_bytes(),
            Name="clash.yaml"
        )
        att["Content-Disposition"] = 'attachment; filename="clash.yaml"'
        msg.attach(att)
        log.info(f"Attached clash.yaml ({CLASH_YAML.stat().st_size} bytes)")
    except Exception as e:
        log.warning(f"Failed to attach file: {e}")

    # 5. Send with fallback
    last_err = None
    for cfg in SMTP_CONFIGS:
        # Check if this config has valid credentials
        user_env = os.getenv(cfg["env_user"])
        pwd_env = os.getenv(cfg["env_pwd"])
        if not user_env or not pwd_env:
            log.debug(f"Skipping {cfg['name']}: credentials not set")
            continue

        try:
            if send_with_smtp(cfg, user_env, pwd_env, msg):
                log.info("Email delivery successful!")
                return
        except Exception as e:
            last_err = f"{cfg['name']}: {e}"
            log.warning(f"Failed to send via {cfg['name']} ({cfg['host']}:{cfg['port']}): {e}")

    # All SMTP attempts failed
    log.error(f"All SMTP attempts failed. Last error: {last_err}")
    sys.exit(1)


if __name__ == "__main__":
    main()
