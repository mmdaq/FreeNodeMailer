# FreeNodeMailer v2.0

Windows + GitHub Actions 免费 Clash 节点采集工具。

## 功能
- 多 GitHub 节点源采集（8+ 源）
- 自动去重
- 生成 clash.yaml
- **GitHub Actions 每天 08:00 (北京时间) 自动更新仓库**
- PySide6 GUI（可继续扩展）

## 使用方式

节点配置会自动推送到本仓库的 `output/clash.yaml`，直接复制使用即可：

```
https://raw.githubusercontent.com/YOUR_USERNAME/FreeNodeMailer/main/output/clash.yaml
```

## 本地运行
```bash
pip install -r requirements.txt
python ui/main.py
```

## 文件说明
- `scripts/fetch.py` - 节点抓取脚本
- `.github/workflows/daily.yml` - GitHub Actions 工作流
- `config/sources.txt` - 节点源列表
- `output/clash.yaml` - 生成的 Clash 配置（自动更新）
- `ui/main.py` - 桌面 GUI 界面

## 自定义源
编辑 `config/sources.txt`，每行一个 YAML 格式的节点源 URL。
