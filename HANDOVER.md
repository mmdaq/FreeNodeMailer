# FreeNodeMailer 项目交接文档

> **更新日期**：2026-10-08
> **GitHub 仓库**：<https://github.com/mmdaq/FreeNodeMailer>（**已推送，main 分支已切换为本次重写版**）
> **本地路径**：`F:\deepseek harness\DSH_project\FreeNodeMailer`
> **订阅邮箱**：385096659@qq.com
> **当前状态**：✅ 本地已实测跑通并成功发信；✅ 云端 Actions 已配置并手动验证

---

## 一、项目当前状态

### 1.1 一句话说明

每天早晨 **08:00（北京时间）**自动从 20 个公开数据源抓取约 1.9 万条节点记录，
用**真实 Mihomo 内核**（Clash Verge 同款）逐节点实测延迟，
过滤出真正可用的节点，生成**带日期的 `.yaml`** 附件发送到指定邮箱，
并在发信前用内核把配置**完整校验两遍**，确保导入 Clash Verge 一定能用。

### 1.2 完成度

| 需求 | 状态 | 实现位置 |
|------|------|---------|
| 每日早晨 8 点推送 | ✅ 双保险 | 本地：`scripts/register_task.ps1`（任务 `FreeNodeMailer-DailyPush`，已注册）；云端：`.github/workflows/daily-v2.yml`（cron `0 0 * * *`） |
| 从网络 / GitHub 获取节点 | ✅ | `scripts/fetcher.py`，20 个源 + 三级镜像链 |
| 经过测速的可用节点 | ✅ | `scripts/tester.py`，真实内核 HTTP 实测 |
| 稳定节点 | ✅ | 4 轮复测 + 延迟阈值 + 单主机限流 |
| 邮件发送到 385096659@qq.com | ✅ 已实测收到 | `scripts/mailer.py`（QQ SMTP SSL） |
| 附带可直接导入 Clash Verge 的带日期 .yaml | ✅ | `output/2026MMDDclash.yaml` |
| .yaml 本身也要经过检测 | ✅ 两遍 | ① `mihomo -t` 语法/字段校验 ② 启动内核确认每个节点真被加载 |

### 1.3 本次重做修复的关键缺陷

原仓库（`main` 分支旧实现）存在**致命缺陷，一直在给用户发空配置**：

| 原设计 | 实际问题 | 现在的做法 |
|--------|---------|-----------|
| 只用 `raw.githubusercontent.com` | 国内网络直接超时，抓不到任何节点 | **三级镜像链**：原地址 → jsDelivr → GitHub API(base64)，失败回退本地缓存 |
| 只有 TCP 可达判断（`scripts/fetch.py`） | TCP 通 ≠ 能用，且实测产出为 `proxies: []` | **真实内核测速**：起 mihomo，跑完整协议握手 + 真实 HTTP 请求 |
| 生成后直接发邮件 | 任何一个字段不兼容的节点都会让整份配置加载失败 | **两道校验**：候选预校验 + 交付 YAML 二次校验，不过则不发信 |
| 仅 2 个数据源 | 源失效即推空配置 | 20 个源 + 单源失败缓存回退 + 源状态上报到邮件 |
| 节点名可含 `#` | YAML 里 `#` 是注释符；重名会让 mihomo **fatal** | 名称净化 + 全局唯一化（`parser.sanitize_name / unique_names`） |
| 写了 `global-client-fingerprint` | 新版 mihomo **已移除该字段**，会导致配置加载失败 | 改为按节点写 `client-fingerprint`，并有黑名单回归测试 |

**实测证据**：旧 `main` 分支的 `output/clash.yaml` 中 `proxies:` 为 `[]`（空）；
本次重写版实测产出 **41 个经内核验证可用的节点**，并已成功发送到 385096659@qq.com。

---

## 二、目录结构

