---
name: event-tracker
description: "记录事件进展，周月归纳，生成看板。触发词：事件追踪、Event Tracker、记录事件、周梳理、看板、生成看板。"
description_zh: "事件追踪：事件日记、周月归纳与看板"
description_en: "Event Tracker: event journaling, reviews and dashboard"
version: 0.5.0
metadata: {"clawdbot": {"emoji": "📋"}}
display_name: "事件追踪"
display_name_en: "Event Tracker"
icon: "icon.svg"
visibility: "public"
---

# 事件追踪 (Event Tracker) — 事件日记、周/月归纳与看板

把口述的事件进展变成可检索的结构化流水，按周/月归纳成报告，并生成一眼看清待办与截止日的可视化看板。数据落在 Obsidian vault 的 `日记/DSH/`，**不改动现有日记正文**。归纳由助手在对话中直接完成，不需要任何外部 API、密钥或第三方依赖。

四项能力互为补充：`log` 沉淀数据，`list` 精确检索，`weekly`/`monthly` 做周期性回顾，`web` 提供日常快速总览。

## 何时使用

- **记录**：用户描述一件正在推进的事（如"今天把主板换了，下周三前要装好系统"），含事件名、做了什么、时间、截止时间四要素
- **更新**：用户说"那件事做完了""截止日改到下周""被卡住了"——用 `update` 追加新版本，不覆盖历史
- **查询**：用户问"之前那件事什么时候截止""某天记了什么""哪些快到期了"（`list --due 7`）
- **周/月梳理**：用户说"这周梳理一下""周总结""这个月做了什么"——生成报告骨架并由助手回填归纳
- **看板**：用户说"生成看板""看看还有什么没做"——产出 HTML 与 Markdown 双份看板

## 环境前提

- Python 3.8+（本机实测 3.13.7）
- 零第三方依赖、零密钥、零网络调用

## 数据位置（自动探测，禁止硬编码）

```bash
python scripts/event_tracker.py config-check        # 查看实际 vault 路径、事件数
```

vault 来源优先级：`--vault` 参数 > `%APPDATA%/obsidian/obsidian.json` 中 `open:true` 的条目。

数据目录固定为 vault 下的 `日记/DSH/`（目录名沿用历史值 `DSH`，与技能标识解耦，改名不迁移既有数据）：
- `events.jsonl` — 事件流水（append-only，一行一事件）
- `reviews/YYYY-Www.md` — 周梳理
- `reviews/YYYY-MM.md` — 月梳理

## 工作流

### 1. 记录事件

用户口述后，抽取字段并调用：

```bash
python scripts/event_tracker.py log \
  --event "更换主板" \
  --what "B560M 已装机，待验证内存通道" \
  --when "2026-11-23" \
  --deadline "2026-11-26" \
  --status doing \
  --tag "硬件,电竞房"
```

字段抽取规则见 `references/conventions.md`。必填：`--event`、`--what`；其余可省略（`--when` 默认今天）。记录后回显 ID 与关键字段供用户确认。

### 2. 更新进展

事情状态会变化（doing→done、截止日调整、受阻解除）。用 `update` 追加新版本，**不改写历史**：

```bash
python scripts/event_tracker.py update E20261123-001 --status done --what "装好了，双通道已验证"
python scripts/event_tracker.py update E20261123-001 --deadline 2026-11-30 --tag "硬件,电竞房"
python scripts/event_tracker.py update E20261123-001 --status done --done-at 2026-11-25  # 补记真实完成日
```

- `--deadline` / `--tag` / `--note` 传空字符串表示清空；未提供的字段保持不变
- `status` 转 `done` 时自动写完成时间；**补记过去完成的事项必须带 `--done-at`**，否则按时完成率会被低估
- 读取时按 `id` 折叠取最新版本，历史版本始终留在 JSONL 中可追溯

### 3. 查询

