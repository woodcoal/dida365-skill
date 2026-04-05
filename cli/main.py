"""Dida365 CLI Logic."""

from __future__ import annotations

import argparse
import os
import re
import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


from auth import load_env_file, run_oauth_flow
from cache import get_cached_data, set_cached_data, invalidate_project_cache, clear_all_cache
from client import Dida365Client
from models import Project, Task

# 先加载 .env 文件，确保环境变量在模块初始化时就可用
load_env_file()

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore


PRIORITY_LABELS = {0: "  ", 1: "低", 3: "中", 5: "高"}

# 获取隐藏清单的字符配置，默认为空（不隐藏任何清单）
HIDDEN_SUBSTRING = os.environ.get("DIDA_LIST_HIDDEN", "")


def _strip_emoji_prefix(name: str) -> str:
    """
    去除字符串开头的 emoji 符号。
    
    :param name: 原始清单名称
    :return: 去除 emoji 后的名称
    """
    # 键帽 emoji: 数字 + FE0F (Variation Selector-16) + 20E3 (Combining Enclosing Keycap)
    keycap_vs = '\ufe0f'  # Variation Selector-16
    keycap_base = '\u20e3'  # 组合键帽符号
    
    while name:
        # 检查是否是键帽emoji (数字 + VS16 + 组合字符)
        if len(name) >= 3 and name[0].isdigit():
            if name[1] == keycap_vs and name[2] == keycap_base:
                name = name[3:]
                continue
        # 检查普通 emoji (单字符，范围 0x1F300-0x1FAFF)
        if name and 0x1F300 <= ord(name[0]) <= 0x1FAFF:
            name = name[1:]
            continue
        break
    return name


