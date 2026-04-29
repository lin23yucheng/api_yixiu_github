import json
import os


def normalize_task_file_path(file_path):
    path = str(file_path or "").strip().strip('"').strip("'").replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def guess_task_name(file_path, labels=None):
    labels = labels or {}
    file_name = os.path.basename(normalize_task_file_path(file_path))
    if file_name in labels:
        return labels[file_name]
    base = os.path.splitext(file_name)[0]
    if base.startswith("test_"):
        base = base[5:]
    return base.replace("_", "-")


def discover_test_modules(project_root, labels=None, excluded=None):
    testcase_dir = os.path.join(project_root, "testcase")
    excluded = set(excluded or ())
    modules = []

    if not os.path.isdir(testcase_dir):
        return modules

    for root, _, files in os.walk(testcase_dir):
        for file_name in files:
            if not file_name.endswith(".py") or file_name in excluded:
                continue
            abs_path = os.path.join(root, file_name)
            rel_path = os.path.relpath(abs_path, project_root).replace("\\", "/")
            modules.append({
                "name": guess_task_name(rel_path, labels),
                "file": rel_path,
                "deps": [],
                "require_success": False,
            })

    modules.sort(key=lambda item: item["file"])
    return modules


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _normalize_deps(deps):
    if deps is None:
        return []
    if isinstance(deps, str):
        deps = [deps]
    if not isinstance(deps, (list, tuple, set)):
        raise ValueError(f"deps 必须是列表或字符串: {deps!r}")
    return [normalize_task_file_path(dep) for dep in deps if normalize_task_file_path(dep)]


def load_task_dependency_config(project_root, config_path=None):
    config_path = config_path or os.path.join(project_root, "config", "task_dependencies.json")
    if not os.path.exists(config_path):
        return []

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        raw_tasks = data
        default_require_success = True
        dependencies = {}
    elif isinstance(data, dict):
        raw_tasks = data.get("tasks") or []
        default_require_success = _as_bool(data.get("require_success"), True)
        dependencies = data.get("dependencies") or {}
    else:
        raise ValueError(f"任务依赖配置格式错误: {config_path}")

    tasks = []
    if not isinstance(dependencies, dict):
        raise ValueError("dependencies 必须是对象，格式为 {file: [deps...]}")

    for file_path, deps in dependencies.items():
        deps = _normalize_deps(deps)
        tasks.append({
            "file": normalize_task_file_path(file_path),
            "deps": deps,
            "require_success": default_require_success if deps else False,
        })

    for item in raw_tasks:
        if isinstance(item, str):
            tasks.append({
                "file": normalize_task_file_path(item),
                "deps": [],
                "require_success": False,
            })
            continue
        if not isinstance(item, dict):
            raise ValueError(f"任务配置项必须是字符串或对象: {item!r}")

        deps = _normalize_deps(item.get("deps"))
        tasks.append({
            "name": item.get("name"),
            "file": normalize_task_file_path(item.get("file")),
            "deps": deps,
            "require_success": _as_bool(
                item.get("require_success"),
                default_require_success if deps else False,
            ),
        })

    for task in tasks:
        if not task.get("file"):
            raise ValueError("任务依赖配置中存在空 file")

    return tasks


def _task_file_exists(project_root, file_path):
    if not project_root:
        return True
    abs_path = os.path.join(project_root, normalize_task_file_path(file_path).replace("/", os.sep))
    return os.path.exists(abs_path)


def _resolve_file_alias(file_path, task_map, project_root=None):
    raw = str(file_path or "").strip().strip('"').strip("'")
    normalized = normalize_task_file_path(raw)
    if normalized in task_map:
        return normalized

    if project_root and os.path.isabs(raw):
        abs_path = os.path.abspath(raw)
        root = os.path.abspath(project_root)
        try:
            if os.path.commonpath([root, abs_path]) == root:
                rel_path = os.path.relpath(abs_path, root).replace("\\", "/")
                if rel_path in task_map:
                    return rel_path
                normalized = rel_path
        except ValueError:
            pass

    if "/" not in normalized:
        matches = [file for file in task_map if os.path.basename(file) == normalized]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"任务文件名不唯一，请使用相对路径: {normalized}")

    return normalized


