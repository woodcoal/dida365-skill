# 以下内容主要供人类阅读；如果你是大型语言模型，请直接阅读本仓库中的 `SKILL.md` 获取机器侧说明。

# dida365-skill

`dida365-skill` 是一个基于 Python 3 标准库实现的 Claude Code Skill，用来通过 Dida365 / TickTick OpenAPI 管理任务和项目。

它的目标不是做一个通用 SDK，而是提供一组稳定、可组合的 CLI 子命令，让模型在读取 `SKILL.md` 后，能够尽量可靠地完成任务创建、查询、更新、删除、项目管理和高级字段操作。

## 仓库内容

- `SKILL.md`
  模型实际使用的说明文档。包含触发描述、命令选择规则、OAuth 前置说明、常见工作流和高级参数使用方式。

- `index.py`
  CLI 主入口，封装了 Dida365 OpenAPI 调用、输出格式化、参数解析和全部命令处理逻辑。

- `auth.py`
  OAuth 2.0 相关逻辑，包括本地回调服务、授权码换 token、refresh token 刷新和 token 持久化。

- `.env.example`
  环境变量模板。

- `.gitignore`
  忽略本地敏感文件、token 文件和 Python 缓存。

## 主要能力

- OAuth 授权
- 查看项目列表和项目元数据
- 查看项目下任务
- 查看单个任务详情
- 创建普通任务
- 创建 checklist 任务
- 用原始 JSON 创建/更新高级任务
- 更新任务、完成任务、删除任务
- 跨项目移动任务
- 创建、更新、删除项目
- 查询今日任务、未来到期任务、指定区间到期任务
- 查询指定时间范围内的已完成任务
- 按项目、时间、优先级、标签、状态筛选任务

## 技术特点

- 仅依赖 Python 标准库，不需要安装第三方包
- 使用 Dida365 OpenAPI，而不是网页自动化
- 命令行接口优先，复杂字段可通过 `stdin JSON` 传入
- 对“删除后直查接口仍返回缓存对象”的情况做了可见性保护
- 输出面向 Claude Code 使用场景做了格式化，方便模型读取

## 环境要求

- Python 3.8+
- 一个可用的 Dida365 开发者应用
- Dida365 账号授权后的 access token

## 首次配置

### 1. 创建开发者应用

如果你还没有 `client_id` 和 `client_secret`：

1. 打开 `https://developer.dida365.com/manage`
2. 点击 `New App`
3. 输入任意应用名并创建
4. 点击应用的 `Edit`
5. 在 `App Setting` 页面获取 `Client ID` 和 `Client Secret`
6. 将 `OAuth redirect URL` 设置为：

```text
http://localhost:18365/callback
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```dotenv
DIDA_CLIENT_ID=your_client_id
DIDA_CLIENT_SECRET=your_client_secret
```

### 3. 完成 OAuth 授权

```bash
python3 index.py auth
```

如果你在远程机器上运行，可以在本地浏览器完成授权后，把回调地址里的 `code` 手动带回来：

```bash
python3 index.py auth --code <authorization_code>
```

## 常用命令

### 基础查询

```bash
python3 index.py projects
python3 index.py project-info <projectId>
python3 index.py project <projectId>
python3 index.py task <projectId> <taskId>
```

### 任务操作

```bash
python3 index.py create-task "写周报" --project <projectId> --due 2026-03-20 --priority 3
python3 index.py update-task <taskId> --project <projectId> --content "更新说明"
python3 index.py complete-task <projectId> <taskId>
python3 index.py delete-task <projectId> <taskId>
python3 index.py move-task <fromProjectId> <toProjectId> <taskId>
```

### checklist 与高级字段

```bash
python3 index.py create-checklist "出差准备" --project <projectId> --items "订机票|订酒店|准备材料"
```

```bash
cat <<'JSON' | python3 index.py create-task-raw
{
  "title": "高级任务",
  "projectId": "<projectId>",
  "desc": "任务描述",
  "isAllDay": true,
  "startDate": "2026-03-22T00:00:00+0800",
  "dueDate": "2026-03-22T23:59:59+0800",
  "timeZone": "Asia/Shanghai",
  "reminders": ["TRIGGER:PT0S"],
  "repeatFlag": "RRULE:FREQ=DAILY;INTERVAL=1",
  "priority": 3,
  "sortOrder": 1000,
  "items": [
    {
      "title": "子项1",
      "status": 0,
      "isAllDay": true,
      "timeZone": "Asia/Shanghai",
      "sortOrder": 10
    }
  ]
}
JSON
```

```bash
cat <<'JSON' | python3 index.py update-task-raw <taskId>
{
  "projectId": "<projectId>",
  "desc": "更新后的描述",
  "reminders": ["TRIGGER:P0DT9H0M0S", "TRIGGER:PT0S"]
}
JSON
```

### 查询命令

```bash
python3 index.py today
python3 index.py upcoming 10
python3 index.py due-range 2026-03-17 2026-03-26 --project <projectId>
python3 index.py completed 2026-03-17 2026-03-17 --project <projectId>
python3 index.py filter-tasks --project <projectId> --priority 3 --status 0 --tags 工作,重要
```

### 项目操作

```bash
python3 index.py create-project "新项目"
python3 index.py update-project <projectId> --name "新名字"
python3 index.py delete-project <projectId>
```

## 使用建议

- 给模型看的主入口是 `SKILL.md`，不是 `README.md`
- 人类排查问题时优先看 `README.md`
- 需要复杂字段时优先用 `create-task-raw` / `update-task-raw`
- 删除任务后，如果单任务直查仍返回内容，以项目列表和筛选结果为准

## 安全说明

- `.env` 和 `.dida-token.json` 不应提交到仓库
- 本仓库默认已通过 `.gitignore` 忽略这些本地敏感文件
- 若你怀疑 token 泄露，应在 Dida365 后台重置相关授权信息

## 适用场景

- 让 Claude Code 直接管理滴答清单
- 通过稳定 CLI 命令驱动任务自动化
- 用 OpenAPI 高级字段构造复杂任务或 checklist
- 在不安装第三方依赖的环境中运行