class DidaCLI:
    """
    滴答清单 CLI 处理器。
    负责业务逻辑封装与 CLI 命令分发。
    """

    def __init__(self):
        self.client = Dida365Client()

    # --- 数据获取与业务逻辑 ---

    def list_projects(self, force: bool = False, include_hidden: bool = False) -> List[Project]:
        """
        列出所有项目（带缓存支持）。
        
        :param force: 是否强制从服务器刷新数据
        :param include_hidden: 是否包含隐藏的清单（包含 HIDDEN_SUBSTRING 的清单）
        :return: 项目列表
        """
        if not force:
            cached = get_cached_data("projects")
            if cached is not None:
                return self._filter_hidden_projects(cached, include_hidden)
        
        projects = self.client.list_projects()
        set_cached_data("projects", projects)
        return self._filter_hidden_projects(projects, include_hidden)
    
    def _filter_hidden_projects(self, projects: List[Project], include_hidden: bool = False) -> List[Project]:
        """
        根据 HIDDEN_SUBSTRING 过滤隐藏的清单。
        
        :param projects: 原始项目列表
        :param include_hidden: 是否包含隐藏的清单
        :return: 过滤后的项目列表
        """
        if not HIDDEN_SUBSTRING or include_hidden:
            return projects
        return [p for p in projects if HIDDEN_SUBSTRING not in p.get("name", "")]

    def get_project_data(self, project_id: str, force: bool = False) -> Dict[str, Any]:
        """获取项目数据（带缓存支持）。"""
        if not force:
            cached = get_cached_data("project_data", sub_key=project_id)
            if cached is not None:
                return cached
        
        data = self.client.get_project_data(project_id)
        set_cached_data("project_data", data, sub_key=project_id)
        return data

    def get_today_tasks(self, force: bool = False) -> List[Task]:
        """获取今日到期的未完成任务。"""
        today_start = datetime.now().date().isoformat()
        return self.get_due_range_tasks(today_start, today_start, include_completed=False, force=force)

    def get_due_range_tasks(
        self,
        start_date: str,
        end_date: str,
        include_completed: bool = False,
        project_id: Optional[str] = None,
        force: bool = False,
    ) -> List[Task]:
        """使用 API 筛选器获取指定日期范围内到期的任务。"""
        # 1. 准备查询参数
        # API 的 startDate/endDate 是闭区间，且通常对应任务的时间范围
        payload: Dict[str, Any] = {
            "startDate": normalize_date(start_date),
            "endDate": normalize_date(end_date).replace("00:00:00", "23:59:59"),
            "status": [0, 2] if include_completed else [0]
        }
        if project_id:
            payload["projectIds"] = [project_id]

        # 2. 调用 API 筛选
        tasks = self.client.filter_tasks(payload)

        # 3. 补充项目名称（为了保持原有的输出格式）
        projects = self.list_projects(force=force)
        proj_map = {p["id"]: p.get("name", "") for p in projects}
        
        results: List[Task] = []
        for t in tasks:
            enriched = dict(t)
            enriched["_projectName"] = proj_map.get(t.get("projectId", ""), "未知项目")
            results.append(enriched)

        # 4. 排序：按截止日期、优先级、项目名、标题
        results.sort(key=lambda t: (
            self._get_task_date(t, "dueDate"),
            -int(t.get("priority", 0) or 0),
            t.get("_projectName", ""),
            t.get("title", ""),
        ))
        return results

    def get_inbox_data(self, force: bool = False) -> Tuple[Project, List[Task]]:
        """获取收集箱。"""

        data = self.get_project_data("inbox", force=force)
        project = data.get("project") or {"id": "inbox", "name": "收集箱"}
        return project, data.get("tasks", [])
    # --- 辅助方法 ---

    def _get_task_date(self, task: Task, field: str) -> str:
        """解析日期字段为 YYYY-MM-DD。"""
        val = task.get(field)
        if not val:
            return ""
        
        parsed = self._parse_api_datetime(val)
        if not parsed:
            return ""
        
        # 时区处理
        tz_info = datetime.now().astimezone().tzinfo
        tz_name = task.get("timeZone")
        if tz_name and ZoneInfo:
            try:
                tz_info = ZoneInfo(tz_name)
            except Exception:
                pass
        
        return parsed.astimezone(tz_info).date().isoformat()

    def _parse_api_datetime(self, value: Any) -> Optional[datetime]:
        """通用 API 日期解析。"""
        if not value:
            return None
    def _resolve_project_id(self, project_name_or_id: str) -> str:
        """根据项目名称或 ID 解析为项目 ID。"""
        # 如果已经是 ID 格式（24 位十六进制），直接返回
        if re.match(r'^[0-9a-f]{24}$', project_name_or_id):
            return project_name_or_id
        # 否则按名称查找
        projects = self.list_projects()
        for p in projects:
            if p.get('name') == project_name_or_id:
                return p['id']

        # 没找到，假设传入的就是 ID
        return project_name_or_id

    # --- 格式化方法 ---

    def format_task_list(self, tasks: List[Task], title: str = "任务列表") -> str:
        if not tasks: return f"{title}: 无任务"
        lines = [f"{title}:\n"]
        for t in tasks:
            prio = PRIORITY_LABELS.get(t.get("priority", 0), "  ")
            due = self._get_task_date(t, "dueDate")
            due_str = f" 截止:{due}" if due else ""
            tags = f" [{','.join(t.get('tags', []))}]" if t.get("tags") else ""
            proj = f" ({t['_projectName']})" if "_projectName" in t else ""
            status = " ✓" if t.get("status") == 2 else ""
            lines.append(f"  [{prio}] {t.get('title', '')}{status}{due_str}{tags}{proj}")
            lines.append(f"       ID: {t.get('id')}  项目ID: {t.get('projectId')}")
        lines.append(f"\n共 {len(tasks)} 个任务")
        return "\n".join(lines)

    def format_project_detail(self, data: Dict[str, Any]) -> str:
        proj = data.get("project", {})
        tasks = data.get("tasks", [])
        lines = [f"项目: {proj.get('name')} [{proj.get('id')}]", ""]
        if not tasks:
            lines.append("  无任务")
        else:
            for t in tasks:
                prio = PRIORITY_LABELS.get(t.get("priority", 0), "  ")
                due = self._get_task_date(t, "dueDate")
                due_str = f" 截止:{due}" if due else ""
                status = " ✓" if t.get("status") == 2 else ""
                lines.append(f"  [{prio}] {t.get('title')}{status}{due_str}")
                lines.append(f"       ID: {t.get('id')}")
        lines.append(f"\n共 {len(tasks)} 个任务")
        return "\n".join(lines)


