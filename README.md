# FreeNodeMailer

> 每日自动抓取公开免费代理节点 → 用真实 Mihomo 内核逐节点测速 → 生成带日期的
> Clash Verge 配置文件 → 内核校验通过后发送到你的邮箱。

**默认推送时间：每天 08:00（北京时间）**
**默认收件邮箱：385096659@qq.com**
**部署方式：本地 Windows 任务计划 + GitHub Actions 云端（双保险，均已配置）**

---

## 一、它到底做了什么

```
20 个公开数据源
      │  ① 抓取（原地址 + jsDelivr + GitHub API 三级镜像链，失败回退本地缓存）
      ▼
~19000 条节点记录
      │  ② 解析归一化（Clash YAML / base64 订阅 / v2ray 分享链接 → 统一格式）
      │  ③ 去重（同服务器同凭据只留字段最全的）
      ▼
~9800 个唯一节点
      │  ④ 预校验：分批交给 `mihomo -t`，剔除内核不兼容的节点
      ▼
~9800 个候选
      │  ⑤ 真实内核测速：
      │     阶段A TCP 预筛（400 并发，秒级淘汰死主机）
      │     阶段B 起 mihomo 实例，对存活节点发真实 HTTP 请求
      │            （完整协议握手 + generate_204），失败节点放宽超时复测 3 轮
      ▼
延迟 ≤ 500ms 的可用节点（实测约 130~160 个）
      │  ⑥ 生成 YAML：按地区分组、url-test 自动选择、fallback 故障转移、
      │     广告拦截 / AI / 流媒体 / 电报 分流规则
      ▼
  ⑦ 二次校验：`mihomo -t` + 启动内核确认所有节点真的被加载
      ▼
  ⑧ 发送邮件（内嵌 HTML 报告 + 带日期 yaml 附件 + 订阅 yaml 附件）
      ▼
  ⑨ 写入 output/，并保留 last_run.json 运行记录
```

### 为什么必须用真实内核测速？

免费节点里大量存在「TCP 端口活着但根本不能用」的情况：握手失败、证书过期、
UUID/密码错误、被 Cloudflare 黑洞、协议参数不匹配……

只用 socket 连一下端口 → 会推给你一堆连不上的垃圾节点。
本项目让 **Mihomo 内核（Clash Verge 同款）** 真正跑完协议握手并发出 HTTP 请求，
只有内核报告 `delay > 0` 的节点才算「可用」。**测通即代表 Clash Verge 里能用。**

> 实测数据（2026-10-08）：
> - **本机**：18962 条记录 → 去重 9806 → TCP 预筛存活 1541 → 内核实测可用 142
>   → 剔除明文代理后入选 **41 个节点**，全程约 10 分钟。
> - **GitHub Actions（国外服务器）**：18948 条 → 去重 9831 → TCP 预筛存活 4886
>   → 内核实测可用 **1019（10.4%）** → 入选 **169 个节点**，261 秒完成。
>
> 云端可用率是本机的 7 倍，所以云端推送的节点质量更好——这是双保险的价值所在。

---

## 二、快速开始

### 1. 准备邮箱授权码（必需）

1. 登录 QQ 邮箱网页版 → **设置 → 账号**
2. 找到 **POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务**
3. 开启 **POP3/SMTP服务**（或 IMAP/SMTP）
4. 按提示验证后**生成授权码**（16 位字母，形如 `abcdwxyzefghijkl`）
5. 把这个授权码填进 `.env`

> ⚠️ 授权码 ≠ QQ 登录密码。填密码会认证失败。

### 2. 配置 `.env`

```powershell
cd "F:\deepseek harness\DSH_project\FreeNodeMailer"
Copy-Item .env.example .env
notepad .env
```

```env
QQ_EMAIL=385096659@qq.com
QQ_AUTH=你的16位授权码
MAIL_TO=385096659@qq.com
```

### 3. 自检

```powershell
python scripts\main.py --doctor
```

预期输出：