```
FreeNodeMailer/
├── .github/workflows/daily-v2.yml # GitHub Actions 每日 08:00（UTC 00:00）
├── config/
│   ├── sources.txt               # 20 个数据源（URL|显示名）
│   └── settings.yaml             # 全部运行参数
├── scripts/
│   ├── main.py                   # 主流程 + CLI（run / doctor / verify-mail）
│   ├── runner.py                 # 定时任务入口（强制 UTF-8，兜底异常）
│   ├── fetcher.py                # 抓取：镜像链 / 重试 / 缓存回退
│   ├── parser.py                 # 解析归一化：Clash YAML / base64 / 分享链接
│   ├── tester.py                 # 真实内核测速 + 预校验 + YAML 校验
│   ├── yaml_builder.py           # 生成 Clash Verge 配置（地区组 / 规则 / DNS）
│   ├── report.py                 # HTML 邮件报告
│   ├── mailer.py                 # QQ SMTP 发信
│   ├── util.py                   # 配置 / 日志 / 路径
│   ├── selftest.py               # 43 项离线自检（改代码后必跑）
│   ├── config_check.py           # 内核级配置格式校验（生成物必须可导入）
│   ├── git_publish_api.py        # github.com 被墙时用 API 发布提交
│   ├── git_push_via_api.py       # API 发布的底层实现
│   └── register_task.ps1         # Windows 任务计划注册
├── output/                       # 生成结果
│   ├── 20261008clash.yaml        # 带日期配置（邮件主附件）
│   ├── clash.yaml                # 订阅用配置
│   ├── report.html               # HTML 报告
│   └── last_run.json             # 本次运行统计
├── logs/                         # fnm.log（按天轮转 30 天）+ runner.out.log
├── .cache/
│   ├── core/mihomo.exe           # 内核（自动复用 D:\Clash Verge 的）
│   ├── geo/                      # geoip.metadb / geosite.dat
│   └── sources/                  # 每个源最后一次成功内容
├── run.bat                       # 定时任务入口
├── run-now.bat                   # 手动运行（调试）
├── .env / .env.example           # 邮箱授权码（.env 已配置，且被 git 忽略）
├── requirements.txt              # requests + PyYAML
├── README.md                     # 使用手册
└── HANDOVER.md                   # 本文档
```

---

## 三、关键设计说明

### 3.1 抓取：三级镜像链（`fetcher.py`）

针对 `raw.githubusercontent.com` 自动生成尝试链：

```
1. 原始地址                    raw.githubusercontent.com
2. cdn.jsdelivr.net/gh/...     jsDelivr CDN（国内实测 0.1~20s）
3. api.github.com/repos/...    GitHub API，内容 base64（国内实测可用）
4. fastly / gcore jsDelivr     备用 CDN
```

- 每个源默认重试 2 轮，全部失败则**回退到 `.cache/sources/` 里的上次成功内容**
- 每轮运行都会把「哪个源走了哪个通道、抓了多少节点」写进邮件报告

### 3.2 测速：两阶段真实内核检测（`tester.py`）

免费节点实测可用率只有 **3%~6%**，所以必须省时间：

```
阶段 A  TCP 预筛
        400 并发 socket 连 host:port，1.5s 超时，秒级淘汰死主机
        （仅省时间，不作为"可用"依据；可达率过低时自动退化为全量测速）

阶段 B  内核测速
        起一个 mihomo 实例 → 遍历每个节点调 /proxies/{name}/delay
        → 内核真的去握手 + 请求 http://www.gstatic.com/generate_204
        第 1 轮 3s 超时 → 之后 4s / 6s / 8s 逐轮复测失败节点（克制冷启动误杀）
        整个阶段受 test_budget（默认 900s）约束，到点停止复测
```

结果判定规则：
- 只有内核返回 `delay > 0` 才算可用
- 最终延迟取多轮最小值；`> max_delay` 的剔除
- 节点被内核拒绝加载的（字段不兼容）在预校验阶段就剔除

### 3.3 配置安全：两道校验（`tester.preflight_filter` + `main.run_pipeline`）

**为什么必须有**：mihomo 只要遇到一个节点字段错误，**整份配置都加载失败**，
用户导入 Clash Verge 就会直接报错。所以：

1. **候选预校验**：把所有候选节点塞进临时配置跑 `mihomo -t`；
   失败则从报错文本里定位问题节点（`proxy N:` 下标 / 节点名）定点剔除，最多重试 12 次；
2. **交付二次校验**：对最终 `2026MMDDclash.yaml` 跑 `mihomo -t`，
   再启动一次内核，逐条确认配置里的每个节点真的出现在 `/proxies` 里；
   任一环节失败 → 记录日志 + **不发邮件**（避免推送坏配置）。

### 3.4 配置内容（`yaml_builder.py`）

生成的是 mihomo 内核格式，Clash Verge / Clash Meta / FlClash 均可直接导入：

- `proxies`：通过测速与校验的节点，按延迟升序
- `proxy-groups`：
  - `♻️ 自动选择`（url-test，300s 自动挑最快）
  - `🔁 故障转移`（fallback，当前节点挂了自动切）
  - `🚀 节点选择`（手动，含各地区子组）
  - 各地区组（🇭🇰 香港 / 🇯🇵 日本 / 🇺🇸 美国 …）
  - `🤖 AI服务` / `🌍 国外媒体` / `📲 电报消息` / `🎯 全球直连` / `🛑 广告拦截` / `🐟 漏网之鱼`
