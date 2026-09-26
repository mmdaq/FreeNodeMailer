
import os,smtplib
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
user=os.getenv("QQ_EMAIL"); pwd=os.getenv("QQ_AUTH")
msg=MIMEMultipart()
msg["Subject"]="FreeNodeMailer Daily"
msg["From"]=user; msg["To"]=user
msg.attach(MIMEText(Path("output/report.html").read_text(),"html","utf8"))
att=MIMEApplication(Path("output/clash.yaml").read_bytes(),Name="clash.yaml")
att["Content-Disposition"]="attachment; filename=clash.yaml"
msg.attach(att)
s=smtplib.SMTP_SSL("smtp.qq.com",465); s.login(user,pwd); s.send_message(msg); s.quit()
