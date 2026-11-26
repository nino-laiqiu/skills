"""事件追踪看板 - 生成自包含静态 HTML。零第三方依赖。"""
import datetime as dt
import html
import json
from pathlib import Path

STATUS_META = {
    "todo": ("待办", "#6b7280"),
    "doing": ("进行中", "#2563eb"),
    "blocked": ("受阻", "#dc2626"),
    "done": ("已完成", "#059669"),
}


def _deadline_status(e, today):
    """返回 (urgency_rank, label, css_class)。rank 越小越紧急。"""
    dl = e.get("deadline", "")
    if not dl:
        return 4, "无截止", "none"
    try:
        d = dt.date.fromisoformat(dl)
    except (ValueError, TypeError):
        return 4, "日期异常", "none"
    delta = (d - today).days
    if delta < 0:
        return 0, "逾期 %d 天" % -delta, "overdue"
    if delta == 0:
        return 1, "今天截止", "today"
    if delta <= 3:
        return 2, "%d 天后截止" % delta, "soon"
    if delta <= 7:
        return 3, "%d 天后截止" % delta, "week"
    return 4, "%d 天后" % delta, "later"


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def build_dashboard(events, today=None, year=None):
    """events: list[dict]; today: dt.date; year: int 标注年份。返回 HTML 字符串。"""
    today = today or dt.date.today()
    items = []
    for e in events:
        rank, dl_label, dl_class = _deadline_status(e, today)
        status = e.get("status", "todo")
        done = status == "done"
        items.append({
            "id": e.get("id", ""),
            "event": e.get("event", ""),
            "what": e.get("what", ""),
            "when": e.get("when", ""),
            "deadline": e.get("deadline", ""),
            "status": status,
            "tags": e.get("tags", []),
            "note": e.get("note", ""),
            "dl_label": dl_label,
            "dl_class": dl_class,
            "_rank": 9 if done else rank,
            "_done": done,
        })
    # 未完成优先，其次按紧急度，再按截止日期
    items.sort(key=lambda x: (x["_done"], x["_rank"], x["deadline"] or "9999", x["id"]))

    pending = [x for x in items if not x["_done"]]
    overdue = [x for x in pending if x["dl_class"] == "overdue"]
    due3 = [x for x in pending if x["dl_class"] in ("today", "soon")]
    no_dl = [x for x in pending if x["dl_class"] == "none"]
    done_n = len(items) - len(pending)
    all_tags = sorted({t for x in items for t in x["tags"]})
    generated = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")

    cards = [
        ("待办", len(pending), "pending", "尚未完成"),
        ("逾期", len(overdue), "overdue", "已过截止日"),
        ("3天内截止", len(due3), "soon", "含今天"),
        ("已完成", done_n, "done", "累计"),
    ]
    card_html = "".join(
        '<button class="card %s" data-filter="%s" type="button">'
        '<div class="card-num">%d</div>'
        '<div class="card-label">%s</div><div class="card-sub">%s</div></button>'
        % (cls, cls, n, _esc(label), _esc(sub)) for label, n, cls, sub in cards
    )

    tag_filters = '<button class="filter active" data-tag="">全部</button>' + "".join(
        '<button class="filter" data-tag="%s">%s</button>' % (_esc(t), _esc(t))
        for t in all_tags
    )

    rows = []
    for x in items:
        st_label, st_color = STATUS_META.get(x["status"], (x["status"], "#6b7280"))
        tags_html = "".join(
            '<span class="tag">%s</span>' % _esc(t) for t in x["tags"]
        )
        note_html = ('<div class="note">%s</div>' % _esc(x["note"])) if x["note"] else ""
        rows.append(
            '<div class="row %s %s" data-status="%s" data-done="%s" data-dlclass="%s" data-tags="%s">'
            '<div class="row-main">'
            '<div class="row-title">%s <span class="status" style="color:%s;border-color:%s">%s</span></div>'
            '<div class="row-what">%s</div>'
            '</div>'
            '<div class="row-meta">'
            '<div class="deadline %s">%s</div>'
            '<div class="date-line">记于 %s</div>'
            '<div class="tags">%s</div>'
            '</div>%s'
            '</div>' % (
                "done" if x["_done"] else "open",
                x["dl_class"],
                _esc(x["status"]),
                "1" if x["_done"] else "0",
                x["dl_class"],
                _esc(",".join(x["tags"])),
                _esc(x["event"]), st_color, st_color, _esc(st_label),
                _esc(x["what"]),
                x["dl_class"], _esc(x["dl_label"]),
                _esc(x["when"]),
                tags_html,
                note_html,
            )
        )
    rows_html = "".join(rows) if rows else '<div class="empty">暂无事件记录。用 log 命令添加。</div>'

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>事件追踪看板</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f1115;color:#e5e7eb;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;padding:32px;line-height:1.6}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:22px;font-weight:600;margin-bottom:4px}
.sub{color:#9ca3af;font-size:13px;margin-bottom:24px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
.card{background:#181b21;border:1px solid #2a2e37;border-radius:12px;padding:16px;text-align:left;cursor:pointer;font-family:inherit;transition:border-color .15s,background .15s}
.card:hover{border-color:#4b5563;background:#1d212a}
.card.active{border-color:#60a5fa;background:#1e293b;box-shadow:inset 0 0 0 1px #60a5fa}
.card-num{font-size:28px;font-weight:600;line-height:1.2}
.card-label{font-size:13px;color:#d1d5db;margin-top:4px}
.card-sub{font-size:11px;color:#6b7280;margin-top:2px}
.card.pending .card-num{color:#60a5fa}
.card.overdue .card-num{color:#f87171}
.card.soon .card-num{color:#fbbf24}
.card.done .card-num{color:#34d399}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.filter{background:#181b21;color:#9ca3af;border:1px solid #2a2e37;border-radius:20px;padding:5px 14px;font-size:12px;cursor:pointer}
.filter:hover{border-color:#4b5563;color:#e5e7eb}
.filter.active{background:#2563eb;color:#fff;border-color:#2563eb}
.list{display:flex;flex-direction:column;gap:10px}
.row{background:#181b21;border:1px solid #2a2e37;border-left:3px solid #3b82f6;border-radius:10px;padding:14px 16px;display:flex;gap:20px;justify-content:space-between}
.row.overdue{border-left-color:#ef4444}
.row.today{border-left-color:#f59e0b}
.row.soon{border-left-color:#fbbf24}
.row.done{opacity:.55;border-left-color:#10b981}
.row.none{border-left-color:#6b7280}
.row-main{flex:1;min-width:0}
.row-title{font-size:15px;font-weight:600;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.status{font-size:11px;font-weight:400;border:1px solid;border-radius:4px;padding:1px 7px}
.row-what{font-size:13px;color:#9ca3af;margin-top:6px;word-break:break-word}
.row-meta{width:180px;text-align:right;flex-shrink:0}
.deadline{font-size:13px;font-weight:500}
.deadline.overdue{color:#f87171}
.deadline.today{color:#fbbf24}
.deadline.soon{color:#fbbf24}
.deadline.week{color:#93c5fd}
.deadline.later,.deadline.none{color:#6b7280}
.date-line{font-size:11px;color:#6b7280;margin-top:3px}
.tags{display:flex;gap:4px;justify-content:flex-end;flex-wrap:wrap;margin-top:6px}
.tag{font-size:10px;color:#9ca3af;background:#232730;border-radius:4px;padding:1px 6px}
.note{font-size:12px;color:#6b7280;margin-top:8px;border-top:1px dashed #2a2e37;padding-top:6px}
.empty{text-align:center;color:#6b7280;padding:48px 0;border:1px dashed #2a2e37;border-radius:10px}
.legend{margin-top:24px;font-size:11px;color:#6b7280;text-align:center}
@media(max-width:720px){.cards{grid-template-columns:repeat(2,1fr)}.row{flex-direction:column;gap:8px}.row-meta{width:auto;text-align:left}.tags{justify-content:flex-start}}
</style>
</head>
<body>
<div class="wrap">
<h1>事件追踪看板 <span style="font-size:14px;color:#9ca3af;font-weight:400">%(year)d 年</span></h1>
<div class="sub">截至 %(generated)s · 未完成优先，按紧急度排序</div>
<div class="cards">%(cards)s</div>
<div class="filters">%(tag_filters)s</div>
<div class="list" id="list">%(rows)s</div>
<div class="legend">点击上方卡片或标签筛选（可叠加，再点一次取消）· 红色=逾期 / 黄色=3天内 / 绿色=已完成</div>
</div>
<script>
var activeCard='';
var activeTag='';
function matchCard(row,key){
  if(!key)return true;
  var done=row.dataset.done==='1';
  var dl=row.dataset.dlclass;
  if(key==='pending')return !done;
  if(key==='overdue')return !done&&dl==='overdue';
  if(key==='soon')return !done&&(dl==='today'||dl==='soon');
  if(key==='done')return done;
  return true;
}
function apply(){
  document.querySelectorAll('.row').forEach(function(row){
    var tags=row.dataset.tags.split(',');
    var okTag=!activeTag||tags.indexOf(activeTag)>=0;
    row.style.display=(okTag&&matchCard(row,activeCard))?'':'none';
  });
}
document.querySelectorAll('.card').forEach(function(btn){
  btn.addEventListener('click',function(){
    activeCard=(activeCard===btn.dataset.filter)?'':btn.dataset.filter;
    document.querySelectorAll('.card').forEach(function(b){b.classList.remove('active')});
    if(activeCard)btn.classList.add('active');
    apply();
  });
});
document.querySelectorAll('.filter').forEach(function(btn){
  btn.addEventListener('click',function(){
    activeTag=(activeTag===btn.dataset.tag)?'':btn.dataset.tag;
    document.querySelectorAll('.filter').forEach(function(b){b.classList.remove('active')});
    if(activeTag)btn.classList.add('active');
    apply();
  });
});
</script>
</body>
</html>
""" % {
        "year": year or today.year,
        "generated": _esc(generated),
        "cards": card_html,
        "tag_filters": tag_filters,
        "rows": rows_html,
    }


def _md_cell(s):
    """转义 Markdown 表格单元格中的管道符与换行。"""
    return str(s or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def build_dashboard_md(events, today=None, year=None):
    """生成 Obsidian 原生可渲染的 Markdown 看板。统计与排序口径与 HTML 版一致。"""
    today = today or dt.date.today()
    items = []
    for e in events:
        rank, dl_label, dl_class = _deadline_status(e, today)
        status = e.get("status", "todo")
        done = status == "done"
        items.append({
            "event": e.get("event", ""),
            "what": e.get("what", ""),
            "when": e.get("when", ""),
            "deadline": e.get("deadline", ""),
            "status": status,
            "tags": e.get("tags", []),
            "note": e.get("note", ""),
            "dl_label": dl_label,
            "dl_class": dl_class,
            "_rank": 9 if done else rank,
            "_done": done,
        })
    # 与 HTML 版完全相同的排序：未完成优先，其次紧急度，再按截止日
    items.sort(key=lambda x: (x["_done"], x["_rank"], x["deadline"] or "9999", x["event"]))

    pending = [x for x in items if not x["_done"]]
    overdue = [x for x in pending if x["dl_class"] == "overdue"]
    due3 = [x for x in pending if x["dl_class"] in ("today", "soon")]
    done_items = [x for x in items if x["_done"]]
    generated = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")
    y = year or today.year

    urgency_icon = {
        "overdue": "🔴", "today": "🟠", "soon": "🟡",
        "week": "🔵", "later": "⚪", "none": "⚪",
    }

    def status_label(s):
        return STATUS_META.get(s, (s, ""))[0]

    lines = [
        "---",
        "type: event-dashboard",
        "year: %d" % y,
        'generated: "%s"' % generated,
        "total: %d" % len(items),
        "pending: %d" % len(pending),
        "overdue: %d" % len(overdue),
        "due_soon: %d" % len(due3),
        "done: %d" % len(done_items),
        "---",
        "",
        "# 事件追踪看板 · %d 年" % y,
        "",
        "> [!info] 概览",
        "> 待办 **%d** · 🔴 逾期 **%d** · 🟡 3天内截止 **%d** · ✅ 已完成 **%d**"
        % (len(pending), len(overdue), len(due3), len(done_items)),
        "> 截至 %s · 未完成优先，按紧急度排序" % generated,
        "",
        "## 待办（%d）" % len(pending),
        "",
    ]
    if pending:
        lines += [
            "| 紧急度 | 事件 | 状态 | 截止日 | 标签 | 记录日 | 说明 |",
            "|---|---|---|---|---|---|---|",
        ]
        for x in pending:
            lines.append("| %s %s | %s | %s | %s | %s | %s | %s |" % (
                urgency_icon.get(x["dl_class"], "⚪"), x["dl_label"],
                _md_cell(x["event"]), status_label(x["status"]),
                _md_cell(x["deadline"] or "—"),
                _md_cell(", ".join(x["tags"]) or "—"),
                _md_cell(x["when"]), _md_cell(x["note"] or x["what"])))
    else:
        lines.append("_暂无待办事项。_")

    lines += ["", "## 已完成（%d）" % len(done_items), ""]
    if done_items:
        lines += [
            "| 事件 | 截止日 | 标签 | 记录日 | 说明 |",
            "|---|---|---|---|---|",
        ]
        for x in done_items:
            lines.append("| %s | %s | %s | %s | %s |" % (
                _md_cell(x["event"]), _md_cell(x["deadline"] or "—"),
                _md_cell(", ".join(x["tags"]) or "—"),
                _md_cell(x["when"]), _md_cell(x["what"] or x["note"])))
    else:
        lines.append("_暂无已完成事项。_")

    lines += [
        "",
        "---",
        "由 event-tracker 生成，数据源：`events.jsonl`。更新数据后重跑 `web` 命令刷新。",
        "",
    ]
    return "\n".join(lines)