- `rules`：geosite/geoip 分流，国内直连、国外走代理
- `dns`：fake-ip 增强模式 + 国内外 DNS 分流（防污染）
- `sniffer`：HTTP/TLS 嗅探，提升分流准确率

### 3.5 节点筛选策略

| 策略 | 配置项 | 默认 |
|------|--------|------|
| 延迟阈值 | `test.max_delay` | 500 ms |
| 明文代理排除 | `select.exclude_insecure` | true（排除 http/socks5） |
| 单地区上限 | `select.max_per_region` | 40 |
| 单主机上限 | `select.max_per_server` | 2（避免一台服务器占满配置） |
| 总节点上限 | `select.max_nodes` | 200 |

---

## 四、关键配置

### 4.1 邮箱（`.env`，不进 git）

```env
QQ_EMAIL=385096659@qq.com
QQ_AUTH=你的16位授权码
MAIL_TO=385096659@qq.com
```

**授权码获取**：QQ邮箱网页版 → 设置 → 账号 → 开启 POP3/SMTP 服务 → 生成授权码。
⚠️ 是 16 位授权码，**不是 QQ 登录密码**。

### 4.2 GitHub Secrets（用 Actions 时需要）

| Secret | 值 |
|--------|-----|
| `QQ_EMAIL` | `385096659@qq.com` |
| `QQ_AUTH` | 16 位授权码 |
| `MAIL_TO` | `385096659@qq.com`（可省略） |

### 4.3 定时任务

```powershell
# 注册每日 08:00
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1

# 查看状态 / 立即运行 / 删除
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Status
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -RunNow
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Unregister
```

任务名：`FreeNodeMailer-DailyPush`

> ⚠️ 本地定时任务要求 **08:00 时电脑开机 + 联网**，且默认「用户登录时运行」。
> 电脑经常关机的话，建议同时启用 GitHub Actions（§9）。

---

## 五、常用命令

```powershell
cd "F:\deepseek harness\DSH_project\FreeNodeMailer"

python scripts\main.py --doctor         # 环境自检（依赖/内核/geodata/数据源/邮箱）
python scripts\main.py --verify-mail    # 发一封测试邮件
python scripts\main.py --dry-run        # 完整跑一遍但不发邮件
python scripts\main.py                  # 正式：生成 + 校验 + 发邮件
python scripts\main.py --limit 300      # 只用 300 个候选测速（调试提速）
python scripts\main.py --max-delay 300  # 临时改阈值
python scripts\selftest.py              # 43 项离线自检（改代码后必跑）
python scripts\config_check.py          # 内核级配置格式校验（生成物必须可导入）
python scripts\git_publish_api.py main  # github.com 被墙时用 API 发布提交
```

或直接双击 `run-now.bat`（带窗口，方便看日志）。

> 定时任务内部走的是 `run.bat` → `scripts\runner.py`（强制 UTF-8，
> 避免中文日志在 cmd 重定向下乱码，并兜底记录异常与退出码）。

---

## 六、实测数据

### 6.1 本机实测（2026-10-08 14:10，Windows）

| 指标 | 数值 |
|------|------|
| 数据源 | 20 个，全部成功 |
| 抓取耗时 | 20s ~ 240s（视镜像通道而定） |
| 原始节点记录 | 18962 条 |
| 去重后 | 9806 个 |
| 预校验剔除 | 18 个内核不兼容节点（35 次内核调用，约 6 秒） |
| TCP 预筛 | 1541/9806 可达（55 秒） |
| 内核实测可用 | 142 个（1.4%） |
| 明文代理排除 | 101 个（http/socks5，默认排除） |
| **最终入选** | **41 个节点**（延迟均 ≤ 500ms，最低 63ms） |
| 协议分布 | vless 13 / anytls 12 / trojan 7 / vmess 5 / ss 2 / hysteria2 2 |
| 单次运行总耗时 | 约 10 分钟 |
| 邮件 | ✅ 已成功送达 385096659@qq.com（118KB，2 个附件） |

### 6.2 GitHub Actions 云端实测（2026-10-08 06:30 UTC，Ubuntu）

