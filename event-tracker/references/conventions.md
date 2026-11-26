# 事件追踪 (Event Tracker) 数据约定与字段抽取规则

## events.jsonl 记录结构

一行一个 JSON 对象，UTF-8，字段固定如下：

```json
{
  "id": "E20261123-001",
  "ts": "2026-11-23T22:40:00+08:00",
  "event": "更换主板",
  "what": "B560M 已装机，待验证内存通道",
  "when": "2026-11-23",
  "deadline": "2026-11-26",
  "status": "doing",
  "tags": ["硬件", "电竞房"],
  "note": "",
  "done_at": ""
}
```

**版本机制**：`update <id>` 不改写原行，而是追加一条同 `id`、新 `ts` 的记录。读取层 `latest_events()` 按 `id` 折叠、取最后版本，保持首次出现顺序。因此历史版本始终保留在 JSONL 中，可追溯。`next_event_id` 也基于折叠视图计算，避免历史版本干扰序号。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| id | str | 是 | `E` + 记录日期 + `-` + 当日三位序号 |
| ts | str | 是 | 记录写入时刻，ISO8601 带时区 |
| event | str | 是 | 事件名（"什么事件"） |
| what | str | 是 | 做了什么 / 进展（"我做什么"） |
| when | str | 是 | 事件发生日 `YYYY-MM-DD`（"什么时候"） |
| deadline | str | 否 | 必须完成日 `YYYY-MM-DD`（"什么时候必须完成"） |
| status | str | 是 | `todo` / `doing` / `done` / `blocked` |
| tags | array | 否 | 标签数组 |
| note | str | 否 | 补充说明 |
| done_at | str | 否 | 完成时间 ISO8601；`status=done` 时写入，可由 `--done-at` 指定真实完成日 |

## 口述 → 字段抽取

从用户自然语言中定位四类信息：

1. **事件名**：名词性主体，如"主板更换""公务员报名"。无明确事件名时，用动作概括（"处理电费"）。
2. **做了什么**：动词短语 + 结果状态。若用户只说计划未说进展，`what` 填计划内容，`status=todo`。
3. **什么时候**：优先取显式日期（"今天""11月23日""下周三"）；无则默认今天。相对日期按当前日期换算。
4. **什么时候必须完成**：含"截止""最迟""之前要""deadline"等信号词时提取；无则留空。

### 状态判定

| 语义 | status |
| --- | --- |
| 已完成 / 搞定了 / 结束了 | `done` |
| 正在进行 / 做到一半 / 待验证 | `doing` |
| 计划 / 打算 / 准备做 | `todo` |
| 卡住了 / 受阻 / 等别人 | `blocked` |

### 抽取示例

> "昨天把水冷换了，但螺丝拧不上，这周之内必须搞定"

```json
{"event":"更换水冷","what":"水冷已换，散热器螺丝拧不上受阻","when":"<昨天日期>","deadline":"<本周日日期>","status":"blocked","tags":["硬件"]}
```

## update 命令约定

`update <id> [--status] [--what] [--when] [--deadline] [--tag] [--note] [--done-at]`

- 仅更新指定字段，其余继承最新版本；未提供的字段保持不变
- `--deadline` / `--tag` / `--note` 传空字符串表示清空
- `status` 转为 `done` 且无 `done_at` 时自动写入当前时刻；补记历史完成事项用 `--done-at YYYY-MM-DD` 指定真实完成日，避免按时完成率失真
- `status` 从 `done` 转回其他状态时清空 `done_at`

## 归纳报告结构

周/月报告骨架包含：本期范围、事件总数、状态分布、标签分类、按时完成率、平均完成耗时、未完成逾期与临期计数、**逾期与临期明细区块**、事件明细、归纳占位标记 `<!-- EVENT_TRACKER_SUMMARY -->`、生成时间。

统计口径：
- 按时完成率 = 有截止日且有 `done_at` 的已完成任务中，`done_at` 日期 ≤ `deadline` 的比例；无样本时标注「无数据」
- 平均完成耗时 = `done_at` 日期 − `when` 日期的均值（天）
- 逾期/临期判定基于报告生成日，仅统计 `status != done` 且带截止日的事件

归纳正文由助手填写并替换占位标记，要求：按主题聚合进展、直接引用「逾期与临期」区块、给出下一步建议，不虚构事件明细之外的事实。

## 看板（dashboard.html + dashboard.md）

`web` 命令基于 `events.jsonl` 同时生成两份看板，输出到 `日记/DSH/`（可用 `--out` 覆盖基准路径，`.md` 自动生成在同目录）：
- `dashboard.html` — 自包含静态 HTML，供浏览器打开，支持卡片与标签点击筛选
- `dashboard.md` — Obsidian 原生 Markdown，可直接作为笔记打开

数据与渲染逻辑分离：`scripts/dashboard.py` 提供 `build_dashboard`（HTML）与 `build_dashboard_md`（Markdown）两个生成器，`event_tracker.py` 负责命令调度。两者复用 `_deadline_status` 判定与相同排序口径。

紧急度判定（以生成当天为基准，按 `deadline` 计算）：逾期（<0 天）> 今天截止 > 3 天内 > 7 天内 > 无截止；已完成项固定排末尾。看板仅作展示，不回写事件数据。

Markdown 版约定：
- YAML frontmatter 字段：`type: event-dashboard`、`year`、`generated`、`total`、`pending`、`overdue`、`due_soon`、`done`（供 Dataview 查询，满足 `total = pending + done`）
- 正文含 `[!info]` 概览 callout、待办表（紧急度/事件/状态/截止日/标签/记录日/说明）、已完成表
- 表格单元格中的 `|` 转义为 `\|`，换行压平为空格；无数据时输出占位提示而非空表
- 紧急度图标：🔴逾期 / 🟠今天 / 🟡3天内 / 🔵7天内 / ⚪无截止或更远