```
依赖         : requests OK, PyYAML OK
内核         : ...\.cache\core\mihomo.exe   （会自动复用 D:\Clash Verge 的内核）
内核版本     : Mihomo Meta v1.19.31 windows amd64 ...
geodata      : ...\.cache\geo → ['geoip.metadb', 'geosite.dat']
数据源数量   : 19
邮箱配置     : 385096659@qq.com → 385096659@qq.com（smtp.qq.com:465）
授权码       : 已配置（16 位）
结论         : 全部就绪 ✅
```

### 4. 测试邮件通道

```powershell
python scripts\main.py --verify-mail
```

收到测试邮件后，通道就打通了。

### 5. 完整跑一次（不发邮件）

```powershell
python scripts\main.py --dry-run
```

### 6. 正式跑一次（生成 + 校验 + 发邮件）

```powershell
python scripts\main.py
```

### 7. 注册每日 08:00 定时任务

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
```

查看 / 立即测试 / 删除：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Status
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -RunNow
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Unregister
```

也可以直接双击 **`run-now.bat`** 手动运行一次。

---

## 三、命令行参数

| 命令 | 说明 |
|------|------|
| `python scripts\main.py` | 完整流程：抓取 → 测速 → 生成 → 校验 → 发邮件 |
| `python scripts\main.py --dry-run` | 只生成文件 + report，不发邮件 |
| `python scripts\main.py --verify-mail` | 只发一封测试邮件验证邮箱配置 |
| `python scripts\main.py --doctor` | 环境自检（依赖 / 内核 / geodata / 数据源 / 邮箱） |
| `python scripts\main.py --limit 200` | 只用前 200 个候选节点测速（调试提速） |
| `python scripts\main.py --no-test` | 跳过测速（**仅调试**，会写入未测速节点） |
| `python scripts\main.py --max-delay 300` | 临时把延迟阈值改成 300ms |
| `python scripts\main.py --min-nodes 20` | 临时要求至少 20 个可用节点 |
| `python scripts\main.py --json` | 结束时输出 JSON 统计（供调度/监控解析） |

---

## 四、输出文件

| 文件 | 说明 |
|------|------|
| `output/20261008clash.yaml` | **带日期的配置**，邮件主附件，可直接导入 Clash Verge |
| `output/clash.yaml` | 无日期订阅配置，内容同上，适合做长期订阅链接 |
| `output/report.html` | HTML 报告：节点明细、延迟分布、协议分布、数据源状态、校验结果 |
| `output/last_run.json` | 本次运行的结构化统计（给自动化/监控用） |
| `logs/fnm.log` | 运行日志（按天轮转，保留 30 天） |

### 导入 Clash Verge

**方式一：本地文件**（推荐，邮件附件直接导入）
1. 把邮件里的 `20261008clash.yaml` 存到本地
2. Clash Verge → **订阅** → 右上角 **新建** → 类型选 **Local**（本地文件）
3. 选择该 yaml → 保存 → 启用

**方式二：URL 订阅**（推送到 GitHub 后可用）
```
https://raw.githubusercontent.com/<你的用户名>/<仓库名>/main/output/clash.yaml
```
> 国内直连 raw.githubusercontent.com 可能超时，Clash Verge 里可换用
> `https://cdn.jsdelivr.net/gh/<用户名>/<仓库名>@main/output/clash.yaml`

### 配置文件里有什么

- `proxies`：测速通过且内核校验通过的节点
- `proxy-groups`：
  - `♻️ 自动选择`（url-test，每 300s 自动挑最快）
  - `🔁 故障转移`（fallback，当前节点挂了自动切换）
  - `🚀 节点选择`（手动选择，含各地区子组）
  - 各地区组（🇭🇰 香港 / 🇯🇵 日本 / 🇺🇸 美国 …）
  - `🤖 AI服务` / `🌍 国外媒体` / `📲 电报消息` / `🎯 全球直连` / `🛑 广告拦截` / `🐟 漏网之鱼`
- `rules`：基于 geosite/geoip 的分流规则，国内直连、国外走代理
- `dns`：fake-ip 增强模式，国内外 DNS 分流，防污染

---

## 五、参数配置

主配置在 **`config/settings.yaml`**，关键项：