| 指标 | 数值 |
|------|------|
| 数据源 | 20 个，全部成功（服务器在国外，**无需镜像链，0.6 秒抓完**） |
| 原始节点记录 | 18948 条 → 去重 9831 |
| TCP 预筛 | 4886/9831 可达（25 秒，明显优于国内） |
| 内核实测可用 | **1019 个（10.4%）** |
| 明文代理排除 | 370 个 |
| **最终入选** | **169 个节点** |
| 协议分布 | vless 83 / ss 32 / vmess 22 / anytls 16 / trojan 14 / hysteria2 2 |
| 延迟分布 | <100ms 76 个，100-200ms 58 个，200-350ms 27 个，350-500ms 8 个 |
| 总耗时 | 261 秒 |
| 邮件 | ✅ 已发送（345KB，2 个附件） |
| 工作流 | 全部 11 个步骤 success |

**结论**：
1. **云端（国外服务器）可用率是国内的 7 倍**（10.4% vs 1.4%），
   所以云端推送的节点质量明显更好——这也是双保险的价值所在。
2. 免费节点天然是「大量失效 + 少量可用」。`http`/`socks5` 明文代理可用率虚高
   （本机实测 30%~37%）但质量与安全性差，默认由
   `select.exclude_insecure: true` 排除；真正用于翻墙的加密协议可用率约 1%~10%。
3. 本项目靠**真实内核测速**保证「进了 yaml 的节点在 Clash Verge 里确实能用」。

---

## 七、故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `SMTP 认证失败` | QQ_AUTH 是登录密码或已失效 | 重新生成授权码 |
| 邮件里节点很少（个位数） | 免费源整体波动 | 正常；加大 `test.test_budget` 或放宽阈值 |
| 没收到邮件，日志「可用节点少于要求」 | 低于 `select.min_nodes` | 故意保护，不发空配置 |
| 「交付 YAML 未通过校验」 | 生成配置被内核拒绝 | 已保护性不发信；看 `logs/fnm.log` 里 `mihomo -t` 输出 |
| 抓取大量 `[FAIL]` | 到 GitHub 网络不通 | 镜像链自动接管；仍失败回退上次缓存 |
| 定任务结果码 `0x1` | main.py 返回非 0 | 看 `logs/runner.out.log` + `logs/fnm.log` |
| 定任务结果码 `0x41303` | 任务从未运行 | 正常，`-RunNow` 测试 |
| 内核下载失败 | GitHub Release 被墙 | 已内置 `gh-proxy.com`/`ghfast.top` 镜像；或复用本机 Clash Verge 内核 |

查看日志：

```powershell
Get-Content logs\fnm.log -Tail 60
Get-Content logs\runner.out.log -Tail 30
Get-ScheduledTaskInfo -TaskName FreeNodeMailer-DailyPush | Format-List
```

---

## 八、退出码约定

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 自检/邮箱测试失败 |
| 2 | 未配置数据源 |
| 3 | 所有源都没解析出节点 |
| 4 | 内核异常（下载/启动/预校验） |
| 5 | 无可用节点 |
| 6 | 交付 YAML 未通过校验（已跳过发信） |
| 7 | 可用节点少于 `min_nodes` |
| 8 | 邮件发送失败 |

---

## 九、GitHub 云端部署（已启用）

### 9.1 当前状态

| 项目 | 值 |
|------|-----|
| 仓库 | <https://github.com/mmdaq/FreeNodeMailer>（public） |
| 默认分支 | `main`（已强制切换为本次重写版，旧实现已移除） |
| 工作流 | `.github/workflows/daily-v2.yml`（旧的 `daily.yml` 已删除，避免两个流程抢同一批文件） |
| 触发 | 每天 UTC 00:00 = **北京 08:00**；也支持 Actions 页面手动触发 |
| Secrets | `QQ_EMAIL`、`QQ_AUTH`（`MAIL_TO` 未设置，代码会回落到 `QQ_EMAIL`/settings.yaml 的 `mail.to`） |

> ⚠️ `QQ_AUTH` 这个 Secret 是 2026-09-26 设置的。本次本地实测用的授权码可以正常发信；
> 若以后换授权码，请同步更新：Settings → Secrets and variables → Actions → `QQ_AUTH`。

### 9.2 手动触发一次（验证用）

```bash
# 需要带 repo+workflow 权限的 token
curl -X POST \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/mmdaq/FreeNodeMailer/actions/workflows/daily-v2.yml/dispatches \
  -d '{"ref":"main","inputs":{"dry_run":"false","limit":"0"}}'
```

或直接网页：Actions → 「FreeNodeMailer 每日节点推送」→ Run workflow。

### 9.3 订阅链接（云端每天提交后自动更新）

