# FreeNodeMailer - GitHub 推送操作指南

## ✅ 已完成的工作

1. **修复了 GitHub Actions 工作流**
   - 原问题：工作流文件在子目录 `FreeNodeMailer_v2.0/.github/workflows/`，GitHub Actions 无法发现
   - 解决方案：创建根目录版本 `.github/workflows/daily.yml`

2. **修正了路径配置**
   - 所有 Python 脚本路径更新为 `FreeNodeMailer_v2.0/scripts/`
   - 订阅 URL 使用正确的分支 `main`

3. **创建了配置文件**
   - `.env` 已包含你的 QQ 邮箱：`385096659@qq.com`
   - `SETUP.md` 包含详细配置说明

---

## 🚀 你需要执行的操作

### 步骤 1：打开 PowerShell，执行以下命令

```powershell
# 进入项目目录
cd D:\DSH_work\FreeNodeMailer\FreeNodeMailer_v2.0

# 初始化 git 仓库（如果还没有）
git init

# 添加远程仓库
git remote add origin https://github.com/mmdaq/FreeNodeMailer.git

# 添加所有更改
git add .

# 提交更改
git commit -m "fix: 修复 workflow 配置并添加环境变量"

# 推送到 GitHub
git push -u origin main
```

### 步骤 2：配置 GitHub Secrets（如果还没有）

1. 访问 https://github.com/mmdaq/FreeNodeMailer/settings/secrets/actions
2. 点击 "New repository secret"
3. 添加以下两个 Secrets：

| Secret Name | Value |
|-------------|-------|
| `QQ_EMAIL` | `385096659@qq.com` |
| `QQ_AUTH` | 你的 QQ 邮箱 SMTP 授权码（16位） |

### 步骤 3：测试工作流

1. 访问 https://github.com/mmdaq/FreeNodeMailer/actions
2. 点击 "FreeNodeMailer" 工作流
3. 点击 "Run workflow" → "Run workflow"
4. 等待 2-5 分钟，检查是否收到邮件

---

## 📧 如何获取 QQ 邮箱授权码

1. 登录 QQ 邮箱：https://mail.qq.com
2. 点击 **设置** → **账户**
3. 找到「POP3/IMAP/SMTP 服务」
4. 点击「开启」
5. 按提示发送短信验证
6. 系统会显示 16 位授权码，**复制并保存**

---

## 📅 自动推送计划

| 时间 | 事件 |
|------|------|
| 每天 00:00 UTC | GitHub Actions 触发 |
| 每天 08:00 北京时间 | 抓取节点 + 发送邮件到 385096659@qq.com |

---

## 🔗 订阅地址

推送成功后，你可以使用以下地址订阅 Clash 配置：

```
https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/FreeNodeMailer_v2.0/output/clash.yaml
```