| 配置项 | 默认 | 说明 |
|--------|------|------|
| `fetch.concurrency` | 8 | 抓取并发源数 |
| `fetch.timeout` | 18 | 单源超时（秒） |
| `fetch.retries` | 2 | 单源重试次数 |
| `test.concurrency` | 48 | 同时测速的节点数 |
| `test.max_delay` | 500 | 延迟阈值（ms），超过则剔除 |
| `test.timeout_ms` | 3000 | 首轮单节点超时（ms） |
| `test.retest_timeout_ms` | 6000 | 复测放宽超时（ms） |
| `test.retest_rounds` | 2 | 失败节点复测轮数 |
| `test.url` | gstatic generate_204 | 测速用的真实请求地址 |
| `select.max_candidates` | 1200 | 进入测速的候选上限（控制耗时） |
| `select.max_nodes` | 200 | 写入 YAML 的最大节点数 |
| `select.max_per_region` | 40 | 每个地区最大节点数 |
| `select.min_nodes` | 5 | 最少可用节点数，低于此值不发邮件 |
| `output.main_group` | 🚀 节点选择 | 主代理组名 |
| `output.mixed_port` | 7890 | 客户端混合端口 |
| `output.enable_rules` | true | 是否写入分流规则 |

也支持用环境变量临时覆盖（配合 GitHub Actions 很方便）：

```
FNM_MAX_DELAY / FNM_TIMEOUT_MS / FNM_TEST_CONCURRENCY / FNM_MAX_NODES
FNM_MIN_NODES / FNM_FETCH_CONCURRENCY / FNM_MAIL_TO / FNM_CORE_PATH
```

---

## 六、数据源

数据源列表在 **`config/sources.txt`**，一行一个 `URL|显示名`。

**三级镜像链**（针对 `raw.githubusercontent.com`）自动生效：

| 顺序 | 通道 | 说明 |
|------|------|------|
| 1 | 原地址 | `raw.githubusercontent.com` |
| 2 | jsDelivr CDN | `cdn.jsdelivr.net/gh/user/repo@ref/path`，国内快 |
| 3 | GitHub API | `api.github.com/repos/.../contents/...`（base64） |
| 4 | jsDelivr Fastly/Gcore | 备用 CDN 节点 |

**源失败处理**：某源本轮抓不到 → 自动回退到**上一次成功的本地缓存**（`.cache/sources/`），
保证不会因为某个源挂了就推空邮件。

**添加/删除源**：直接编辑 `config/sources.txt`，注释用 `#`。
跑一次看日志里的 `[OK]/[FAIL]` 决定去留。

---

## 七、GitHub Actions 云端部署（已启用）

`.github/workflows/daily-v2.yml` 已配置并实测运行：

- **触发**：每天 UTC 00:00 = **北京时间 08:00**；也支持手动 `workflow_dispatch`
- **流程**：离线自检 → 下载 mihomo 内核 → 下载 geodata → 内核级配置格式校验
  → 抓取 → 测速 → 生成 → 二次校验 → 发邮件 → 提交 output 回仓库
- **邮件密钥**（Settings → Secrets and variables → Actions）

| Secret | 值 |
|--------|-----|
| `QQ_EMAIL` | `385096659@qq.com` |
| `QQ_AUTH` | 16 位授权码 |
| `MAIL_TO` | 可选，缺省发给 `QQ_EMAIL` |

### 本机 git push 被墙怎么办

本机 `github.com:443` 经常被重置，`git push` 会失败，但 `api.github.com` 可用。
用仓库自带的脚本发布：

```powershell
python scripts\git_publish_api.py main          # 常规更新
python scripts\git_publish_api.py main --force  # 强制覆盖
```

### 订阅链接

`output/` 已纳入版本管理，工作流每天会把最新配置提交回 `main`：

```
# 国内推荐（gh-proxy 加速，实测可拉到最新内容）
https://gh-proxy.com/https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/output/clash.yaml

# 备用
https://ghfast.top/https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/output/clash.yaml
https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/output/clash.yaml
```

> ⚠️ 不要用 `cdn.jsdelivr.net` 做订阅：实测它对 `@main` 的缓存可能长时间不刷新，
> 会一直返回旧内容。它只适合拉取不变的文件。
>
> GitHub 只自动调度**默认分支(main)** 上的 schedule 工作流；本仓库已完成切换。