`output/` 已纳入版本管理（其内部 `output/.gitignore` 覆盖了根 `.gitignore` 的忽略规则），
且工作流会每天把新生成的配置提交回 `main`，因此订阅链接长期有效。

**推荐用的链接（国内实测可正常拉取最新内容，2026-10-08 验证）：**

```
# 1) gh-proxy.com 加速（国内直连可用，带 GitHub 实时内容）
https://gh-proxy.com/https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/output/clash.yaml

# 2) ghfast.top 加速（备用）
https://ghfast.top/https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/output/clash.yaml

# 3) 原始地址（需能访问 GitHub）
https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/output/clash.yaml
```

带日期的当日配置同理：

```
https://gh-proxy.com/https://raw.githubusercontent.com/mmdaq/FreeNodeMailer/main/output/20261008clash.yaml
```

> ⚠️ **不要用 `cdn.jsdelivr.net` 做订阅**：实测它对 `@main` 的缓存可能长时间不刷新
> （本次验证时它返回的仍是旧的 1240 字节空配置）。它只适合拉取不常变的内容。
>
> `output/` 里只有公开免费节点，不含任何密钥，可以安全提交。
> 若你不想公开节点列表，可把 `output/` 重新加入 `.gitignore`，
> 订阅链接随之失效，但邮件推送不受影响（产物也可从 Actions 页面下载）。

### 9.4 ⚠️ 本机 git push 被墙（重要）

本机到 `github.com:443` 经常被重置（`Recv failure: Connection was reset`），
而 `api.github.com` 一直可用。因此**本机不要依赖 `git push`**，改用：

```powershell
python scripts\git_publish_api.py main          # 常规更新
python scripts\git_publish_api.py main --force  # 强制覆盖
```

该脚本用 GitHub Git Data API 上传变化的文件并更新 ref，效果与 push 相同。
凭据从 `git credential store` 读取（token 属主 `mmdaq`，权限 `repo` + `workflow`），
不会打印或落盘明文。

> 说明：API 生成的远端 commit SHA 与本地会不同（GitHub 写入自己的 committer 时间戳），
> **文件内容完全一致**。这属正常现象，不影响使用。

---

## 十、后续可优化项

- [ ] 增加更多优质数据源（`config/sources.txt` 直接加行即可）
- [ ] 节点质量评分：连续多日可用 + 延迟稳定性加权排序
- [ ] 端口/协议维度去重，减少同主机重复测试
- [ ] 支持多收件人分组推送（不同人不同阈值）
- [ ] 加入 Telegram / 企业微信 通知渠道
- [ ] 把「历史可用率」写进 `.cache/history.json`，优先测历史成功节点

---

## 十一、开发注意事项

1. **改完代码必须跑** `python scripts\selftest.py`（43 项，覆盖解析/去重/命名/配置生成）
   和 `python scripts\config_check.py`（内核级校验，确认生成物能真正导入）
2. 新增节点协议支持时，注意同步更新：
   - `parser.SUPPORTED_BY_MIHOMO`（内核支持的协议白名单）
   - `parser.normalize_proxy`（字段归一化）
   - `parser.SCHEME_MAP`（分享链接 scheme）
3. **不要**在节点名里保留 `#`（YAML 注释符）；名称唯一性由
   `parser.unique_names` 统一保证，mihomo 遇重名会直接 fatal
4. 配置字段有版本风险：**`global-client-fingerprint` 已被新版 mihomo 移除**，
   写了会导致配置加载失败。`yaml_builder.REMOVED_CONFIG_KEYS` +
   `selftest` 里有回归测试防止再犯；类似被移除的字段请一并加入黑名单
5. 中文 Windows 下读内核输出必须按字节读再逐个尝试 utf-8/gbk 解码，
   直接 `subprocess.run(text=True)` 会因 GBK 解码失败抛异常（已修复）
6. `.ps1` 脚本要存成 **UTF-8 with BOM**，否则 Windows PowerShell 5.1
   会按 ANSI 解码导致语法错误；`.bat` 尽量纯 ASCII
7. `.env` 已在 `.gitignore` 中，**永远不要**提交；仓库历史上 `master` 分支
   曾提交过一个 `.env`（其中 `QQ_AUTH` 为空，未泄露密钥），如需可自行清理

---

## 十二、联系方式

| 项目 | 信息 |
|------|------|
| 本地路径 | `F:\deepseek harness\DSH_project\FreeNodeMailer` |
| 订阅邮箱 | 385096659@qq.com |
| 文档更新 | 2026-10-08 |
