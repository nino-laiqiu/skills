# skills

个人 DeepSeek Harness (DSH) 技能集合。

## 技能列表

| 技能 | 说明 |
| --- | --- |
| `event-tracker` | 记录事件进展、周/月归纳、生成看板。触发词：事件追踪、Event Tracker、记录事件、周梳理、看板。 |

## 安装

将需要的技能目录复制到 DSH 的扫描根之一：

- 项目级：`<项目根>/.dsh/skills/`
- 项目级（兼容）：`<项目根>/.agents/skills/`
- 用户级：`~/.dsh/skills/`（Windows 默认 `C:\Users\<用户名>\.dsh\skills`）

每个技能是独立目录，入口为 `SKILL.md`（同名 `.md` 单文件也支持）。复制后新建会话即可使用；DSH 会监听目录变化。

## 目录约定

- 每个技能一个顶级目录，入口为 `SKILL.md`
- 技能数据（如 `event-tracker` 的 `events.jsonl`、`reviews/`、看板）保存在用户 vault 中，不纳入本仓库
- `scripts/` 内的 Python 脚本依赖 Python 3.13

## 许可

私有仓库，保留所有权利。
