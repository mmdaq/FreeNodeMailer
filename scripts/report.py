"""生成 HTML 邮件报告。"""
from __future__ import annotations

import html
import time
from typing import Any, Dict, Iterable, List, Tuple

from util import now_cn


def _bar(value: int, total: int, width: int = 160, color: str = "#4c8bf5") -> str:
    pct = 0 if total <= 0 else value / total
    return (
        f'<div style="background:#eceff4;border-radius:4px;height:14px;width:{width}px">'
        f'<div style="background:{color};height:14px;border-radius:4px;width:{max(2, int(pct * width))}px">'
        f"</div></div>"
    )


def _delay_color(delay: int) -> str:
    if delay < 200:
        return "#1a9c53"
    if delay <= 500:
        return "#d98200"
    return "#b23c3c"


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _node_rows(nodes: List[Dict[str, Any]], results_by_name: Dict[str, Any],
               grouped: Dict[str, List[Dict[str, Any]]], statuses: Dict[str, str]) -> str:
    rows: List[str] = []
    for region, items in grouped.items():
        rows.append(
            f'<tr><td colspan="6" style="background:#f5f7fa;font-weight:700;padding:7px 10px;'
            f'border-top:1px solid #e3e8ef">{_esc(region)} '
            f'<span style="color:#8a94a6;font-weight:400">({len(items)})</span></td></tr>'
        )
        for n in items:
            r = results_by_name.get(n["name"])
            delay = (r.delay if r else None) or 0
            rows.append(
                "<tr>"
                f'<td style="padding:6px 10px;border-bottom:1px solid #eef1f5">{_esc(n["name"])}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #eef1f5;color:#5b6472">'
                f'{_esc(n.get("type", ""))}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #eef1f5;color:#5b6472">'
                f'{_esc(n.get("server", ""))}:{_esc(n.get("port", ""))}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #eef1f5;text-align:right;'
                f'font-weight:600;color:{_delay_color(delay)}">{delay} ms</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #eef1f5;color:#5b6472;'
                f'font-size:12px">{_esc(statuses.get(n["name"], ""))}</td>'
                "</tr>"
            )
    return "\n".join(rows)


