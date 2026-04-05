# dida365-skill

基于 Python 3 标准库实现的滴答清单/TickTick CLI 工具，支持通过命令行管理任务和项目。

## 核心能力

- **OAuth 2.0 授权**：完整的授权流程支持
- **项目管理**：创建、更新、删除及列出所有清单
- **任务管理**：增删改查、标记完成、跨项目移动
- **高级任务**：支持 Checklist（清单任务）和高级字段
- **智能查询**：今日待办、未来到期、指定区间、已完成任务、高级筛选
- **零依赖**：仅使用 Python 标准库，无需安装第三方包

---

## 快速开始

### 1. 创建开发者应用

1. 登录 [滴答清单开发者平台](https://developer.dida365.com/manage)
2. 创建新应用，设置 **OAuth redirect URL** 为：`http://localhost:18365/callback`
3. 获取 `Client ID` 和 `Client Secret`

### 2. 配置环境

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的凭据
DIDA_CLIENT_ID=your_client_id
DIDA_CLIENT_SECRET=your_client_secret
```

### 3. 完成授权

```bash
python cli/index.py auth
```

按照提示在浏览器中完成授权。远程服务器可使用 `--code` 参数手动提交授权码。

---

## 常用命令

### 查看清单

```bash
# 列出所有清单
python cli/index.py project list

# 查看清单中的任务
python cli/index.py project get <项目ID>

# 查看收集箱
python cli/index.py search inbox
```

### 管理任务

```bash
# 创建任务（带截止日期和优先级）
python cli/index.py task create "完成项目报告" --due 2026-03-25 --priority 5

# 创建清单任务（子任务）
python cli/index.py task create-checklist "出差准备" \
  --project <项目ID> \
  --items "订票|订酒店|打包行李"

# 完成任务
python cli/index.py task complete <项目ID> <任务ID>

# 移动任务到其他清单
python cli/index.py task move <源项目ID> <目标项目ID> <任务ID>
```

### 查询任务

```bash
# 今日待办
python cli/index.py search today

# 未来 7 天任务
python cli/index.py search upcoming 7

# 指定日期范围
python cli/index.py search due-range 2026-03-01 2026-03-31

# 筛选高优先级任务
python cli/index.py search filter --priority 5

# 按标签筛选
python cli/index.py search filter --tags 工作,紧急
```

---

## 优先级说明

| 值  | 优先级 |
| --- | ------ |
| 0   | 无     |
| 1   | 低     |
| 3   | 中     |
| 5   | 高     |

---

## 缓存机制

本工具内置缓存以提高响应速度：

- **默认缓存时长**：365 分钟
- **强制刷新**：添加 `--force` 参数
- **自动失效**：执行写操作后自动清除相关缓存
- **手动清空**：`python cli/index.py project clear-cache`

可通过环境变量 `DIDA_CACHE_MINUTES` 自定义缓存时长。

---

## 输出格式

默认输出纯文本格式。使用 `--json` 参数可获取 JSON 格式输出：

```bash
python cli/index.py project list --json
python cli/index.py search today --json
```

---

## 高级用法

### 隐藏敏感清单

设置 `DIDA_LIST_HIDDEN` 环境变量，包含该字符的清单不会在列表中显示：

```bash
DIDA_LIST_HIDDEN=~
```

### 查看命令帮助

```bash
python cli/index.py -h           # 查看主命令帮助
python cli/index.py task -h      # 查看任务子命令帮助
python cli/index.py task create -h  # 查看 create 子命令详细参数
```

---

## 项目结构

```
dida365-skill/
├── SKILL.md              # AI Agent 使用说明（SKILL.md 标准格式）
├── README.md             # 用户使用文档
├── .env.example          # 环境变量模板
├── cli/                  # CLI 脚本
│   ├── index.py          # CLI 入口
│   ├── main.py           # 主逻辑
│   ├── auth.py           # OAuth 授权
│   ├── client.py         # API 客户端
│   ├── models.py         # 数据模型
│   └── cache.py          # 缓存管理
├── reference/            # 参考文档
│   └── Dida365 Open API.md
└── tests/               # 测试
```

---

## 故障排除

| 问题       | 解决方案                                                                     |
| ---------- | ---------------------------------------------------------------------------- |
| 授权失败   | 确认 `.env` 中 Client ID 和 Secret 正确，重新运行 `python cli/index.py auth` |
| 数据不同步 | 在命令后添加 `--force` 参数强制刷新                                          |
| API 限流   | 减少查询频率，或使用 `--json` 减少输出处理                                   |

---

## 致谢

本项目基于 [fanxing-6/dida365-skill](https://github.com/fanxing-6/dida365-skill) 开发。

由 [woodcoal](https://github.com/woodcoal) 进行优化与功能扩展，包括：

- 优化 CLI 命令结构，支持更清晰的层级调用
- 增强 Checklist 和高级 JSON 字段的处理能力
- 完善面向 AI Agent 的 `SKILL.md` 文档

---

**声明**：本工具并非滴答清单官方出品。

基于 **MIT License** 开源。
