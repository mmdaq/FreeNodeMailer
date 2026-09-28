# FreeNodeMailer v2.0

Windows + GitHub Actions 免费 Clash 节点采集工具。

## 功能
- 多 GitHub 节点源采集（8+ 源）
- 自动去重
- 生成**完整可用的 Clash 配置**（含代理组、规则、DNS）
- 支持 **Clash Meta 订阅**（自动更新）
- GitHub Actions 每天 08:00 (北京时间) 自动推送

---

## 使用方式

### 方式一：直接导入（推荐）

1. Fork 本仓库（或直接使用原仓库）
2. 仓库名已配置为 `mmdaq/FreeNodeMailer`
3. 在 Actions 中手动运行一次 workflow，生成初始配置
4. 下载 `output/clash.yaml` 直接导入 Clash/ClashX

### 方式二：订阅管理（Clash Meta / Clash Verge）

在 Clash Meta 客户端中添加订阅：

```
https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/output/clash.yaml
```

客户端会自动识别订阅，每天 08:00 自动更新节点。

---

## 输出文件说明

| 文件 | 说明 |
|------|------|
| `output/clash.yaml` | 完整可用配置（直接导入 Clash） |
| `output/providers.yaml` | Provider 格式（Clash Meta 订阅用） |
| `output/report.html` | 每日报告（HTML 格式） |

---

## 本地运行

```bash
pip install -r requirements.txt
python scripts/fetch.py
```

---

## 自定义节点源

编辑 `config/sources.txt`，每行一个 YAML 格式的节点源 URL。

---

## 文件说明
- `scripts/fetch.py` - 节点抓取 + 配置生成
- `scripts/send_email.py` - 邮件发送脚本（可选）
- `.github/workflows/daily.yml` - GitHub Actions 工作流
- `config/sources.txt` - 节点源列表
- `config/github_repo.txt` - GitHub 仓库名配置
- `ui/main.py` - 桌面 GUI 界面