---

## 八、目录结构

```
FreeNodeMailer/
├── .github/workflows/daily.yml   # GitHub Actions 每日 08:00
├── config/
│   ├── sources.txt               # 数据源列表（19 个）
│   └── settings.yaml             # 全部运行参数
├── scripts/
│   ├── main.py                   # 主流程 + CLI
│   ├── fetcher.py                # 抓取（镜像链 / 重试 / 缓存回退）
│   ├── parser.py                 # 解析归一化（YAML/base64/分享链接）
│   ├── tester.py                 # 真实内核测速 + 预校验 + YAML 校验
│   ├── yaml_builder.py           # 生成 Clash Verge 配置（分组/规则）
│   ├── report.py                 # HTML / 文本报告
│   ├── mailer.py                 # QQ SMTP 发信
│   ├── util.py                   # 配置 / 日志 / 路径
│   └── register_task.ps1         # Windows 定时任务注册
├── output/                       # 生成结果
├── logs/                         # 运行日志
├── .cache/                       # 内核 / geodata / 源缓存
├── run.bat                       # 定时任务入口
├── run-now.bat                   # 手动运行（调试）
├── .env                          # 邮箱授权码（不提交 git）
└── requirements.txt
```

---

## 九、故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `SMTP 认证失败` | QQ_AUTH 填成了登录密码，或授权码过期 | 重新生成授权码，填进 `.env` |
| 收到邮件但节点很少 | 免费源整体质量波动 | 正常；可调大 `select.max_candidates` 或放宽 `test.max_delay` |
| 没收到邮件，日志显示「可用节点少于要求」 | 可用节点低于 `select.min_nodes` | 故意不发空邮件；调大候选上限或降低 `min_nodes` |
| 日志显示「交付 YAML 未通过校验」 | 生成的配置被内核拒绝 | 已自动不发邮件保护；看 `logs/fnm.log` 里 `mihomo -t` 的输出 |
| 抓取大量 `[FAIL]` | 网络到 GitHub 不通 | 镜像链会自动接管；仍失败会回退上一次缓存 |
| 内核下载失败 | GitHub Release 被墙 | 已内置 `gh-proxy.com` 等镜像；或直接复用本机 Clash Verge 内核 |
| 定时任务没跑 | 电脑关机 / 休眠 / 未登录 | `-Status` 查看结果码；需要关机也跑就用 GitHub Actions |
| 任务结果码 `0x41303` | 任务从未运行过 | 正常，等首次触发或 `-RunNow` |
| 定时任务结果码 `0x1` | main.py 返回非 0 | 看 `logs/runner.out.log` 和 `logs/fnm.log` |

### 查看定时任务

```powershell
Get-ScheduledTaskInfo -TaskName FreeNodeMailer-DailyPush | Format-List
Get-Content logs\fnm.log -Tail 60
Get-Content logs\runner.out.log -Tail 30
```

---

## 十、退出码约定

| 退出码 | 含义 |
|--------|------|
| 0 | 成功（已生成并通过校验；未加 `--dry-run` 时已发信） |
| 1 | 自检/邮箱测试失败 |
| 2 | 没有配置数据源 |
| 3 | 所有数据源都没解析出节点 |
| 4 | 内核异常（下载/启动/预校验失败） |
| 5 | 没有可用节点 |
| 6 | 交付 YAML 未通过内核校验（已保护性跳过发信） |
| 7 | 可用节点少于 `min_nodes` |
| 8 | 邮件发送失败 |

---

## 十一、安全与合规说明

- 节点全部来自**公开的免费订阅源**，本项目不做任何破解或私有资源抓取。
- 免费节点**随时可能失效**，这是免费资源的固有属性；本项目通过
  「实测可用 + 自动选择组 + 故障转移组」尽量提升可用体验。
- 请勿使用本工具生成的内容从事任何违法活动；请遵守当地法律法规。
- `.env` 含邮箱授权码，已在 `.gitignore` 中排除，**不要提交到仓库**。
