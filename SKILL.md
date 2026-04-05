---
name: dida365
description: |
  滴答清单/TickTick 任务管理工具——创建、查看、完成、删除任务和清单项目。
  触发词：创建任务、添加待办、今日任务、查看清单、完成任务、滴答清单、TickTick、
  TODO、待办事项、任务管理、项目管理、标记完成、删除任务、设置截止日期、
  任务优先级、新建清单、收集箱、inbox、未来几天任务、本周任务、已完成任务
license: MIT
compatibility:
  - Claude Code
  - Gemini CLI
  - OpenClaw
  - Cursor
  - 其他 Agent Skills 兼容工具
metadata:
  author: fanxing / woodcoal
  version: 3.1.0
  tags: [task-management, productivity, todo, api-tool]
allowed-tools: Bash(python:cli/index.py)
---

# 滴答清单 (Dida365) 任务管理

通过命令行接口管理滴答清单/TickTick 的任务和项目。

## 首次使用

1. **创建应用**：前往 https://developer.dida365.com/manage 创建应用，设置回调 URL 为 `http://localhost:18365/callback`
2. **配置凭据**：在 `.env` 中填写 `DIDA_CLIENT_ID` 和 `DIDA_CLIENT_SECRET`
3. **完成授权**：运行 `python cli/index.py auth` 并在浏览器完成操作

## 命令格式

```
python cli/index.py <分类> <子命令> [参数]
```

**重要**：

- 命令各部分之间必须用空格分隔（如 `project list` 而非 `projectlist`）
- `delete` 操作需用户明确批准后才能执行

---

## 意图决策树

### 用户意图 → 对应命令

```
用户想要…
├─ 查看清单列表 ────────────────────→ project list [--force] [--json]
│  └─ 查看项目任务 ─────────────────→ project get <项目ID> [--force] [--json]
│  └─ 查看项目元数据 ───────────────→ project info <项目ID> [--json]
│
├─ 管理清单
│  ├─ 创建新清单 ──────────────────→ project create "<名称>" [--color 色值]
│  ├─ 更新清单 ────────────────────→ project update <ID> [--name 新名称]
│  └─ 删除清单 ⚠️ ─────────────────→ project delete <ID>
│
├─ 管理任务
│  ├─ 创建任务 ────────────────────→ task create "<标题>" [--project ID] [--due YYYY-MM-DD] [--priority 0|1|3|5]
│  ├─ 创建清单任务 ────────────────→ task create-checklist "<标题>" --project ID --items "项1|项2"
│  ├─ 查看任务 ────────────────────→ task get <项目ID> <任务ID> [--json]
│  ├─ 更新任务 ────────────────────→ task update <项目ID> <任务ID> [--title 新标题]
│  ├─ 完成任务 ────────────────────→ task complete <项目ID> <任务ID>
│  ├─ 移动任务 ────────────────────→ task move <源项目> <目标项目> <任务ID>
│  └─ 删除任务 ⚠️ ────────────────→ task delete <项目ID> <任务ID]
│
└─ 查询任务
   ├─ 今日待办 ────────────────────→ search today [--force] [--json]
   ├─ 未来 N 天 ───────────────────→ search upcoming [天数] [--force] [--json]
   ├─ 指定日期范围 ────────────────→ search due-range <开始> <结束> [--force] [--json]
   ├─ 已完成任务 ──────────────────→ search completed <开始> <结束> [--json]
   ├─ 高级筛选 ────────────────────→ search filter [--project ID] [--priority N] [--tags 标签] [--json]
   └─ 收集箱 ──────────────────────→ search inbox [--force] [--json]
```

---

## 分类命令详解

### project — 项目/清单管理

| 子命令        | 用途           | 示例                                                    |
| ------------- | -------------- | ------------------------------------------------------- |
| `list`        | 列出所有清单   | `python cli/index.py project list`                      |
| `get`         | 查看清单任务   | `python cli/index.py project get <id>`                  |
| `info`        | 查看清单元数据 | `python cli/index.py project info <id>`                 |
| `create`      | 创建清单       | `python cli/index.py project create "工作"`             |
| `update`      | 更新清单       | `python cli/index.py project update <id> --name 新名称` |
| `delete` ⚠️   | 删除清单       | `python cli/index.py project delete <id>`               |
| `clear-cache` | 清除缓存       | `python cli/index.py project clear-cache`               |

### task — 任务操作