```bash
python scripts/event_tracker.py list --date 2026-11-23        # 某天
python scripts/event_tracker.py list --from 2026-11-01 --to 2026-11-30
python scripts/event_tracker.py list --status doing --tag 硬件
python scripts/event_tracker.py list --due 7                  # 逾期 + 未来7天内到期
python scripts/event_tracker.py list --json                   # 结构化输出，便于二次处理
```

查询结果按截止日升序（无截止排末尾），便于先看最紧急的。

### 4. 周/月梳理（两步）

**第一步 — 生成骨架**（脚本只做筛选与统计，不生成归纳）：

```bash
python scripts/event_tracker.py weekly --date 2026-11-23      # 该日期所在 ISO 周
python scripts/event_tracker.py monthly --month 2026-11
```

**第二步 — 填写归纳**（必须由助手完成，不可留给占位符）：

1. 读取上一步输出的报告文件（路径在命令回显中）
2. 依据「统计」「逾期与临期」「事件明细」撰写归纳正文，要求：
   - 按主题聚合进展，不逐条罗列
   - 直接引用报告中的「逾期与临期」区块，点名具体事项与逾期天数
   - 参考按时完成率与平均耗时评估执行效率
   - 给出下一步建议
   - 严禁虚构事件明细之外的事实
3. 用归纳正文替换文件中的 `<!-- EVENT_TRACKER_SUMMARY -->` 标记行
4. 向用户回显报告路径与 2-3 条要点

覆盖已有报告前脚本自动写 `.bak`；无事件时生成占位报告而非报错。

### 5. 看板（web）

一次生成两份看板，直观展示未完成任务、截止日期与紧急度：
- `dashboard.html` — 自包含静态 HTML，浏览器打开，支持点击筛选
- `dashboard.md` — Obsidian 原生 Markdown，可直接在 vault 中打开查看

```bash
python scripts/event_tracker.py web                          # 默认输出到 <vault>/日记/DSH/dashboard.*
python scripts/event_tracker.py web --out "E:/path/看板.html"  # 自定义路径（.md 自动生成在同目录）
python scripts/event_tracker.py web --year 2025               # 查看指定年份（默认当年）
```

看板特性：
- 只显示当年事件（按 `when` 字段年份过滤），标题标注年份；`--year` 可查看其他年份
- 未完成优先，按紧急度排序：逾期 → 今天截止 → 3天内 → 7天内 → 无截止 → 已完成
- HTML 版：顶部统计卡片可点击筛选（再点一次取消，可与标签筛选叠加），逾期红色、临近黄色、已完成半透明
- Markdown 版：YAML frontmatter 含统计字段（可被 Dataview 查询），概览 callout + 待办表 + 已完成表，逾期 🔴 / 临期 🟠🟡
- 两份看板统计口径与排序完全一致；零依赖、纯静态，数据更新后重跑命令刷新

### 6. 备份（backup）

打包技能文件与事件数据，用于换电脑迁移：

```bash
python scripts/event_tracker.py backup                       # 默认输出到 ~/event-tracker-backup-<时间戳>.zip
python scripts/event_tracker.py backup --out "E:/backup.zip"  # 自定义路径
```

zip 内分 `skill/`（技能全部文件）与 `data/`（事件流水、报告、看板）两区，附 `RESTORE.txt` 恢复说明。换电脑时解压后按说明放回对应位置即可。

## 交互约定

- 记录后回显事件 ID 与关键字段，让用户确认
- 梳理后回显报告路径与事件数，并摘要要点
- 归纳必须回填到报告文件，不得只口头输出
- 不主动修改用户现有日记 `.md` 文件

## 已知限制

- 归纳质量取决于事件明细的完整度；记录时字段越具体，梳理价值越高
- 报告骨架由脚本生成，归纳部分需助手在对话中完成
- 无 `category` / `amount` 字段：买东西、看书、看电视等场景只能用 `tags` + `note` 记录，无法统计金额、页数或时长
- 按时完成率依赖 `done_at`；补记的历史完成事项若未指定 `--done-at`，会被视为当日完成
