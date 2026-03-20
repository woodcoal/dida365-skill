#!/usr/bin/env python3
"""Dida365 CLI skill entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any


from auth import get_access_token, load_env_file, refresh_access_token, run_oauth_flow

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8 fallback
    ZoneInfo = None  # type: ignore[assignment]

API_BASE = "https://api.dida365.com/open/v1"
PRIORITY_LABELS = {0: "  ", 1: "低", 3: "中", 5: "高"}

# 缓存配置
CACHE_FILE = os.path.join(os.path.dirname(__file__), ".dida-cache.json")
CACHE_EXPIRATION_MINUTES = int(os.environ.get("DIDA_CACHE_MINUTES", "365"))


def load_cache() -> dict[str, Any]:
    """从本地文件加载缓存数据。"""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache_data: dict[str, Any]) -> None:
    """将缓存数据保存到本地文件。"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def get_cached_data(key: str, sub_key: str | None = None) -> Any | None:
    """获取缓存数据，如果已过期则返回 None。"""
    cache = load_cache()
    data_entry = cache.get(key)
    if sub_key and data_entry:
        data_entry = data_entry.get(sub_key)

    if not data_entry:
        return None

    timestamp = data_entry.get("timestamp", 0)
    if datetime.now().timestamp() - timestamp > CACHE_EXPIRATION_MINUTES * 60:
        return None

    return data_entry.get("data")


def set_cached_data(key: str, data: Any, sub_key: str | None = None) -> None:
    """设置缓存数据。"""
    cache = load_cache()
    entry = {"timestamp": datetime.now().timestamp(), "data": data}
    
    if sub_key:
        if key not in cache:
            cache[key] = {}
        cache[key][sub_key] = entry
    else:
        cache[key] = entry
        
    save_cache(cache)


def request_dida_api(method: str, api_path: str, body: dict[str, Any] | None = None, retry: bool = True) -> Any:
    """发送请求到 Dida365 API。"""
    token = get_access_token()
    data = None
    headers = {"Authorization": f"Bearer {token}"}

    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif method in {"POST", "PUT", "PATCH"}:
        data = b""

    request = urllib.request.Request(
        f"{API_BASE}{api_path}",
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request) as response:
            if response.status == 204:
                return None

            payload = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                if not payload:
                    return None
                return json.loads(payload.decode("utf-8"))
            return payload.decode("utf-8")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        if exc.code == 401 and retry and not os.environ.get("DIDA_ACCESS_TOKEN"):
            refresh_access_token()
            return request_dida_api(method, api_path, body=body, retry=False)
        raise RuntimeError(f"Dida API {method} {api_path}: HTTP {exc.code} - {text}") from exc


# --- API 封装函数 ---

def list_projects(force: bool = False) -> list[dict[str, Any]]:
    """列出所有项目。"""
    if not force:
        cached = get_cached_data("projects")
        if cached is not None:
            return cached
            
    data = request_dida_api("GET", "/project")
    set_cached_data("projects", data)
    return data


def get_project_data(project_id: str, force: bool = False) -> dict[str, Any]:
    """获取项目及其任务数据。"""
    if not force:
        cached = get_cached_data("project_data", sub_key=project_id)
        if cached is not None:
            return cached
            
    data = request_dida_api("GET", f"/project/{project_id}/data")
    set_cached_data("project_data", data, sub_key=project_id)
    return data


def get_project(project_id: str) -> dict[str, Any]:
    """获取项目元数据。"""
    return request_dida_api("GET", f"/project/{project_id}")


def get_task(project_id: str, task_id: str) -> dict[str, Any]:
    """获取单个任务详情。"""
    return request_dida_api("GET", f"/project/{project_id}/task/{task_id}")


def create_project(data: dict[str, Any]) -> dict[str, Any]:
    """创建新项目。"""
    result = request_dida_api("POST", "/project", body=data)
    set_cached_data("projects", None) # 清除项目列表缓存
    return result