# --- 命令处理函数 ---

def cmd_auth(args, cli: DidaCLI):
    run_oauth_flow(args.code)

def cmd_project_list(args, cli: DidaCLI):
    """列出项目列表，支持隐藏指定前缀的清单和 JSON 输出。"""
    # 获取所有项目（包含隐藏的，用于内部处理）
    all_projects = cli.list_projects(force=args.force, include_hidden=True)
    # 显示的项目（过滤掉隐藏的）
    projects = cli.list_projects(force=args.force, include_hidden=False)
    
    # 计算隐藏了多少个清单
    hidden_count = len(all_projects) - len(projects)
    
    # 根据 --json 参数决定输出格式
    if getattr(args, 'json', False):
        output_json(projects)
    else:
        lines = ["项目列表:\n"]
        for p in projects:
            archived = " (已归档)" if p.get("closed") else ""
            lines.append(f"  [{p['id']}] {p['name']}{archived}")
        
        # 显示隐藏清单的提示信息（仅当有隐藏清单且设置了隐藏前缀时）
        if hidden_count > 0 and HIDDEN_SUBSTRING:
            lines.append(f"\n共 {len(projects)} 个项目（已隐藏 {hidden_count} 个包含 '{HIDDEN_SUBSTRING}' 的清单）")
        else:
            lines.append(f"\n共 {len(projects)} 个项目")
        
        output_text("\n".join(lines))

def cmd_project_get(args, cli: DidaCLI):
    """获取项目详情，支持 JSON 输出格式。"""
    project_id = cli._resolve_project_id(args.id)
    data = cli.get_project_data(project_id, force=args.force)
    
    if getattr(args, 'json', False):
        output_json(data)
    else:
        output_text(cli.format_project_detail(data))
def cmd_project_create(args, cli: DidaCLI):
    payload: Project = {"name": args.name}
    if args.color: payload["color"] = args.color
    if args.kind: payload["kind"] = args.kind.upper()
    if args.view_mode: payload["viewMode"] = args.view_mode
    if args.sort_order is not None: payload["sortOrder"] = args.sort_order
    
    res = cli.client.create_project(payload)
    invalidate_project_cache()
    print(f"项目创建成功: {res['name']} [{res['id']}]")

def cmd_project_update(args, cli: DidaCLI):
    payload: Project = {}
    if args.name: payload["name"] = args.name
    if args.color: payload["color"] = args.color
    if args.view_mode: payload["viewMode"] = args.view_mode
    if args.sort_order is not None: payload["sortOrder"] = args.sort_order
    
    res = cli.client.update_project(args.id, payload)
    invalidate_project_cache(args.id)
    print(f"项目更新成功: {res['name']} [{res['id']}]")

def cmd_project_delete(args, cli: DidaCLI):
    cli.client.delete_project(args.id)
    invalidate_project_cache(args.id)
    print(f"项目已删除: {args.id}")

def cmd_task_create(args, cli: DidaCLI):
    payload: Task = {"title": args.title}
    if args.project: payload["projectId"] = args.project
    if args.content: payload["content"] = args.content
    if args.due: payload["dueDate"] = normalize_date(args.due)
    if args.priority is not None: payload["priority"] = args.priority
    if args.tags: payload["tags"] = [t.strip() for t in args.tags.split(",")]
    if args.all_day is not None: payload["isAllDay"] = args.all_day
    if args.tz: payload["timeZone"] = args.tz
    if args.repeat: payload["repeatFlag"] = args.repeat
    if args.desc: payload["desc"] = args.desc
    
    res = cli.client.create_task(payload)
    invalidate_project_cache(res.get("projectId"))
    print(f"任务创建成功: {res['title']} [{res['id']}]")

