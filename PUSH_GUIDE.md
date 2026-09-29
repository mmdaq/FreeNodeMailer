# FreeNodeMailer GitHub 推送指南

## 问题分析

当前项目结构：
```
D:\DSH_work\FreeNodeMailer\FreeNodeMailer_v2.0\   # 你的项目目录
├── .github\
│   └── workflows\
│       └── daily.yml                              # GitHub Actions 工作流（需要移动到根目录）
├── scripts\
│   ├── fetch.py
│   └── send_email.py
├── config\
└── output\
```

**问题**：
1. GitHub Actions 要求工作流文件在仓库根目录的 `.github/workflows/`
2. 当前工作流在 `FreeNodeMailer_v2.0/.github/workflows/` 子目录中
3. GitHub 不会自动发现这个路径的工作流

## 解决方案

### 步骤 1：创建正确的 workflow 文件

我已经创建了一个修正后的 workflow 文件，请复制以下内容：

**创建文件**：`D:\DSH_work\FreeNodeMailer\FreeNodeMailer_v2.0\.github\workflows\daily.yml`

但需要将内容更新为根目录版本。让我创建一个正确的版本：

---

### 步骤 2：手动执行以下命令

打开 PowerShell，执行：

```powershell
# 1. 进入项目目录
cd D:\DSH_work\FreeNodeMailer\FreeNodeMailer_v2.0

# 2. 初始化 git（如果还没有）
git init

# 3. 添加远程仓库
git remote add origin https://github.com/mmdaq/FreeNodeMailer.git

# 4. 添加所有文件
git add .

# 5. 提交更改
git commit -m "fix: 修复 workflow 配置文件到根目录"

# 6. 推送到 GitHub
git push -u origin main
```

---

### 步骤 3：验证 GitHub Actions

推送成功后：
1. 访问 https://github.com/mmdaq/FreeNodeMailer/actions
2. 你应该能看到 FreeNodeMailer workflow
3. 点击 "Run workflow" 测试一次

---

## 重要说明

### GitHub Secrets 需要配置

在 GitHub 仓库页面：
1. 进入 **Settings** → **Secrets and variables** → **Actions**
2. 添加以下 Secrets：
   - `QQ_EMAIL` = `385096659@qq.com`
   - `QQ_AUTH` = 你的 QQ 邮箱 SMTP 授权码（16位）

### 获取 QQ 邮箱授权码

1. 登录 QQ 邮箱
2. 设置 → 账户
3. 找到「POP3/IMAP/SMTP 服务」
4. 开启服务并生成授权码
5. 复制 16 位授权码

---

## 推送后工作流位置

修正后的工作流将位于：
```
.github/workflows/daily.yml
```

而不是：
```
FreeNodeMailer_v2.0/.github/workflows/daily.yml  ❌ 错误位置
```

GitHub Actions 只会在根目录的 `.github/workflows/` 查找工作流文件。
