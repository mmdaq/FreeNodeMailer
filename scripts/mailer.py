"""邮件发送（QQ 邮箱 SMTP）。"""
from __future__ import annotations

import mimetypes
import smtplib
import ssl
import time
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from email import encoders
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from util import LOG, env, now_cn


class MailError(RuntimeError):
    pass


def load_mail_credentials(settings: Dict[str, Any]) -> Dict[str, Any]:
    cfg = settings.get("mail", {})
    sender = env("QQ_EMAIL") or env("SMTP_USER")
    auth = env("QQ_AUTH") or env("SMTP_PASS") or env("SMTP_PASSWORD")
    to_raw = env("MAIL_TO") or str(cfg.get("to", "") or "")
    recipients = [a.strip() for a in to_raw.replace(";", ",").split(",") if a.strip()]
    if not recipients and sender:
        recipients = [sender]
    return {
        "host": env("SMTP_HOST") or str(cfg.get("smtp_host", "smtp.qq.com")),
        "port": int(env("SMTP_PORT") or cfg.get("smtp_port", 465) or 465),
        "use_ssl": str(env("SMTP_SSL") or cfg.get("use_ssl", True)).lower() not in {"0", "false", "no"},
        "sender": sender,
        "auth": auth,
        "to": recipients,
        "subject_prefix": str(cfg.get("subject_prefix", "【FreeNodeMailer】")),
    }


def check_credentials(settings: Dict[str, Any]) -> None:
    c = load_mail_credentials(settings)
    problems = []
    if not c["sender"]:
        problems.append("缺少发件邮箱：请在 .env 设置 QQ_EMAIL")
    if not c["auth"]:
        problems.append("缺少 SMTP 授权码：请在 .env 设置 QQ_AUTH（QQ邮箱设置→账号→开启SMTP→生成授权码，16位）")
    if not c["to"]:
        problems.append("缺少收件人：请在 .env 设置 MAIL_TO 或 config/settings.yaml 的 mail.to")
    if problems:
        raise MailError("\n".join(problems))


def _attach_file(msg: MIMEMultipart, path: Path, filename: Optional[str] = None) -> None:
    ctype, encoding = mimetypes.guess_type(str(path))
    if ctype is None or encoding is not None:
        ctype = "application/octet-stream"
    maintype, subtype = ctype.split("/", 1)
    part = MIMEBase(maintype, subtype)
    part.set_payload(path.read_bytes())
    encoders.encode_base64(part)
    name = filename or path.name
    part.add_header("Content-Disposition", "attachment",
                    filename=("utf-8", "", name))
    msg.attach(part)


def send_mail(settings: Dict[str, Any], subject: str, html_body: str, text_body: str = "",
              attachments: Sequence[Path] = (), retries: int = 2) -> Dict[str, Any]:
    c = load_mail_credentials(settings)
    check_credentials(settings)

    msg = MIMEMultipart("mixed")
    # QQ SMTP 对 From/To 头的 RFC 格式校验很严格，必须用
    # email.utils.formataddr 生成 "显示名 <addr>" 形式（非 ASCII 名自动编码）
    msg["From"] = formataddr(("FreeNodeMailer", c["sender"]))
    msg["To"] = ", ".join(formataddr(("", a)) for a in c["to"])
    msg["Subject"] = Header(f"{c['subject_prefix']}{subject}", "utf-8")
    msg["Date"] = formatdate(localtime=True)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body or "请使用支持 HTML 的邮件客户端查看本报告。", "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    for p in attachments:
        p = Path(p)
        if p.exists():
            _attach_file(msg, p)
            LOG.info("已附加：%s (%.1f KB)", p.name, p.stat().st_size / 1024)
        else:
            LOG.warning("附件不存在，跳过：%s", p)

    raw = msg.as_string()
    attempts = 0
    last_err = ""
    for attempt in range(1, max(1, retries) + 1):
        attempts = attempt
        try:
            if c["use_ssl"]:
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(c["host"], c["port"], timeout=45, context=ctx) as s:
                    s.login(c["sender"], c["auth"])
                    s.sendmail(c["sender"], c["to"], raw)
            else:
                with smtplib.SMTP(c["host"], c["port"], timeout=45) as s:
                    s.ehlo()
                    s.starttls(context=ssl.create_default_context())
                    s.login(c["sender"], c["auth"])
                    s.sendmail(c["sender"], c["to"], raw)
            LOG.info("邮件已发送 → %s（%d 字节，%d 个附件）",
                     ", ".join(c["to"]), len(raw), len(list(attachments)))
            return {"ok": True, "attempts": attempts, "to": c["to"],
                    "subject": subject, "bytes": len(raw)}
        except smtplib.SMTPAuthenticationError as exc:
            last_err = (f"SMTP 认证失败（授权码错误？）：{exc.smtp_code} {exc.smtp_error!r}\n"
                        "请确认 QQ_AUTH 填的是「授权码」而不是 QQ 密码，且已开启 SMTP 服务。")
            break  # 认证错误重试无意义
        except (smtplib.SMTPException, OSError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                LOG.warning("邮件发送失败（第 %d 次）：%s，%.0fs 后重试", attempt, last_err, 3 * attempt)
                time.sleep(3 * attempt)
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            break

    LOG.error("邮件发送失败：%s", last_err)
    return {"ok": False, "attempts": attempts, "error": last_err, "to": c["to"]}


def send_test_mail(settings: Dict[str, Any]) -> Dict[str, Any]:
    html = f"""<div style="font-family:'Microsoft YaHei',sans-serif;padding:16px">
      <h2 style="color:#2b6cb0">✅ FreeNodeMailer 邮件通道测试成功</h2>
      <p>发送时间（北京时间）：<b>{now_cn()}</b></p>
      <p>如果你收到这封邮件，说明 QQ SMTP 授权码配置正确，
      每日 08:00 的节点推送可以正常送达。</p>
    </div>"""
    return send_mail(settings, "邮件通道测试", html, "FreeNodeMailer 邮件通道测试成功")