def cmd_task_update(args, cli: DidaCLI):
    payload: Task = {}
    if args.title: payload["title"] = args.title
    if args.content: payload["content"] = args.content
    if args.due: payload["dueDate"] = normalize_date(args.due)
    if args.priority is not None: payload["priority"] = args.priority
    if args.tags: payload["tags"] = [t.strip() for t in args.tags.split(",")]
    if args.all_day is not None: payload["isAllDay"] = args.all_day
    if args.tz: payload["timeZone"] = args.tz
    if args.repeat: payload["repeatFlag"] = args.repeat
    if args.desc: payload["desc"] = args.desc
    
    res = cli.client.update_task(args.id, args.project, payload)
    invalidate_project_cache(args.project)
    print(f"任务更新成功: {res['title']} [{res['id']}]")

def cmd_task_create_checklist(args, cli: DidaCLI):
    items = [{"title": item.strip(), "status": 0} for item in args.items.split("|")]
    payload: Task = {
        "title": args.title,
        "projectId": args.project,
        "items": items,
        "kind": "CHECKLIST"
    }
    if args.content: payload["content"] = args.content
    if args.due: payload["dueDate"] = normalize_date(args.due)
    if args.priority is not None: payload["priority"] = args.priority
    
    res = cli.client.create_task(payload)
    invalidate_project_cache(args.project)
    print(f"Checklist 创建成功: {res['title']} [{res['id']}]")

def cmd_project_info(args, cli: DidaCLI):
    """获取项目元数据，支持 JSON 输出格式。"""
    res = cli.client.get_project(args.id)
    if getattr(args, 'json', False):
        output_json(res)
    else:
        lines = [
            f"项目: {res.get('name')} [{res.get('id')}]",
            f"类型: {res.get('kind')}",
            f"视图: {res.get('viewMode')}",
            f"颜色: {res.get('color')}",
            f"已关闭: {'是' if res.get('closed') else '否'}"
        ]
        output_text("\n".join(lines))

def cmd_project_clear_cache(args, cli: DidaCLI):
    clear_all_cache()
    print("缓存已清除。")

def cmd_task_get(args, cli: DidaCLI):
    """获取任务详情，支持 JSON 输出格式。"""
    task = cli.client.get_task(args.project, args.id)
    if getattr(args, 'json', False):
        output_json(task)
    else:
        output_text(json.dumps(task, ensure_ascii=False, indent=2))

def cmd_task_complete(args, cli: DidaCLI):
    project_id = cli._resolve_project_id(args.project)
    cli.client.complete_task(project_id, args.id)
    print(f"任务已完成: {args.id}")

def cmd_task_delete(args, cli: DidaCLI):
    project_id = cli._resolve_project_id(args.project)
    cli.client.delete_task(project_id, args.id)
    print(f"任务已删除: {args.id}")

def cmd_task_move(args, cli: DidaCLI):
    ops = [{"fromProjectId": args.from_project, "toProjectId": args.to_project, "taskId": args.id}]
    res = cli.client.move_tasks(ops)
    invalidate_project_cache(args.from_project)
    invalidate_project_cache(args.to_project)
    print("任务移动成功。")

def cmd_search_today(args, cli: DidaCLI):
    """获取今日待办，支持 JSON 输出格式。"""
    tasks = cli.get_today_tasks(force=args.force)
    if getattr(args, 'json', False):
        output_json(tasks)
    else:
        output_text(cli.format_task_list(tasks, "今日待办"))

def cmd_search_upcoming(args, cli: DidaCLI):
    """获取未来几天到期任务，支持 JSON 输出格式。"""
    start = datetime.now().date()
    end = start + timedelta(days=args.days - 1)
    tasks = cli.get_due_range_tasks(start.isoformat(), end.isoformat(), project_id=args.project, force=args.force)
    if getattr(args, 'json', False):
        output_json(tasks)
    else:
        output_text(cli.format_task_list(tasks, f"未来 {args.days} 天到期任务 ({start.isoformat()} ~ {end.isoformat()})"))

def cmd_search_due_range(args, cli: DidaCLI):
    """获取指定日期范围的任务，支持 JSON 输出格式。"""
    tasks = cli.get_due_range_tasks(args.start, args.end, project_id=args.project, force=args.force)
    if getattr(args, 'json', False):
        output_json(tasks)
    else:
        output_text(cli.format_task_list(tasks, f"到期任务 ({args.start} ~ {args.end})"))

