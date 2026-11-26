#!/usr/bin/env python3
"""Event Tracker (事件追踪) - 事件日记 CLI。零第三方依赖，标准库实现。"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

STATUS_SET = {"todo", "doing", "done", "blocked"}
SUMMARY_MARK = "<!-- EVENT_TRACKER_SUMMARY -->"


def eprint(msg):
    print(msg, file=sys.stderr)


def fail(msg, code=2):
    eprint("错误: " + msg)
    raise SystemExit(code)


def resolve_vault(explicit=None):
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_dir():
            fail("--vault 指向的目录不存在: " + str(p))
        return p
    candidates = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "obsidian" / "obsidian.json")
    candidates.append(Path.home() / "Library/Application Support/obsidian/obsidian.json")
    for cfg in candidates:
        if not cfg.is_file():
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            vaults = data.get("vaults", {})
            opened = [v for v in vaults.values() if v.get("open")]
            if opened:
                p = Path(opened[0]["path"])
                if p.is_dir():
                    return p
        except (ValueError, OSError, KeyError, TypeError):
            continue
    fail("未能自动探测 Obsidian vault；请用 --vault 指定路径")


def data_dir(vault):
    return Path(vault) / "日记" / "DSH"


def events_path(vault):
    return data_dir(vault) / "events.jsonl"


def reviews_dir(vault):
    return data_dir(vault) / "reviews"


def load_events(vault):
    p = events_path(vault)
    if not p.is_file():
        return []
    rows = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            eprint("警告: 跳过损坏行 %s:%d" % (p, n))
    return rows


def latest_events(rows):
    """按 id 折叠为最新版本，保持首次出现顺序；无 id 行原样保留。"""
    order = []
    by_id = {}
    others = []
    for e in rows:
        eid = e.get("id")
        if not eid:
            others.append(e)
            continue
        if eid not in by_id:
            order.append(eid)
        by_id[eid] = e  # 同一 id 后出现的覆盖先出现的
    return [by_id[i] for i in order] + others


def next_event_id(events, day_str):
    prefix = "E" + day_str.replace("-", "") + "-"
    mx = 0
    for e in events:
        eid = str(e.get("id", ""))
        if eid.startswith(prefix):
            try:
                mx = max(mx, int(eid[len(prefix):]))
            except ValueError:
                pass
    return prefix + "%03d" % (mx + 1)


def parse_day(value, label):
    try:
        return dt.date.fromisoformat(value)
    except (ValueError, TypeError):
        fail("%s 需为 YYYY-MM-DD，收到: %r" % (label, value))


def parse_done_at(value):
    """接受 YYYY-MM-DD 或 ISO8601 时间戳，返回带时区的 ISO 字符串。"""
    if not value:
        return None
    tz = dt.datetime.now().astimezone().tzinfo
    try:
        day = dt.date.fromisoformat(value)
        return dt.datetime.combine(day, dt.time.min, tzinfo=tz).isoformat(timespec="seconds")
    except ValueError:
        pass
    try:
        stamp = dt.datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=tz)
        return stamp.isoformat(timespec="seconds")
    except ValueError:
        fail("--done-at 需为 YYYY-MM-DD 或 ISO8601 时间戳，收到: %r" % value)


def iso_week_label(day):
    year, week, _ = day.isocalendar()
    return "%d-W%02d" % (year, week)


def week_range(day):
    monday = day - dt.timedelta(days=day.weekday())
    return monday, monday + dt.timedelta(days=6)


def month_label(day):
    return day.strftime("%Y-%m")


def event_day(e):
    try:
        return dt.date.fromisoformat(e["when"])
    except (ValueError, TypeError, KeyError):
        return None


def cmd_config_check(args):
    vault = resolve_vault(args.vault)
    print("vault:    " + str(vault))
    print("data dir: " + str(data_dir(vault)))
    print("events:   %d 条" % len(load_events(vault)))
    print("reviews:  " + str(reviews_dir(vault)))


def cmd_log(args):
    vault = resolve_vault(args.vault)
    day = parse_day(args.when, "--when") if args.when else dt.date.today()
    if args.deadline:
        parse_day(args.deadline, "--deadline")
    if args.status not in STATUS_SET:
        fail("--status 必须是 %s 之一" % ", ".join(sorted(STATUS_SET)))
    d = data_dir(vault)
    d.mkdir(parents=True, exist_ok=True)
    events = latest_events(load_events(vault))
    now = dt.datetime.now().astimezone()
    tags = [t.strip() for t in args.tag.split(",") if t.strip()] if args.tag else []
    rec = {
        "id": next_event_id(events, day.isoformat()),
        "ts": now.isoformat(timespec="seconds"),
        "event": args.event.strip(),
        "what": args.what.strip(),
        "when": day.isoformat(),
        "deadline": args.deadline or "",
        "status": args.status,
        "tags": tags,
        "note": args.note or "",
        "done_at": (parse_done_at(args.done_at) or now.isoformat(timespec="seconds"))
                   if args.status == "done" else "",
    }
    with events_path(vault).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("已记录 %s [%s] %s" % (rec["id"], rec["when"], rec["event"]))
    print("  what:     " + rec["what"])
    if rec["deadline"]:
        print("  deadline: " + rec["deadline"])
    print("  status:   " + rec["status"])


def cmd_update(args):
    vault = resolve_vault(args.vault)
    rows = load_events(vault)
    current = {e.get("id"): e for e in rows if e.get("id")}
    if args.id not in current:
        fail("未找到事件 id: %s" % args.id)
    base = current[args.id]
    updated = dict(base)  # 复制最新版本全部字段

    if args.status:
        if args.status not in STATUS_SET:
            fail("--status 必须是 %s 之一" % ", ".join(sorted(STATUS_SET)))
        updated["status"] = args.status
    if args.what:
        updated["what"] = args.what.strip()
    if args.when:
        updated["when"] = parse_day(args.when, "--when").isoformat()
    if args.deadline is not None:
        if args.deadline:
            parse_day(args.deadline, "--deadline")
        updated["deadline"] = args.deadline
    if args.tag is not None:
        updated["tags"] = [t.strip() for t in args.tag.split(",") if t.strip()] if args.tag else []
    if args.note is not None:
        updated["note"] = args.note

    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    updated["ts"] = now
    if args.done_at:
        updated["done_at"] = parse_done_at(args.done_at)
    elif updated["status"] == "done" and not updated.get("done_at"):
        updated["done_at"] = now
    elif updated["status"] != "done":
        updated["done_at"] = ""

    with events_path(vault).open("a", encoding="utf-8") as f:
        f.write(json.dumps(updated, ensure_ascii=False) + "\n")
    print("已更新 %s → [%s] %s" % (args.id, updated["status"], updated["event"]))
    for k in ("what", "deadline", "tags", "note"):
        if updated.get(k) != base.get(k):
            print("  %s: %s → %s" % (k, base.get(k, ""), updated.get(k, "")))
    if updated.get("done_at") and not base.get("done_at"):
        print("  完成时间: " + updated["done_at"])


def cmd_list(args):
    vault = resolve_vault(args.vault)
    rows = latest_events(load_events(vault))
    if args.date:
        target = parse_day(args.date, "--date")
        rows = [e for e in rows if event_day(e) == target]
    if args.from_date:
        lo = parse_day(args.from_date, "--from")
        rows = [e for e in rows if event_day(e) and event_day(e) >= lo]
    if args.to_date:
        hi = parse_day(args.to_date, "--to")
        rows = [e for e in rows if event_day(e) and event_day(e) <= hi]
    if args.status:
        rows = [e for e in rows if e.get("status") == args.status]
    if args.tag:
        wanted = {t.strip() for t in args.tag.split(",") if t.strip()}
        rows = [e for e in rows if wanted & set(e.get("tags", []))]
    if args.due is not None:
        today = dt.date.today()
        kept = []
        for e in rows:
            if e.get("status") == "done" or not e.get("deadline"):
                continue
            try:
                delta = (dt.date.fromisoformat(e["deadline"]) - today).days
            except (ValueError, TypeError):
                continue
            if delta <= args.due:  # 负数=已逾期，含在结果中
                kept.append(e)
        rows = kept
    rows.sort(key=lambda e: (e.get("deadline", "9999") or "9999", e.get("when", "")))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("无匹配事件")
        return
    for e in rows:
        dl = (" | 截止 " + e["deadline"]) if e.get("deadline") else ""
        tags = (" | #" + " #".join(e.get("tags", []))) if e.get("tags") else ""
        print("%s [%s] %s — %s ( %s )%s%s" % (
            e["id"], e.get("when", "?"), e.get("event", ""),
            e.get("what", ""), e.get("status", "?"), dl, tags))


def write_review(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(str(tmp), str(path))
    return path


def stat_lines(rows, today=None):
    today = today or dt.date.today()
    by_status = {}
    by_tag = {}
    done_with_dl = 0   # 有截止日的已完成任务
    on_time = 0        # 其中按时完成
    durations = []     # 完成耗时（天）
    overdue_open = 0   # 未完成且已逾期
    soon_open = 0      # 未完成且 7 天内到期
    for e in rows:
        st = e.get("status", "?")
        by_status[st] = by_status.get(st, 0) + 1
        for t in e.get("tags", []):
            by_tag[t] = by_tag.get(t, 0) + 1

        dl = e.get("deadline", "")
        if st == "done":
            done_at = e.get("done_at", "")
            if done_at:
                try:
                    dd = dt.date.fromisoformat(done_at[:10])
                    when = event_day(e)
                    if when:
                        durations.append((dd - when).days)
                except (ValueError, TypeError):
                    pass
            if dl and done_at:
                done_with_dl += 1
                try:
                    if dt.date.fromisoformat(done_at[:10]) <= dt.date.fromisoformat(dl):
                        on_time += 1
                except (ValueError, TypeError):
                    pass
        elif dl:
            try:
                delta = (dt.date.fromisoformat(dl) - today).days
                if delta < 0:
                    overdue_open += 1
                elif delta <= 7:
                    soon_open += 1
            except (ValueError, TypeError):
                pass

    out = ["## 统计", ""]
    out.append("- 事件总数: %d" % len(rows))
    out.append("- 状态分布: " + ("、".join("%s %d" % (k, v) for k, v in sorted(by_status.items())) or "无"))
    out.append("- 标签分类: " + ("、".join("%s %d" % (k, v) for k, v in sorted(by_tag.items())) or "无"))
    if done_with_dl:
        out.append("- 按时完成率: %d/%d（%.0f%%）" % (on_time, done_with_dl, 100.0 * on_time / done_with_dl))
    else:
        out.append("- 按时完成率: 无数据（已完成任务需带截止日与完成时间）")
    if durations:
        out.append("- 平均完成耗时: %.1f 天（样本 %d）" % (sum(durations) / len(durations), len(durations)))
    out.append("- 未完成逾期: %d 项 | 7 天内到期: %d 项" % (overdue_open, soon_open))
    return "\n".join(out)


def detail_lines(rows):
    out = ["## 事件明细", ""]
    if not rows:
        out.append("本期无事件记录。")
        return "\n".join(out)
    for e in rows:
        dl = ("；截止 " + e["deadline"]) if e.get("deadline") else ""
        tags = ("；#" + " #".join(e.get("tags", []))) if e.get("tags") else ""
        out.append("- [%s][%s] **%s**：%s%s%s" % (
            e.get("when", "?"), e.get("status", "?"), e.get("event", ""),
            e.get("what", ""), dl, tags))
        if e.get("note"):
            out.append("  - 备注: " + e["note"])
    return "\n".join(out)


def due_lines(rows, today=None):
    """逾期与临期事项明细，供我归纳时直接引用，不再肉眼扫描。"""
    today = today or dt.date.today()
    out = ["## 逾期与临期", ""]
    overdue, soon = [], []
    for e in rows:
        if e.get("status") == "done":
            continue
        dl = e.get("deadline", "")
        if not dl:
            continue
        try:
            delta = (dt.date.fromisoformat(dl) - today).days
        except (ValueError, TypeError):
            continue
        if delta < 0:
            overdue.append((e, -delta))
        elif delta <= 7:
            soon.append((e, delta))
    if not overdue and not soon:
        out.append("本期无逾期或 7 天内到期事项。")
        return "\n".join(out)
    if overdue:
        out.append("### 已逾期")
        for e, days in sorted(overdue, key=lambda x: -x[1]):
            out.append("- 逾期 %d 天 · [%s] **%s**（截止 %s）" % (
                days, e.get("status", "?"), e.get("event", ""), e["deadline"]))
        out.append("")
    if soon:
        out.append("### 7 天内到期")
        for e, days in sorted(soon, key=lambda x: x[1]):
            label = "今天截止" if days == 0 else "%d 天后" % days
            out.append("- %s · [%s] **%s**（截止 %s）" % (
                label, e.get("status", "?"), e.get("event", ""), e["deadline"]))
    return "\n".join(out)


def build_review(title, basis_line, rows, today=None):
    today = today or dt.date.today()
    return "\n".join([
        "# " + title, "",
        "> " + basis_line,
        "> 生成时间: " + dt.datetime.now().astimezone().isoformat(timespec="seconds"), "",
        stat_lines(rows, today), "",
        due_lines(rows, today), "",
        detail_lines(rows), "",
        "## 归纳", "",
        SUMMARY_MARK,
        "（由助手依据上方事件明细填写：按主题聚合进展、参考逾期与临期区块、给出下一步建议；不得虚构未记录的事实）",
    ]) + "\n"


def cmd_weekly(args):
    vault = resolve_vault(args.vault)
    basis = parse_day(args.date, "--date") if args.date else dt.date.today()
    lo, hi = week_range(basis)
    label = iso_week_label(basis)
    rows = [e for e in latest_events(load_events(vault))
            if event_day(e) and lo <= event_day(e) <= hi]
    rows.sort(key=lambda e: (e.get("when", ""), e.get("ts", "")))
    basis_line = "覆盖区间: %s ~ %s" % (lo.isoformat(), hi.isoformat())
    path = write_review(reviews_dir(vault) / (label + ".md"),
                        build_review("周梳理 " + label, basis_line, rows))
    print("已生成周梳理骨架: %s（%d 条事件）" % (path, len(rows)))
    print("下一步: 助手读取该文件，用归纳内容替换 %s" % SUMMARY_MARK)


def cmd_monthly(args):
    vault = resolve_vault(args.vault)
    if args.month:
        try:
            basis = dt.date.fromisoformat(args.month + "-01")
        except ValueError:
            fail("--month 需为 YYYY-MM，收到: %r" % args.month)
    else:
        basis = dt.date.today().replace(day=1)
    label = month_label(basis)
    rows = [e for e in latest_events(load_events(vault))
            if event_day(e) and event_day(e).strftime("%Y-%m") == label]
    rows.sort(key=lambda e: (e.get("when", ""), e.get("ts", "")))
    path = write_review(reviews_dir(vault) / (label + ".md"),
                        build_review("月梳理 " + label, "覆盖区间: " + label, rows))
    print("已生成月梳理骨架: %s（%d 条事件）" % (path, len(rows)))
    print("下一步: 助手读取该文件，用归纳内容替换 %s" % SUMMARY_MARK)


def cmd_web(args):
    vault = resolve_vault(args.vault)
    rows = latest_events(load_events(vault))
    year = args.year if args.year else dt.date.today().year
    total = len(rows)
    rows = [e for e in rows if event_day(e) and event_day(e).year == year]
    from dashboard import build_dashboard, build_dashboard_md
    out = Path(args.out).expanduser() if args.out else (data_dir(vault) / "dashboard.html")
    if out.suffix.lower() != ".html":
        out = out.with_suffix(".html")
    md_out = out.with_suffix(".md")

    for target, content in ((out, build_dashboard(rows, year=year)),
                            (md_out, build_dashboard_md(rows, year=year))):
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(str(tmp), str(target))

    print("已生成 HTML 看板: %s（%d 条事件，%d 年）" % (out, len(rows), year))
    print("已生成 MD 看板:   %s（Obsidian 可直接打开）" % md_out)
    if total != len(rows):
        print("已过滤 %d 条非 %d 年事件（可用 --year 查看其他年份）" % (total - len(rows), year))
    print("更新数据后重跑本命令刷新两份看板。")


def cmd_backup(args):
    import zipfile
    vault = resolve_vault(args.vault)
    skill_dir = Path(__file__).resolve().parent.parent
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    default_out = Path.home() / ("event-tracker-backup-%s.zip" % stamp)
    out = Path(args.out).expanduser() if args.out else default_out
    out.parent.mkdir(parents=True, exist_ok=True)

    restore_note = (
        "事件追踪 (Event Tracker) 备份包\n"
        "生成时间: %s\n"
        "vault 路径: %s\n\n"
        "恢复步骤:\n"
        "1. 将 skill/ 整个文件夹复制到新电脑的 ~/.dsh/skills/event-tracker/\n"
        "2. 将 data/ 内的全部内容复制到 Obsidian vault 的 日记/DSH/ 目录\n"
        "3. 在 Obsidian 中打开该 vault（技能会自动探测，无需改配置）\n"
        "4. 新电脑需 Python 3.8+，运行 python scripts/event_tracker.py config-check 验证\n\n"
        "注: events.jsonl 为事件流水；reviews/ 为周月报告；dashboard.html 与 dashboard.md 为看板（均可重新生成）。\n"
        % (dt.datetime.now().astimezone().isoformat(timespec="seconds"), vault)
    )

    skill_files = sorted(p for p in skill_dir.rglob("*")
                         if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    data_root = data_dir(vault)
    data_files = sorted(p for p in data_root.rglob("*") if p.is_file()) if data_root.is_dir() else []

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("RESTORE.txt", restore_note)
        for p in skill_files:
            z.write(p, "skill/" + str(p.relative_to(skill_dir)).replace("\\", "/"))
        for p in data_files:
            z.write(p, "data/" + str(p.relative_to(data_root)).replace("\\", "/"))

    print("已生成备份: %s" % out)
    print("  技能文件: %d 个 | 数据文件: %d 个" % (len(skill_files), len(data_files)))
    print("  包大小: %d bytes" % out.stat().st_size)


def build_parser():
    p = argparse.ArgumentParser(prog="event-tracker", description="事件追踪：记录、查询、周/月梳理")
    p.add_argument("--vault", help="显式指定 vault 路径（默认自动探测）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("config-check", help="检查 vault 与数据配置").set_defaults(fn=cmd_config_check)

    log = sub.add_parser("log", help="记录一条事件")
    log.add_argument("--event", required=True, help="事件名")
    log.add_argument("--what", required=True, help="做了什么/进展")
    log.add_argument("--when", help="发生日 YYYY-MM-DD，默认今天")
    log.add_argument("--deadline", help="截止日 YYYY-MM-DD")
    log.add_argument("--status", default="doing", help="todo/doing/done/blocked")
    log.add_argument("--tag", help="逗号分隔标签")
    log.add_argument("--note", default="", help="补充说明")
    log.add_argument("--done-at", help="完成时间 YYYY-MM-DD，默认done时为当前时刻")
    log.set_defaults(fn=cmd_log)

    upd = sub.add_parser("update", help="更新事件进展（追加新版本，保留历史）")
    upd.add_argument("id", help="事件 id，如 E20261123-001")
    upd.add_argument("--status", help="新状态 todo/doing/done/blocked")
    upd.add_argument("--what", help="新进展描述")
    upd.add_argument("--when", help="新发生日 YYYY-MM-DD")
    upd.add_argument("--deadline", help="新截止日 YYYY-MM-DD；传空字符串清空")
    upd.add_argument("--tag", help="新标签（逗号分隔）；传空字符串清空")
    upd.add_argument("--note", help="新备注；传空字符串清空")
    upd.add_argument("--done-at", help="完成时间 YYYY-MM-DD，可修正补记任务的真实完成日")
    upd.set_defaults(fn=cmd_update)

    lst = sub.add_parser("list", help="查询事件")
    lst.add_argument("--date", help="精确日期")
    lst.add_argument("--from", dest="from_date", help="起始日期")
    lst.add_argument("--to", dest="to_date", help="结束日期")
    lst.add_argument("--status", help="按状态筛选")
    lst.add_argument("--tag", help="按标签筛选（逗号分隔）")
    lst.add_argument("--due", type=int, metavar="N", help="N 天内到期或已逾期的未完成任务")
    lst.add_argument("--json", action="store_true", help="JSON 输出")
    lst.set_defaults(fn=cmd_list)

    wk = sub.add_parser("weekly", help="生成周梳理骨架")
    wk.add_argument("--date", help="基准日期，默认今天")
    wk.set_defaults(fn=cmd_weekly)

    mo = sub.add_parser("monthly", help="生成月梳理骨架")
    mo.add_argument("--month", help="YYYY-MM，默认当月")
    mo.set_defaults(fn=cmd_monthly)

    web = sub.add_parser("web", help="生成静态 HTML 看板")
    web.add_argument("--out", help="输出路径，默认 <vault>/日记/DSH/dashboard.html")
    web.add_argument("--year", type=int, help="只显示指定年份事件，默认当年")
    web.set_defaults(fn=cmd_web)

    bk = sub.add_parser("backup", help="打包技能与数据为 zip 备份")
    bk.add_argument("--out", help="输出 zip 路径，默认 ~/event-tracker-backup-<时间戳>.zip")
    bk.set_defaults(fn=cmd_backup)

    return p


def main():
    args = build_parser().parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
