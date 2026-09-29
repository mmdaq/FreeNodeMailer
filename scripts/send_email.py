import os,smtplib
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
user=os.getenv("QQ_EMAIL"); pwd=os.getenv("QQ_AUTH")
msg=MIMEMultipart()
msg["Subject"]=f"FreeNodeMailer Daily - {datetime.now().strftime('%Y-%m-%d')}"
msg["From"]=user; msg["To"]=user

# 读取报告
report_html = Path("output/report.html").read_text(encoding="utf8")
msg.attach(MIMEText(report_html,"html","utf8"))

# 添加附件
att=MIMEApplication(Path("output/clash.yaml").read_bytes(),Name="clash.yaml")
att["Content-Disposition"]="attachment; filename=clash.yaml"
msg.attach(att)

# 发送邮件
s=smtplib.SMTP_SSL("smtp.qq.com",465)
s.login(user,pwd)
s.send_message(msg)
s.quit()
print("Email sent successfully!")