def cmd_search_completed(args, cli: DidaCLI):
    """获取已完成任务，支持 JSON 输出格式。"""
    project_ids = [args.project] if args.project else None
    tasks = cli.client.list_completed_tasks(project_ids=project_ids, start_date=args.start, end_date=args.end)
    if getattr(args, 'json', False):
        output_json(tasks)
    else:
        output_text(cli.format_task_list(tasks, f"已完成任务 ({args.start} ~ {args.end})"))

def cmd_search_filter(args, cli: DidaCLI):
    """高级筛选任务，支持 JSON 输出格式。"""
    payload: Dict[str, Any] = {}
    if args.project: payload["projectIds"] = [args.project]
    if args.start: payload["startDate"] = normalize_date(args.start)
    if args.end: payload["endDate"] = normalize_date(args.end)
    if args.priority: payload["priority"] = [int(p) for p in args.priority.split(",")]
    if args.tags: payload["tag"] = [t.strip() for t in args.tags.split(",")]
    if args.status: payload["status"] = [int(s) for s in args.status.split(",")]
    
    tasks = cli.client.filter_tasks(payload)
    if getattr(args, 'json', False):
        output_json(tasks)
    else:
        output_text(cli.format_task_list(tasks, "筛选结果"))

def cmd_search_inbox(args, cli: DidaCLI):
    """获取收集箱，支持 JSON 输出格式。"""
    project, tasks = cli.get_inbox_data(force=args.force)
    if getattr(args, 'json', False):
        output_json({"project": project, "tasks": tasks})
    else:
        output_text(cli.format_task_list(tasks, f"收集箱 ({project['name']})"))


# --- 辅助工具 ---

def output_json(data: Any) -> None:
    """
    以 JSON 格式输出数据。
    
    :param data: 要输出的数据（dict 或 list）
    """
    print(json.dumps(data, ensure_ascii=False, indent=2))

def output_text(text: str) -> None:
    """
    以纯文本格式输出数据。
    
    :param text: 要输出的文本
    """
    print(text)

def normalize_date(date_str: str) -> str:
    if "T" in date_str: return date_str
    offset = datetime.now().astimezone().strftime("%z") or "+0000"
    return f"{date_str}T00:00:00{offset}"

def repair_argv():
    if len(sys.argv) < 2: return
    categories = ["project", "task", "search", "auth", "check"]
    cat_arg = sys.argv[1]
    for cat in categories:
        if cat_arg.startswith(cat) and len(cat_arg) > len(cat):
            sys.argv[1] = cat
            sys.argv.insert(2, cat_arg[len(cat):])
            break