def build_html_report(stats: Dict[str, Any],
                      picked: List[Tuple[Dict[str, Any], str, int]],
                      region_of: Dict[str, str],
                      validation: Dict[str, Any],
                      sources: List[Dict[str, Any]],
                      files: Dict[str, str],
                      settings: Dict[str, Any]) -> str:
    now = now_cn()
    cap = stats.get("max_delay", 500)
    total_candidates = stats.get("candidates", 0)
    tested = stats.get("tested", 0)
    avail = stats.get("available", 0)
    picked_n = len(picked)

    results_by_name = stats.get("results_by_name", {})
    statuses = stats.get("statuses", {})

    region_counts: Dict[str, List[Tuple[Dict[str, Any], str, int]]] = {}
    for n, region, delay in picked:
        region_counts.setdefault(region, []).append((n, region, delay))
    grouped_regions = {
        r: [n for n, _r2, _d in sorted(items, key=lambda x: x[2])]
        for r, items in sorted(region_counts.items(), key=lambda kv: -len(kv[1]))
    }

    # 延迟分布
    dist = stats.get("dist", {})
    dist_total = max(1, sum(dist.values()))
    dist_rows = "".join(
        f'<tr><td style="padding:4px 10px;width:90px">{k}</td>'
        f'<td style="padding:4px 10px">{_bar(v, dist_total)}</td>'
        f'<td style="padding:4px 10px;text-align:right;width:70px">{v}</td></tr>'
        for k, v in dist.items()
    )

    # 类型分布
    type_stats = stats.get("types", {})
    type_rows = "".join(
        f'<tr><td style="padding:4px 10px">{_esc(k)}</td>'
        f'<td style="padding:4px 10px">{_bar(v, max(1, picked_n))}</td>'
        f'<td style="padding:4px 10px;text-align:right">{v}</td></tr>'
        for k, v in sorted(type_stats.items(), key=lambda kv: -kv[1])
    )

    # 源状态
    src_rows = "".join(
        "<tr>"
        f'<td style="padding:5px 10px;border-bottom:1px solid #eef1f5">{_esc(s["source"])}</td>'
        f'<td style="padding:5px 10px;border-bottom:1px solid #eef1f5;color:'
        f'{"#1a9c53" if s["ok"] else "#b23c3c"};font-weight:600">'
        f'{"成功" if s["ok"] else "失败"}</td>'
        f'<td style="padding:5px 10px;border-bottom:1px solid #eef1f5;color:#5b6472">'
        f'{_esc(s.get("via") or "-")}</td>'
        f'<td style="padding:5px 10px;border-bottom:1px solid #eef1f5;text-align:right;color:#5b6472">'
        f'{s.get("nodes", 0)}</td>'
        f'<td style="padding:5px 10px;border-bottom:1px solid #eef1f5;color:#5b6472;font-size:12px">'
        f'{_esc(s.get("error") or "")}</td>'
        "</tr>"
        for s in sources
    )

    v_ok = validation.get("ok")
    v_badge = (
        '<span style="background:#e6f7ec;color:#1a9c53;padding:3px 10px;border-radius:11px;'
        'font-weight:700">✔ 校验通过</span>' if v_ok else
        '<span style="background:#fdecea;color:#b23c3c;padding:3px 10px;border-radius:11px;'
        'font-weight:700">✘ 校验失败</span>'
    )

    nodes_table = _node_rows([n for n, _r, _d in picked], results_by_name,
                             grouped_regions, statuses)

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FreeNodeMailer 每日节点报告 {now}</title></head>
<body style="margin:0;padding:0;background:#f2f4f8;font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:#20242c">
<div style="max-width:900px;margin:0 auto;padding:20px">

  <div style="background:linear-gradient(135deg,#2b6cb0,#4c8bf5);border-radius:12px;padding:22px 24px;color:#fff">
    <div style="font-size:13px;opacity:.85;letter-spacing:.5px">FreeNodeMailer 每日推送</div>
    <div style="font-size:22px;font-weight:700;margin-top:6px">今日可用节点 {picked_n} 个</div>
    <div style="font-size:13px;opacity:.9;margin-top:8px">生成时间（北京时间）：{now}</div>
  </div>

  <div style="display:flex;gap:12px;margin-top:14px;flex-wrap:wrap">
    {_stat_card("抓取节点", total_candidates, "去重归一化后")}
    {_stat_card("实测节点", tested, f"真实内核握手 + HTTP 请求")}
    {_stat_card("可用节点", f'<span style="color:#1a9c53">{avail}</span>', f"延迟 ≤ {cap} ms")}
    {_stat_card("入选配置", f'<span style="color:#2b6cb0">{picked_n}</span>', "写入 YAML")}
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px 20px;margin-top:14px">
    <div style="font-size:15px;font-weight:700;margin-bottom:10px">📎 附件与校验</div>
    <div style="line-height:1.9;font-size:13.5px">
      带日期配置：<code style="background:#f5f7fa;padding:2px 6px;border-radius:4px">{_esc(files.get("dated", ""))}</code><br>
      订阅配置：<code style="background:#f5f7fa;padding:2px 6px;border-radius:4px">{_esc(files.get("subscription", ""))}</code><br>
      配置校验（mihomo -t）：{v_badge}
      <div style="color:#5b6472;font-size:12.5px;margin-top:6px;white-space:pre-wrap">{_esc(validation.get("detail", "")[:600])}</div>
    </div>
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px 20px;margin-top:14px">
    <div style="font-size:15px;font-weight:700;margin-bottom:10px">⏱ 延迟分布（可用节点）</div>
    <table style="border-collapse:collapse;font-size:13px;width:100%">{dist_rows}</table>
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px 20px;margin-top:14px">
    <div style="font-size:15px;font-weight:700;margin-bottom:10px">🧩 协议类型（入选配置）</div>
    <table style="border-collapse:collapse;font-size:13px;width:100%">{type_rows}</table>
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px 20px;margin-top:14px">
    <div style="font-size:15px;font-weight:700;margin-bottom:10px">🌐 数据源状态</div>
    <table style="border-collapse:collapse;font-size:13px;width:100%">
      <tr style="background:#f5f7fa">
        <th style="text-align:left;padding:7px 10px">数据源</th>
        <th style="text-align:left;padding:7px 10px">状态</th>
        <th style="text-align:left;padding:7px 10px">通道</th>
        <th style="text-align:right;padding:7px 10px">节点</th>
        <th style="text-align:left;padding:7px 10px">备注</th>
      </tr>
      {src_rows}
    </table>
  </div>

  <div style="background:#fff;border-radius:12px;padding:18px 20px;margin-top:14px">
    <div style="font-size:15px;font-weight:700;margin-bottom:10px">📋 节点明细（按地区 / 延迟排序）</div>
    <table style="border-collapse:collapse;font-size:13px;width:100%">
      <tr style="background:#f5f7fa">
        <th style="text-align:left;padding:7px 10px">名称</th>
        <th style="text-align:left;padding:7px 10px">类型</th>
        <th style="text-align:left;padding:7px 10px">服务器</th>
        <th style="text-align:right;padding:7px 10px">延迟</th>
        <th style="text-align:left;padding:7px 10px">复测</th>
      </tr>
      {nodes_table}
    </table>
  </div>

  <div style="color:#8a94a6;font-size:12px;margin:18px 0 8px;line-height:1.8">
    本邮件由 FreeNodeMailer 自动发送。节点来自公开免费订阅源，测得可用 ≠ 长期稳定，
    建议在 Clash Verge 中开启「自动选择 / 故障转移」组使用。<br>
    导入方法：Clash Verge → 订阅 → 新建 → 本地文件，选择附件中的 yaml。
  </div>
</div></body></html>"""


def _stat_card(label: str, value: Any, hint: str) -> str:
    return (
        '<div style="flex:1;min-width:150px;background:#fff;border-radius:12px;padding:14px 16px">'
        f'<div style="font-size:12px;color:#8a94a6">{_esc(label)}</div>'
        f'<div style="font-size:24px;font-weight:700;margin-top:4px">{value}</div>'
        f'<div style="font-size:11.5px;color:#a7b0be;margin-top:4px">{_esc(hint)}</div>'
        "</div>"
    )


def build_text_report(stats: Dict[str, Any], picked_n: int, validation: Dict[str, Any],
                      files: Dict[str, str]) -> str:
    lines = [
        f"FreeNodeMailer 每日推送（北京时间 {now_cn()}）",
        "",
        f"抓取候选节点 : {stats.get('candidates', 0)}",
        f"实际测速节点 : {stats.get('tested', 0)}",
        f"测速可用节点 : {stats.get('available', 0)} (阈值 {stats.get('max_delay', 500)}ms)",
        f"写入配置节点 : {picked_n}",
        "",
        f"带日期配置 : {files.get('dated', '')}",
        f"订阅配置   : {files.get('subscription', '')}",
        f"配置校验   : {'通过' if validation.get('ok') else '失败'}",
        "",
        "导入方法：Clash Verge → 订阅 → 新建 → 本地文件，选择附件 yaml。",
    ]
    return "\n".join(lines)