def update_project(project_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """更新项目属性。"""
    result = request_dida_api("POST", f"/project/{project_id}", body=data)
    set_cached_data("projects", None) # 清除项目列表缓存
    return result


def delete_project(project_id: str) -> None:
    """删除指定项目。"""
    request_dida_api("DELETE", f"/project/{project_id}")
    set_cached_data("projects", None) # 清除项目列表缓存


def create_task(task_data: dict[str, Any]) -> dict[str, Any]:
    """创建新任务。"""
    result = request_dida_api("POST", "/task", body=task_data)
    project_id = result.get("projectId")
    if project_id:
        set_cached_data("project_data", None, sub_key=project_id) # 清除该项目任务缓存
    return result


def update_task(task_id: str, project_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """更新任务属性。"""
    payload = dict(data)
    payload["projectId"] = project_id
    result = request_dida_api("POST", f"/task/{task_id}", body=payload)
    set_cached_data("project_data", None, sub_key=project_id) # 清除该项目任务缓存
    return result


def complete_task(project_id: str, task_id: str) -> None:
    """标记任务为完成。"""
    request_dida_api("POST", f"/project/{project_id}/task/{task_id}/complete")
    set_cached_data("project_data", None, sub_key=project_id) # 清除该项目任务缓存


def delete_task(project_id: str, task_id: str) -> None:
    """删除指定任务。"""
    request_dida_api("DELETE", f"/project/{project_id}/task/{task_id}")
    set_cached_data("project_data", None, sub_key=project_id) # 清除该项目任务缓存


def move_tasks(operations: list[dict[str, str]]) -> list[dict[str, Any]]:
    """跨项目移动任务。"""
    result = request_dida_api("POST", "/task/move", body=operations)
    # 清除受影响项目的缓存
    project_ids = set()
    for op in operations:
        if op.get("fromProjectId"):
            project_ids.add(op["fromProjectId"])
        if op.get("toProjectId"):
            project_ids.add(op["toProjectId"])
    for pid in project_ids:
        set_cached_data("project_data", None, sub_key=pid)
    return result


def list_completed_tasks(
    project_ids: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """查询已完成任务。"""
    payload: dict[str, Any] = {}
    if project_ids:
        payload["projectIds"] = project_ids
    if start_date:
        payload["startDate"] = normalize_range_boundary(start_date, end_of_day=False)
    if end_date:
        payload["endDate"] = normalize_range_boundary(end_date, end_of_day=True)
    return request_dida_api("POST", "/task/completed", body=payload)


def filter_tasks(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """根据条件筛选任务。"""
    return request_dida_api("POST", "/task/filter", body=filters)


def is_task_visible_in_project(project_id: str, task_id: str) -> bool:
    """校验任务在项目中是否可见。"""
    for status in (0, 2):
        tasks = filter_tasks({"projectIds": [project_id], "status": [status]})
        if any(str(task.get("id")) == str(task_id) for task in tasks):
            return True
    return False


# --- 辅助逻辑 ---

def get_today_tasks(force: bool = False) -> list[dict[str, Any]]:
    """获取今日到期的未完成任务。"""
    today_str = datetime.now().date().isoformat()
    results: list[dict[str, Any]] = []

    for project in list_projects(force=force):
        project_data = get_project_data(project["id"], force=force)
        for task in project_data.get("tasks", []):
            due_day = get_task_date(task, "dueDate")
            if due_day == today_str and task.get("status") == 0:
                enriched = dict(task)
                enriched["_projectName"] = project.get("name", "")
                results.append(enriched)

    return results


def get_due_range_tasks(
    start_date: str,
    end_date: str,
    include_completed: bool = False,
    project_id: str | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """获取指定日期范围内到期的任务。"""
    results: list[dict[str, Any]] = []

    if project_id:
        project_data = get_project_data(project_id, force=force)
        projects = [
            {
                "id": project_data.get("project", {}).get("id", project_id),
                "name": project_data.get("project", {}).get("name", project_id),
                "tasks": project_data.get("tasks", []),
            }
        ]
    else:
        projects = []
        for project in list_projects(force=force):
            project_data = get_project_data(project["id"], force=force)
            projects.append(
                {
                    "id": project["id"],
                    "name": project.get("name", ""),
                    "tasks": project_data.get("tasks", []),
                }
            )

    for project in projects:
        for task in project.get("tasks", []):
            due_day = get_task_date(task, "dueDate")
            if not due_day:
                continue
            if start_date <= due_day <= end_date and (include_completed or task.get("status") == 0):
                enriched = dict(task)
                enriched["_projectName"] = project.get("name", "")
                results.append(enriched)

    results.sort(
        key=lambda task: (
            get_task_date(task, "dueDate"),
            -int(task.get("priority", 0) or 0),
            task.get("_projectName", ""),
            task.get("title", ""),
        )
    )
    return results


def get_inbox_data(force: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """获取收集箱项目及任务。"""
    projects = list_projects(force=force)
    inbox = next(
        (
            project
            for project in projects
            if project.get("kind") == "TASK" and project.get("isOwner") and project.get("inAll") is not False
        ),
        None,
    )
    if inbox is None:
        inbox = next((project for project in projects if project.get("name") in {"收集箱", "Inbox"}), None)
    if inbox is None and projects:
        inbox = projects[0]
    if inbox is None:
        raise RuntimeError("未找到收集箱项目")

    project_data = get_project_data(inbox["id"], force=force)
    return inbox, project_data.get("tasks", [])


# --- 格式化函数 ---

def format_project_list(projects: list[dict[str, Any]]) -> str:
    """格式化项目列表。"""
    lines = ["项目列表:\n"]
    for project in projects:
        archived = " (已归档)" if project.get("closed") else ""
        lines.append(f"  [{project['id']}] {project['name']}{archived}")
    lines.append(f"\n共 {len(projects)} 个项目")
    return "\n".join(lines)


def parse_api_datetime(value: str | None) -> datetime | None:
    """解析 API 返回的日期时间字符串。"""
    if not value:
        return None

    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=datetime.now().astimezone().tzinfo)

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def get_task_timezone(task: dict[str, Any]):
    """获取任务的时区信息。"""
    tz_name = task.get("timeZone")
    if tz_name and ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            pass
    return datetime.now().astimezone().tzinfo


def get_task_date(task: dict[str, Any], field: str) -> str:
    """获取任务日期 (YYYY-MM-DD)。"""
    parsed = parse_api_datetime(task.get(field))
    if parsed is None:
        return ""
    timezone_info = get_task_timezone(task)
    if timezone_info is not None:
        parsed = parsed.astimezone(timezone_info)
    return parsed.date().isoformat()


def get_task_datetime(task: dict[str, Any], field: str) -> str:
    """获取任务日期时间 (ISO 格式)。"""
    parsed = parse_api_datetime(task.get(field))
    if parsed is None:
        return ""
    timezone_info = get_task_timezone(task)
    if timezone_info is not None:
        parsed = parsed.astimezone(timezone_info)
    return parsed.isoformat(timespec="seconds")


def format_task_list(tasks: list[dict[str, Any]], title: str = "任务列表") -> str:
    """格式化任务列表。"""
    if not tasks:
        return f"{title}: 无任务"

    lines = [f"{title}:\n"]
    for task in tasks:
        priority = PRIORITY_LABELS.get(task.get("priority"), "  ")
        due_date = get_task_date(task, "dueDate")
        due = f" 截止:{due_date}" if due_date else ""
        tags = f" [{','.join(task['tags'])}]" if task.get("tags") else ""
        project = f" ({task['_projectName']})" if task.get("_projectName") else ""
        status = " ✓" if task.get("status") == 2 else ""
        lines.append(f"  [{priority}] {task.get('title', '')}{status}{due}{tags}{project}")
        lines.append(f"       ID: {task.get('id')}  项目ID: {task.get('projectId')}")
        if task.get("content"):
            lines.append(f"       {task['content'][:80]}")
    lines.append(f"\n共 {len(tasks)} 个任务")
    return "\n".join(lines)


def format_project_detail(project_data: dict[str, Any]) -> str:
    """格式化项目任务详情。"""
    project = project_data.get("project", {})
    tasks = project_data.get("tasks", [])
    lines = [f"项目: {project.get('name', '')} [{project.get('id', '')}]", ""]

    if not tasks:
        lines.append("  无任务")
    else:
        for task in tasks:
            priority = PRIORITY_LABELS.get(task.get("priority"), "  ")
            due_date = get_task_date(task, "dueDate")
            due = f" 截止:{due_date}" if due_date else ""
            tags = f" [{','.join(task['tags'])}]" if task.get("tags") else ""
            status = " ✓" if task.get("status") == 2 else ""
            lines.append(f"  [{priority}] {task.get('title', '')}{status}{due}{tags}")
            lines.append(f"       ID: {task.get('id')}")
            if task.get("content"):
                lines.append(f"       {task['content'][:80]}")

    lines.append(f"\n共 {len(tasks)} 个任务")
    return "\n".join(lines)


def format_project_info(project: dict[str, Any]) -> str:
    """格式化项目元数据。"""
    lines = [
        f"项目: {project.get('name', '')} [{project.get('id', '')}]",
        f"类型: {project.get('kind', '')}",
        f"视图: {project.get('viewMode', '')}",
    ]
    if "closed" in project:
        lines.append(f"已关闭: {'是' if project.get('closed') else '否'}")
    if project.get("color"):
        lines.append(f"颜色: {project['color']}")
    if project.get("permission"):
        lines.append(f"权限: {project['permission']}")
    if project.get("sortOrder") is not None:
        lines.append(f"排序值: {project['sortOrder']}")
    if project.get("groupId"):
        lines.append(f"分组ID: {project['groupId']}")
    return "\n".join(lines)


def format_task_detail(task: dict[str, Any]) -> str:
    """格式化单个任务详情。"""
    lines = [
        f"任务: {task.get('title', '')} [{task.get('id', '')}]",
        f"项目ID: {task.get('projectId', '')}",
        f"状态: {'已完成' if task.get('status') == 2 else '未完成'}",
        f"优先级: {PRIORITY_LABELS.get(task.get('priority'), '无').strip() or '无'}",
    ]

    due_date = get_task_date(task, "dueDate")
    if due_date:
        lines.append(f"截止日期: {due_date}")

    start_date = get_task_datetime(task, "startDate")
    if start_date:
        lines.append(f"开始时间: {start_date}")

    completed_time = get_task_datetime(task, "completedTime")
    if completed_time:
        lines.append(f"完成时间: {completed_time}")

    if task.get("timeZone"):
        lines.append(f"时区: {task['timeZone']}")
    if task.get("desc"):
        lines.append(f"描述: {task['desc']}")
    if "isAllDay" in task:
        lines.append(f"全天: {'是' if task.get('isAllDay') else '否'}")
    if task.get("repeatFlag"):
        lines.append(f"重复规则: {task['repeatFlag']}")
    if task.get("sortOrder") is not None:
        lines.append(f"排序值: {task['sortOrder']}")
    if task.get("tags"):
        lines.append(f"标签: {', '.join(task['tags'])}")
    if task.get("reminders"):
        lines.append(f"提醒: {', '.join(task['reminders'])}")
    if task.get("content"):
        lines.append(f"内容: {task['content']}")

    items = task.get("items") or []
    if items:
        lines.append("子项:")
        for item in items:
            status = "✓" if item.get("status") == 1 else " "
            item_parts = [
                f"  [{status}] {item.get('title', '')} [{item.get('id', '')}]",
                f"status={item.get('status')}",
            ]
            if item.get("isAllDay") is not None:
                item_parts.append(f"全天={'是' if item.get('isAllDay') else '否'}")
            if item.get("sortOrder") is not None:
                item_parts.append(f"sortOrder={item.get('sortOrder')}")
            if item.get("timeZone"):
                item_parts.append(f"tz={item.get('timeZone')}")
            item_start = get_task_datetime(item, "startDate")
            if item_start:
                item_parts.append(f"start={item_start}")
            item_completed = get_task_datetime(item, "completedTime")
            if item_completed:
                item_parts.append(f"completed={item_completed}")
            lines.append(" ".join(item_parts))

    return "\n".join(lines)


# --- 转换工具 ---

def repair_argv() -> None:
    """尝试修复模型可能生成的连体命令 (例如 project updateabcd -> project update abcd)。"""
    if len(sys.argv) < 2:
        return

    # 1. 修复分类连体: projectupdate -> project update
    categories = ["project", "task", "search", "auth", "check"]
    cat_arg = sys.argv[1]
    if cat_arg not in categories:
        for cat in categories:
            if cat_arg.startswith(cat) and len(cat_arg) > len(cat):
                remainder = cat_arg[len(cat):]
                sys.argv[1] = cat
                sys.argv.insert(2, remainder)
                break

    # 2. 修复子命令连体: updateabcd -> update abcd
    if len(sys.argv) < 3:
        return

    commands = {
        "project": ["list", "info", "get", "create", "update", "delete", "clear-cache"],
        "task": [
            "get", "create-raw", "create-checklist", "create", 
            "update-raw", "update", "complete", "delete", "move"
        ],
        "search": ["today", "upcoming", "due-range", "completed", "filter", "inbox"],
    }

    category = sys.argv[1]
    if category in commands:
        sub_arg = sys.argv[2]
        valid_subs = commands[category]
        if sub_arg not in valid_subs:
            # 匹配最长的有效子命令前缀
            best_match = ""
            for v in valid_subs:
                if sub_arg.startswith(v) and len(v) > len(best_match):
                    best_match = v
            
            if best_match and len(sub_arg) > len(best_match):
                remainder = sub_arg[len(best_match):]
                sys.argv[2] = best_match
                sys.argv.insert(3, remainder)


def normalize_date(date_str: str | None) -> str | None:
    """标准化日期字符串。"""
    if not date_str:
        return None
    if "T" in date_str:
        return date_str
    offset = datetime.now().astimezone().strftime("%z") or "+0000"
    return f"{date_str}T00:00:00{offset}"


def normalize_range_boundary(date_str: str | None, end_of_day: bool) -> str | None:
    """标准化时间范围边界。"""
    if not date_str:
        return None
    if "T" in date_str:
        return date_str
    offset = datetime.now().astimezone().strftime("%z") or "+0000"
    time_part = "23:59:59" if end_of_day else "00:00:00"
    return f"{date_str}T{time_part}{offset}"


def normalize_date_only(date_str: str) -> str:
    """强制转换为 YYYY-MM-DD 格式。"""
    return datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()


def parse_csv(value: str | None, separator: str = ",") -> list[str]:
    """解析 CSV 字符串。"""
    if not value:
        return []
    return [item.strip() for item in str(value).split(separator) if item.strip()]


def parse_json_input(raw: str | None) -> Any:
    """解析 JSON 输入。"""
    if not raw:
        raise RuntimeError("需要通过 stdin 提供 JSON")
    return json.loads(raw)


def read_stdin() -> str | None:
    """读取标准输入。"""
    if sys.stdin.isatty():
        return None
    content = sys.stdin.read()
    return content or None


# --- 命令执行函数 ---

def command_auth(args: argparse.Namespace) -> None:
    """认证。"""
    run_oauth_flow(args.code)


def command_check(args: argparse.Namespace) -> None:
    """连通性检查。"""
    projects = list_projects(force=True)
    print(f"连接正常。共 {len(projects)} 个项目。")


def command_project_list(args: argparse.Namespace) -> None:
    """列出项目。"""
    print(format_project_list(list_projects(force=args.force)))


def command_project_info(args: argparse.Namespace) -> None:
    """项目元数据。"""
    print(format_project_info(get_project(args.id)))


def command_project_get(args: argparse.Namespace) -> None:
    """项目任务。"""
    print(format_project_detail(get_project_data(args.id, force=args.force)))


def command_project_create(args: argparse.Namespace) -> None:
    """创建项目。"""
    payload: dict[str, Any] = {"name": args.name}
    if args.color:
        payload["color"] = args.color
    if args.kind:
        payload["kind"] = args.kind
    result = create_project(payload)
    print(f"项目创建成功: {result['name']} [{result['id']}]")


def command_project_update(args: argparse.Namespace) -> None:
    """更新项目。"""
    payload: dict[str, Any] = {}
    if args.name:
        payload["name"] = args.name
    if args.color:
        payload["color"] = args.color
    result = update_project(args.id, payload)
    print(f"项目更新成功: {result['name']} [{result['id']}]")


def command_project_delete(args: argparse.Namespace) -> None:
    """删除项目。"""
    delete_project(args.id)
    print(f"项目已删除: {args.id}")


def command_project_clear_cache(args: argparse.Namespace) -> None:
    """清除缓存。"""
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        print("缓存已清除。")
    else:
        print("无缓存。")


def command_task_get(args: argparse.Namespace) -> None:
    """查询任务。"""
    task = get_task(args.project, args.id)
    if not is_task_visible_in_project(args.project, args.id):
        raise RuntimeError("该任务已不在项目可见结果中；可能已删除。")
    print(format_task_detail(task))


def command_task_create(args: argparse.Namespace) -> None:
    """创建任务。"""
    stdin_content = read_stdin()
    payload: dict[str, Any] = {"title": args.title}
    if args.project:
        payload["projectId"] = args.project
    if args.content:
        payload["content"] = args.content
    if stdin_content:
        payload["content"] = stdin_content
    if args.due:
        payload["dueDate"] = normalize_date(args.due)
    if args.priority is not None:
        payload["priority"] = args.priority
    if args.tags:
        payload["tags"] = parse_csv(args.tags)

    result = create_task(payload)
    print(f"任务创建成功: {result['title']} [{result['id']}] 项目ID: {result.get('projectId')}")


def command_task_create_raw(args: argparse.Namespace) -> None:
    """JSON 创建任务。"""
    payload = parse_json_input(read_stdin())
    if not isinstance(payload, dict):
        raise RuntimeError("需要 JSON object")
    result = create_task(payload)
    print(f"高级任务创建成功: {result['title']} [{result['id']}]")


def command_task_create_checklist(args: argparse.Namespace) -> None:
    """创建清单。"""
    items = parse_csv(args.items, separator="|")
    payload: dict[str, Any] = {
        "title": args.title,
        "projectId": args.project,
        "items": [{"title": item, "status": 0} for item in items],
    }
    if args.content:
        payload["content"] = args.content
    if args.due:
        payload["dueDate"] = normalize_date(args.due)
    if args.priority is not None:
        payload["priority"] = args.priority

    result = create_task(payload)
    print(f"Checklist 创建成功: {result['title']} [{result['id']}]")


def command_task_update(args: argparse.Namespace) -> None:
    """更新任务。"""
    payload: dict[str, Any] = {}
    if args.title:
        payload["title"] = args.title
    if args.content:
        payload["content"] = args.content
    if args.due:
        payload["dueDate"] = normalize_date(args.due)
    if args.priority is not None:
        payload["priority"] = args.priority
    if args.tags:
        payload["tags"] = parse_csv(args.tags)

    result = update_task(args.id, args.project, payload)
    print(f"任务更新成功: {result['title']} [{result['id']}]")


def command_task_update_raw(args: argparse.Namespace) -> None:
    """JSON 更新任务。"""
    payload = parse_json_input(read_stdin())
    if not isinstance(payload, dict):
        raise RuntimeError("需要 JSON object")
    project_id = payload.get("projectId") or args.project
    if not project_id:
        raise RuntimeError("必须指定 projectId (通过参数或 JSON)")
    result = update_task(args.id, project_id, payload)
    print(f"高级任务更新成功: {result['title']} [{result['id']}]")


def command_task_complete(args: argparse.Namespace) -> None:
    """完成任务。"""
    complete_task(args.project, args.id)
    print(f"任务已完成: {args.id}")


def command_task_delete(args: argparse.Namespace) -> None:
    """删除任务。"""
    delete_task(args.project, args.id)
    if is_task_visible_in_project(args.project, args.id):
        print(f"删除请求已发送，但任务仍可见: {args.id}")
        return
    print(f"任务已删除: {args.id}")


def command_task_move(args: argparse.Namespace) -> None:
    """移动任务。"""
    result = move_tasks(
        [
            {
                "fromProjectId": args.from_project,
                "toProjectId": args.to_project,
                "taskId": args.id,
            }
        ]
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_search_today(args: argparse.Namespace) -> None:
    """今日任务。"""
    print(format_task_list(get_today_tasks(force=args.force), "今日待办"))


def command_search_upcoming(args: argparse.Namespace) -> None:
    """未来任务。"""
    start = datetime.now().date()
    end = start + timedelta(days=args.days - 1)
    tasks = get_due_range_tasks(start.isoformat(), end.isoformat(), project_id=args.project, force=args.force)
    print(format_task_list(tasks, f"未来 {args.days} 天到期任务 ({start.isoformat()} ~ {end.isoformat()})"))


def command_search_due_range(args: argparse.Namespace) -> None:
    """区间到期。"""
    start = normalize_date_only(args.start)
    end = normalize_date_only(args.end)
    if start > end:
        raise RuntimeError("开始日期不能晚于结束日期")
    tasks = get_due_range_tasks(start, end, project_id=args.project, force=args.force)
    print(format_task_list(tasks, f"到期任务 ({start} ~ {end})"))


def command_search_completed(args: argparse.Namespace) -> None:
    """已完成查询。"""
    start = normalize_date_only(args.start)
    end = normalize_date_only(args.end)
    if start > end:
        raise RuntimeError("开始日期不能晚于结束日期")
    project_ids = [args.project] if args.project else None
    tasks = list_completed_tasks(project_ids=project_ids, start_date=start, end_date=end)
    if args.project:
        project_name = get_project_data(args.project, force=args.force).get("project", {}).get("name", args.project)
        for task in tasks:
            task.setdefault("_projectName", project_name)
    print(format_task_list(tasks, f"已完成任务 ({start} ~ {end})"))


def command_search_filter(args: argparse.Namespace) -> None:
    """高级筛选。"""
    payload: dict[str, Any] = {}
    if args.project:
        payload["projectIds"] = [args.project]
    if args.start:
        payload["startDate"] = normalize_range_boundary(args.start, end_of_day=False)
    if args.end:
        payload["endDate"] = normalize_range_boundary(args.end, end_of_day=True)
    if args.priority:
        payload["priority"] = [int(item) for item in parse_csv(args.priority)]
    if args.tags:
        payload["tag"] = parse_csv(args.tags)
    if args.status:
        payload["status"] = [int(item) for item in parse_csv(args.status)]

    if not payload:
        raise RuntimeError("需要提供至少一个筛选条件")

    tasks = filter_tasks(payload)
    print(format_task_list(tasks, "筛选结果"))


def command_search_inbox(args: argparse.Namespace) -> None:
    """收集箱。"""
    project, tasks = get_inbox_data(force=args.force)
    print(format_task_list(tasks, f"收集箱 ({project['name']})"))


# --- CLI 入口逻辑 ---

def setup_args() -> argparse.ArgumentParser:
    """配置命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="Dida365 CLI 工具")
    subparsers = parser.add_subparsers(dest="command", required=True, help="主命令分类")

    # Auth
    auth_parser = subparsers.add_parser("auth", help="OAuth 2.0 授权认证")
    auth_parser.add_argument("--code", help="手动提供授权码")
    auth_parser.set_defaults(func=command_auth)

    # Check
    check_parser = subparsers.add_parser("check", help="检查 API 连接状态")
    check_parser.set_defaults(func=command_check)

    # Project
    project_parser = subparsers.add_parser("project", help="项目管理 (list/get/create/...)")
    project_sub = project_parser.add_subparsers(dest="sub", required=True, help="项目子命令")
    
    p_list = project_sub.add_parser("list", help="列出所有项目")
    p_list.add_argument("--force", action="store_true", help="强制从 API 更新")
    p_list.set_defaults(func=command_project_list)
    
    p_info = project_sub.add_parser("info", help="查看项目元数据")
    p_info.add_argument("id", help="项目 ID")
    p_info.set_defaults(func=command_project_info)
    
    p_get = project_sub.add_parser("get", help="查看项目任务详情")
    p_get.add_argument("id", help="项目 ID")
    p_get.add_argument("--force", action="store_true", help="强制从 API 更新")
    p_get.set_defaults(func=command_project_get)
    
    p_create = project_sub.add_parser("create", help="创建新项目")
    p_create.add_argument("name", help="项目名称")
    p_create.add_argument("--color", help="项目颜色")
    p_create.add_argument("--kind", help="项目类型")
    p_create.set_defaults(func=command_project_create)
    
    p_update = project_sub.add_parser("update", help="更新项目")
    p_update.add_argument("id", help="项目 ID")
    p_update.add_argument("--name", help="新名称")
    p_update.add_argument("--color", help="新颜色")
    p_update.set_defaults(func=command_project_update)
    
    p_delete = project_sub.add_parser("delete", help="删除项目")
    p_delete.add_argument("id", help="项目 ID")
    p_delete.set_defaults(func=command_project_delete)

    project_sub.add_parser("clear-cache", help="清除本地缓存数据").set_defaults(func=command_project_clear_cache)

    # Task
    task_parser = subparsers.add_parser("task", help="任务管理 (get/create/complete/...)")
    task_sub = task_parser.add_subparsers(dest="sub", required=True, help="任务子命令")
    
    t_get = task_sub.add_parser("get", help="查看任务详情")
    t_get.add_argument("project", help="项目 ID")
    t_get.add_argument("id", help="任务 ID")
    t_get.set_defaults(func=command_task_get)
    
    t_create = task_sub.add_parser("create", help="创建任务")
    t_create.add_argument("title", help="任务标题")
    t_create.add_argument("--project", help="项目 ID")
    t_create.add_argument("--content", help="任务描述")
    t_create.add_argument("--due", help="截止日期 (YYYY-MM-DD)")
    t_create.add_argument("--priority", type=int, choices=[0, 1, 3, 5], help="优先级 (0/1/3/5)")
    t_create.add_argument("--tags", help="标签 (逗号分隔)")
    t_create.set_defaults(func=command_task_create)

    task_sub.add_parser("create-raw", help="从 stdin JSON 创建高级任务").set_defaults(func=command_task_create_raw)

    t_checklist = task_sub.add_parser("create-checklist", help="创建清单任务")
    t_checklist.add_argument("title", help="标题")
    t_checklist.add_argument("--project", required=True, help="项目 ID")
    t_checklist.add_argument("--items", required=True, help='子项，用 "|" 分隔')
    t_checklist.add_argument("--content", help="描述")
    t_checklist.add_argument("--due", help="日期")
    t_checklist.add_argument("--priority", type=int, choices=[0, 1, 3, 5])
    t_checklist.set_defaults(func=command_task_create_checklist)
    
    t_update = task_sub.add_parser("update", help="更新任务")
    t_update.add_argument("project", help="项目 ID")
    t_update.add_argument("id", help="任务 ID")
    t_update.add_argument("--title", help="新标题")
    t_update.add_argument("--content", help="新内容")
    t_update.add_argument("--due", help="新日期")
    t_update.add_argument("--priority", type=int, choices=[0, 1, 3, 5])
    t_update.add_argument("--tags", help="新标签")
    t_update.set_defaults(func=command_task_update)

    t_update_raw = task_sub.add_parser("update-raw", help="从 stdin JSON 更新高级任务")
    t_update_raw.add_argument("id", help="任务 ID")
    t_update_raw.add_argument("--project", help="项目 ID")
    t_update_raw.set_defaults(func=command_task_update_raw)
    
    t_complete = task_sub.add_parser("complete", help="完成任务")
    t_complete.add_argument("project", help="项目 ID")
    t_complete.add_argument("id", help="任务 ID")
    t_complete.set_defaults(func=command_task_complete)
    
    t_delete = task_sub.add_parser("delete", help="删除任务")
    t_delete.add_argument("project", help="项目 ID")
    t_delete.add_argument("id", help="任务 ID")
    t_delete.set_defaults(func=command_task_delete)
    
    t_move = task_sub.add_parser("move", help="移动任务")
    t_move.add_argument("from_project", help="源项目 ID")
    t_move.add_argument("to_project", help="目标项目 ID")
    t_move.add_argument("id", help="任务 ID")
    t_move.set_defaults(func=command_task_move)

    # Search
    search_parser = subparsers.add_parser("search", help="查询与筛选 (today/upcoming/filter/...)")
    search_sub = search_parser.add_subparsers(dest="sub", required=True, help="查询子命令")
    
    s_today = search_sub.add_parser("today", help="今日到期待办")
    s_today.add_argument("--force", action="store_true", help="强制更新")
    s_today.set_defaults(func=command_search_today)
    
    s_upcoming = search_sub.add_parser("upcoming", help="未来几天到期待办")
    s_upcoming.add_argument("days", type=int, nargs="?", default=7, help="天数 (默认 7)")
    s_upcoming.add_argument("--project", help="限定项目 ID")
    s_upcoming.add_argument("--force", action="store_true", help="强制更新")
    s_upcoming.set_defaults(func=command_search_upcoming)
    
    s_range = search_sub.add_parser("due-range", help="指定日期区间到期任务")
    s_range.add_argument("start", help="开始日期 (YYYY-MM-DD)")
    s_range.add_argument("end", help="结束日期 (YYYY-MM-DD)")
    s_range.add_argument("--project", help="限定项目 ID")
    s_range.add_argument("--force", action="store_true", help="强制更新")
    s_range.set_defaults(func=command_search_due_range)
    
    s_completed = search_sub.add_parser("completed", help="查看已完成任务")
    s_completed.add_argument("start", help="开始日期")
    s_completed.add_argument("end", help="结束日期")
    s_completed.add_argument("--project", help="限定项目 ID")
    s_completed.add_argument("--force", action="store_true", help="强制更新")
    s_completed.set_defaults(func=command_search_completed)
    
    s_filter = search_sub.add_parser("filter", help="高级筛选查询")
    s_filter.add_argument("--project", help="项目 ID")
    s_filter.add_argument("--start", help="到期开始")
    s_filter.add_argument("--end", help="到期结束")
    s_filter.add_argument("--priority", help="优先级 (如 0,3)")
    s_filter.add_argument("--tags", help="标签")
    s_filter.add_argument("--status", help="状态 (0=未完成, 2=完成)")
    s_filter.set_defaults(func=command_search_filter)
    
    s_inbox = search_sub.add_parser("inbox", help="查看收集箱任务")
    s_inbox.add_argument("--force", action="store_true", help="强制更新")
    s_inbox.set_defaults(func=command_search_inbox)

    return parser


def main() -> None:
    load_env_file()
    repair_argv()
    parser = setup_args()
    args = parser.parse_args()
    
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        sys.exit(1)