def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="滴答清单 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Auth
    p_auth = subparsers.add_parser("auth", help="认证授权", description="进行 OAuth 授权获取访问令牌")
    p_auth.add_argument("--code", help="手动授权码（如果无法自动打开浏览器）")
    p_auth.set_defaults(func=cmd_auth)

    # Project
    p_proj = subparsers.add_parser("project", help="项目管理", description="项目管理的各种子命令")
    ps_proj = p_proj.add_subparsers(dest="sub", required=True)
    
    pp_list = ps_proj.add_parser("list", help="列出所有项目", description="列出所有项目（可隐藏包含指定字符的项目）")
    pp_list.add_argument("--force", action="store_true", help="强制从服务器刷新数据")
    pp_list.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    pp_list.set_defaults(func=cmd_project_list)
    
    pp_get = ps_proj.add_parser("get", help="获取项目详情", description="查看指定项目的详细信息")
    pp_get.add_argument("id", help="项目ID")
    pp_get.add_argument("--force", action="store_true", help="强制从服务器刷新数据")
    pp_get.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    pp_get.set_defaults(func=cmd_project_get)
    
    pp_create = ps_proj.add_parser("create", help="创建项目", description="创建一个新项目")
    pp_create.add_argument("name", help="项目名称")
    pp_create.add_argument("--color", help="项目颜色（颜色代码）")
    pp_create.add_argument("--kind", choices=["TASK", "NOTE"], help="项目类型（TASK=任务，NOTE=清单）")
    pp_create.add_argument("--view-mode", choices=["list", "kanban", "timeline"], help="视图模式")
    pp_create.add_argument("--sort-order", type=int, help="排序顺序")
    pp_create.set_defaults(func=cmd_project_create)
    
    pp_update = ps_proj.add_parser("update", help="更新项目", description="更新项目信息")
    pp_update.add_argument("id", help="项目ID")
    pp_update.add_argument("--name", help="新项目名称")
    pp_update.add_argument("--color", help="项目颜色")
    pp_update.add_argument("--view-mode", choices=["list", "kanban", "timeline"], help="视图模式")
    pp_update.add_argument("--sort-order", type=int, help="排序顺序")
    pp_update.set_defaults(func=cmd_project_update)
    
    pp_info = ps_proj.add_parser("info", help="查看项目信息", description="查看项目的简要信息")
    pp_info.add_argument("id", help="项目ID")
    pp_info.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    pp_info.set_defaults(func=cmd_project_info)
    
    ps_proj.add_parser("delete", help="删除项目", description="删除指定项目").add_argument("id", help="项目ID")
    ps_proj.choices["delete"].set_defaults(func=cmd_project_delete)
    
    ps_proj.add_parser("clear-cache", help="清除缓存", description="清除项目缓存数据").set_defaults(func=cmd_project_clear_cache)

    # Task
    p_task = subparsers.add_parser("task", help="任务管理", description="任务管理的各种子命令")
    ps_task = p_task.add_subparsers(dest="sub", required=True)
    
    t_get = ps_task.add_parser("get", help="获取任务详情", description="查看指定任务的详细信息")
    t_get.add_argument("project", help="项目ID或名称")
    t_get.add_argument("id", help="任务ID")
    t_get.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    t_get.set_defaults(func=cmd_task_get)

    tt_checklist = ps_task.add_parser("create-checklist", help="创建清单任务", description="创建一个包含多个子项的任务")
    tt_checklist.add_argument("title", help="任务标题")
    tt_checklist.add_argument("--project", required=True, help="项目ID或名称")
    tt_checklist.add_argument("--items", required=True, help='子项，用 "|" 分隔')
    tt_checklist.add_argument("--content", help="任务描述")
    tt_checklist.add_argument("--due", help="截止日期（YYYY-MM-DD）")
    tt_checklist.add_argument("--priority", type=int, choices=[0, 1, 3, 5], help="优先级（0=无，1=低，3=中，5=高）")
    tt_checklist.set_defaults(func=cmd_task_create_checklist)
    
    tt_create = ps_task.add_parser("create", help="创建任务", description="创建一个新任务")
    tt_create.add_argument("title", help="任务标题")
    tt_create.add_argument("--project", help="项目ID或名称")
    tt_create.add_argument("--content", help="任务描述")
    tt_create.add_argument("--due", help="截止日期（YYYY-MM-DD）")
    tt_create.add_argument("--priority", type=int, choices=[0, 1, 3, 5], help="优先级（0=无，1=低，3=中，5=高）")
    tt_create.add_argument("--tags", help="标签（逗号分隔）")
    tt_create.add_argument("--all-day", type=lambda x: x.lower() == 'true', help="是否全天（true/false）")
    tt_create.add_argument("--repeat", help="重复规则")
    tt_create.add_argument("--tz", help="时区")
    tt_create.add_argument("--desc", help="详细描述")
    tt_create.set_defaults(func=cmd_task_create)
    
    tt_update = ps_task.add_parser("update", help="更新任务", description="更新任务信息")
    tt_update.add_argument("project", help="项目ID或名称")
    tt_update.add_argument("id", help="任务ID")
    tt_update.add_argument("--title", help="新任务标题")
    tt_update.add_argument("--content", help="任务描述")
    tt_update.add_argument("--due", help="截止日期")
    tt_update.add_argument("--priority", type=int, choices=[0, 1, 3, 5], help="优先级")
    tt_update.add_argument("--tags", help="标签")
    tt_update.add_argument("--all-day", type=lambda x: x.lower() == 'true', help="是否全天")
    tt_update.add_argument("--repeat", help="重复规则")
    tt_update.add_argument("--tz", help="时区")
    tt_update.add_argument("--desc", help="详细描述")
    tt_update.set_defaults(func=cmd_task_update)
    
    ps_task.add_parser("complete", help="完成任务", description="标记指定任务为已完成").add_argument("project", help="项目ID或名称")
    ps_task.choices["complete"].add_argument("id", help="任务ID")
    ps_task.choices["complete"].set_defaults(func=cmd_task_complete)
    
    ps_task.add_parser("delete", help="删除任务", description="删除指定任务").add_argument("project", help="项目ID或名称")
    ps_task.choices["delete"].add_argument("id", help="任务ID")
    ps_task.choices["delete"].set_defaults(func=cmd_task_delete)
    
    t_move = ps_task.add_parser("move", help="移动任务", description="将任务从一个项目移动到另一个项目")
    t_move.add_argument("from_project", help="源项目ID或名称")
    t_move.add_argument("to_project", help="目标项目ID或名称")
    t_move.add_argument("id", help="任务ID")
    t_move.set_defaults(func=cmd_task_move)

    # Search
    p_search = subparsers.add_parser("search", help="查询任务", description="查询任务的各种子命令")
    ps_search = p_search.add_subparsers(dest="sub", required=True)
    
    ps_today = ps_search.add_parser("today", help="查看今天的任务", description="查看今天需要完成的任务")
    ps_today.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ps_today.set_defaults(func=cmd_search_today, force=False)
    
    ps_upcoming = ps_search.add_parser("upcoming", help="查看即将到期的任务", description="查看未来N天内需要完成的任务（默认7天）")
    ps_upcoming.add_argument("days", type=int, nargs="?", default=7, help="查看未来多少天内的任务（默认7天）")
    ps_upcoming.add_argument("--project", help="指定项目ID或名称筛选")
    ps_upcoming.add_argument("--force", action="store_true", help="强制从服务器刷新数据")
    ps_upcoming.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ps_upcoming.set_defaults(func=cmd_search_upcoming)
    
    ps_range = ps_search.add_parser("due-range", help="查看指定日期范围的任务", description="查看截止日在指定日期范围内的任务")
    ps_range.add_argument("start", help="开始日期（YYYY-MM-DD）")
    ps_range.add_argument("end", help="结束日期（YYYY-MM-DD）")
    ps_range.add_argument("--project", help="指定项目ID或名称筛选")
    ps_range.add_argument("--force", action="store_true", help="强制从服务器刷新数据")
    ps_range.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ps_range.set_defaults(func=cmd_search_due_range)
    
    ps_completed = ps_search.add_parser("completed", help="查看已完成的任务", description="查看在指定日期范围内已完成的任务")
    ps_completed.add_argument("start", help="开始日期（YYYY-MM-DD）")
    ps_completed.add_argument("end", help="结束日期（YYYY-MM-DD）")
    ps_completed.add_argument("--project", help="指定项目ID或名称筛选")
    ps_completed.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ps_completed.set_defaults(func=cmd_search_completed)
    
    ps_filter = ps_search.add_parser("filter", help="高级筛选任务", description="根据多个条件筛选任务（优先级、标签、状态等）")
    ps_filter.add_argument("--project", help="指定项目ID或名称筛选")
    ps_filter.add_argument("--start", help="开始日期（YYYY-MM-DD）")
    ps_filter.add_argument("--end", help="结束日期（YYYY-MM-DD）")
    ps_filter.add_argument("--priority", help="优先级筛选（1=低，3=中，5=高）")
    ps_filter.add_argument("--tags", help="标签筛选（逗号分隔多个标签）")
    ps_filter.add_argument("--status", help="状态筛选（0=未完成，2=已完成）")
    ps_filter.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ps_filter.set_defaults(func=cmd_search_filter)
    
    ps_inbox = ps_search.add_parser("inbox", help="查看收集箱任务", description="查看收集箱中的所有任务")
    ps_inbox.add_argument("--force", action="store_true", help="强制从服务器刷新数据")
    ps_inbox.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ps_inbox.set_defaults(func=cmd_search_inbox)

    return parser

def main():
    load_env_file()
    repair_argv()
    parser = setup_parser()
    args = parser.parse_args()
    cli = DidaCLI()
    if hasattr(args, "func"):
        args.func(args, cli)
    else:
        parser.print_help()
