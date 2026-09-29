# FreeNodeMailer 配置指南

## ✅ 已完成配置

### 1. GitHub Actions 工作流修复
- 已添加 `working-directory: FreeNodeMailer_v2.0` 到所有需要运行 Python 脚本的步骤
- 默认定时：每天 00:00 UTC = **北京时间 08:00**

### 2. 本地环境变量文件
- `.env` 已创建在 `FreeNodeMailer/FreeNodeMailer_v2.0/.env`
- QQ 邮箱已设置为 `385096659@qq.com`
- **需要填写：QQ 邮箱 SMTP 授权码**

### 3. GitHub Secrets（你已配置）
确认已设置：
- `QQ_EMAIL` = 385096659@qq.com
- `QQ_AUTH` = 你的16位授权码

---

## 🔧 还需要完成的操作

### 步骤 1：获取 QQ 邮箱授权码
1. 打开 QQ 邮箱 → 设置 → 账户
2. 找到「POP3/IMAP/SMTP 服务」
3. 开启 SMTP 服务并生成授权码
4. 复制 16 位授权码

### 步骤 2：更新本地 .env 文件
编辑文件 `D:\DSH_work\FreeNodeMailer\FreeNodeMailer_v2.0\.env`：
```
QQ_AUTH=你的16位授权码
```

### 步骤 3：提交更改到 GitHub
```bash
cd D:\DSH_work\FreeNodeMailer\FreeNodeMailer_v2.0
git add .
git commit -m "fix: 修复 workflow working-directory 配置"
git push
```

### 步骤 4：手动触发测试（可选）
在 GitHub 仓库页面：
1. 进入 **Actions** 标签
2. 选择 **FreeNodeMailer** 工作流
3. 点击 **Run workflow** → **Run workflow**

---

## 📧 本地运行命令（如需测试）

```bash
cd D:\DSH_work\FreeNodeMailer\FreeNodeMailer_v2.0

# 安装依赖
pip install -r requirements.txt

# 测试抓取节点
python scripts/fetch.py

# 测试发送邮件（需要设置 QQ_AUTH 环境变量）
QQ_AUTH=你的授权码 python scripts/send_email.py
```

---

## 📋 输出文件说明

| 文件 | 说明 |
|------|------|
| `output/clash.yaml` | 完整 Clash 配置，可直接导入客户端 |
| `output/report.html` | 每日 HTML 报告 |
| `output/providers.yaml` | Provider 格式（Clash Meta 订阅用） |

订阅地址：`https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/output/clash.yaml`