def build_together_tasks(project_root, labels=None, config_path=None, excluded=None):
    discovered = discover_test_modules(project_root, labels=labels, excluded=excluded)
    configured = load_task_dependency_config(project_root, config_path=config_path)

    task_map = {task["file"]: dict(task) for task in discovered}
    ordered_files = []

    for item in configured:
        file_path = item["file"]
        task = dict(task_map.get(file_path) or {
            "name": guess_task_name(file_path, labels),
            "file": file_path,
            "deps": [],
            "require_success": False,
        })
        task["deps"] = list(item.get("deps") or [])
        task["require_success"] = _as_bool(item.get("require_success"), bool(task["deps"]))
        if item.get("name"):
            task["name"] = item["name"]
        task_map[file_path] = task
        if file_path not in ordered_files:
            ordered_files.append(file_path)

        for dep in task["deps"]:
            if dep not in task_map:
                task_map[dep] = {
                    "name": guess_task_name(dep, labels),
                    "file": dep,
                    "deps": [],
                    "require_success": False,
                }
                ordered_files.append(dep)

    for task in discovered:
        if task["file"] not in ordered_files:
            ordered_files.append(task["file"])

    _validate_task_graph(task_map, project_root)
    return [dict(task_map[file_path]) for file_path in ordered_files]


def _validate_task_graph(task_map, project_root=None):
    for file_path, task in task_map.items():
        if not _task_file_exists(project_root, file_path):
            raise ValueError(f"并行任务文件不存在: {file_path}")
        for dep in task.get("deps") or []:
            if dep not in task_map:
                raise ValueError(f"任务 {file_path} 的依赖未定义: {dep}")
            if not _task_file_exists(project_root, dep):
                raise ValueError(f"任务 {file_path} 的依赖文件不存在: {dep}")

    visited = set()
    visiting = []

    def visit(file_path):
        if file_path in visiting:
            cycle = visiting[visiting.index(file_path):] + [file_path]
            raise ValueError(f"任务依赖存在循环: {' -> '.join(cycle)}")
        if file_path in visited:
            return

        visiting.append(file_path)
        for dep in task_map[file_path].get("deps") or []:
            visit(dep)
        visiting.pop()
        visited.add(file_path)

    for file_path in task_map:
        visit(file_path)


def resolve_task_dependencies(selected_files, tasks, project_root=None, labels=None):
    task_map = {task["file"]: dict(task) for task in tasks}
    selected = list(selected_files or [task["file"] for task in tasks])
    resolved_order = []
    visited = set()
    visiting = []

    def ensure_task(file_path):
        if file_path in task_map:
            return
        if not _task_file_exists(project_root, file_path):
            raise ValueError(f"并行任务不存在: {file_path}")
        task_map[file_path] = {
            "name": guess_task_name(file_path, labels),
            "file": file_path,
            "deps": [],
            "require_success": False,
        }

    def add_with_deps(file_path):
        file_path = _resolve_file_alias(file_path, task_map, project_root=project_root)
        ensure_task(file_path)

        if file_path in visiting:
            cycle = visiting[visiting.index(file_path):] + [file_path]
            raise ValueError(f"任务依赖存在循环: {' -> '.join(cycle)}")
        if file_path in visited:
            return

        visiting.append(file_path)
        for dep in task_map[file_path].get("deps") or []:
            add_with_deps(dep)
        visiting.pop()

        visited.add(file_path)
        resolved_order.append(file_path)

    for item in selected:
        add_with_deps(item)

    return [dict(task_map[file_path]) for file_path in resolved_order]