| 子命令             | 用途         | 示例                                                                               |
| ------------------ | ------------ | ---------------------------------------------------------------------------------- | ------ | ------ |
| `create`           | 创建任务     | `python cli/index.py task create "写周报" --due 2026-03-20 --priority 5`           |
| `create-checklist` | 创建清单任务 | `python cli/index.py task create-checklist "出差准备" --project <id> --items "订票 | 订酒店 | 打包"` |
| `get`              | 查看任务详情 | `python cli/index.py task get <项目ID> <任务ID>`                                   |
| `update`           | 更新任务     | `python cli/index.py task update <项目ID> <任务ID> --title 新标题`                 |
| `complete`         | 完成任务     | `python cli/index.py task complete <项目ID> <任务ID>`                              |
| `move`             | 移动任务     | `python cli/index.py task move <源项目ID> <目标项目ID> <任务ID>`                   |
| `delete` ⚠️        | 删除任务     | `python cli/index.py task delete <项目ID> <任务ID>`                                |

### search — 查询与筛选

| 子命令      | 用途     | 示例                                                           |
| ----------- | -------- | -------------------------------------------------------------- |
| `today`     | 今日待办 | `python cli/index.py search today`                             |
| `upcoming`  | 未来任务 | `python cli/index.py search upcoming 7`                        |
| `due-range` | 日期范围 | `python cli/index.py search due-range 2026-03-01 2026-03-31`   |
| `completed` | 已完成   | `python cli/index.py search completed 2026-03-01 2026-03-31`   |
| `filter`    | 高级筛选 | `python cli/index.py search filter --priority 3,5 --tags 工作` |
| `inbox`     | 收集箱   | `python cli/index.py search inbox`                             |

---

## 参数说明

### 全局参数

| 参数      | 说明                               |
| --------- | ---------------------------------- |
| `--force` | 忽略缓存，强制从服务器获取最新数据 |
| `--json`  | 以 JSON 格式输出（默认输出纯文本） |

### 任务参数

| 参数         | 说明                               | 示例               |
| ------------ | ---------------------------------- | ------------------ | -------- |
| `--project`  | 项目 ID（可用 "inbox" 表示收集箱） | `--project inbox`  |
| `--due`      | 截止日期，格式 YYYY-MM-DD          | `--due 2026-03-20` |
| `--priority` | 优先级：0=无, 1=低, 3=中, 5=高     | `--priority 5`     |
| `--tags`     | 标签，逗号分隔                     | `--tags 工作,紧急` |
| `--items`    | 清单子项，竖线分隔                 | `--items "订票     | 订酒店"` |
| `--color`    | 清单颜色代码                       | `--color 1`        |

---

## 缓存机制

为提高响应速度并减少 API 调用，本工具内置缓存（默认 365 分钟）：

1. **优先使用缓存**：`project list`、`project get`、`search` 命令默认读取缓存
2. **强制刷新**：使用 `--force` 参数跳过缓存
3. **自动失效**：执行 `create`、`update`、`delete`、`complete` 后，相关缓存自动清除
4. **手动清空**：`python cli/index.py project clear-cache`

---

## 环境变量

| 变量                 | 说明                                 |
| -------------------- | ------------------------------------ |
| `DIDA_CLIENT_ID`     | 开发者应用 Client ID                 |
| `DIDA_CLIENT_SECRET` | 开发者应用 Client Secret             |
| `DIDA_CACHE_MINUTES` | 缓存时长（默认 365 分钟）            |
| `DIDA_LIST_HIDDEN`   | 隐藏清单字符，包含该字符的清单不显示 |

---

## 故障排除

| 问题       | 解决方案                                                    |
| ---------- | ----------------------------------------------------------- |
| 数据不一致 | 使用 `--force` 重新查询                                     |
| 未授权错误 | 运行 `python cli/index.py auth` 重新授权                    |
| ID 错误    | 运行 `python cli/index.py project list --force` 核对最新 ID |
| 获取帮助   | 在分类后加 `-h`，如 `python cli/index.py task -h`           |

---

## 工作流程示例

**创建任务并设置优先级**：

```bash
python cli/index.py task create "完成项目报告" --project <项目ID> --due 2026-03-25 --priority 5 --tags 工作
```

**移动任务到其他清单**：

```bash
python cli/index.py task move <源项目ID> <目标项目ID> <任务ID>
```

**筛选高优先级任务**：

```bash
python cli/index.py search filter --priority 5 --tags 紧急 --json
```
