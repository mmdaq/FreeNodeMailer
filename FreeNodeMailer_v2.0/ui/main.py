
from PySide6.QtWidgets import *
import subprocess, sys
app=QApplication(sys.argv)
w=QWidget(); w.setWindowTitle("FreeNodeMailer v2.0")
lay=QVBoxLayout(w)
lay.addWidget(QLabel("Free Clash Node Mailer"))
mail=QLineEdit(); mail.setPlaceholderText("QQ邮箱")
lay.addWidget(mail)
btn=QPushButton("立即抓取")
log=QTextEdit()
lay.addWidget(btn); lay.addWidget(log)
def run():
    p=subprocess.run([sys.executable,"scripts/fetch.py"],capture_output=True,text=True)
    log.append(p.stdout+p.stderr)
btn.clicked.connect(run)
w.resize(520,420); w.show()
app.exec()
