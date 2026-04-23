import os
import sys
import time
import argparse
import queue
import threading
import subprocess
import traceback
import multiprocessing
import importlib
import importlib.util
import contextlib
import functools
import http.server
import re
import socket
import tkinter as tk
from tkinter import ttk, messagebox
from io import UnsupportedOperation
from pathlib import Path
from urllib.parse import urlparse, unquote
from urllib.request import urlopen
from urllib.error import URLError
import webbrowser

import psutil


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RUN_SCRIPT = os.path.join(PROJECT_ROOT, "test_run.py")
ALLURE_REPORT_LINE_RE = re.compile(r"ALLURE_REPORT_URL=(file://\S+)")
ALLURE_REPORT_MISSING_RE = re.compile(r"ALLURE_REPORT_MISSING=(.+)")
ALLURE_CLI_MISSING_RE = re.compile(r"ALLURE_CLI_MISSING=(.+)")
ALLURE_GENERATE_ERR_RE = re.compile(r"ALLURE_GENERATE_(?:ERROR|EXCEPTION)=(.+)")


def _load_test_run_module():
    try:
        return importlib.import_module("test_run")
    except ModuleNotFoundError as exc:
        # 仅处理 test_run 本体缺失；若是其内部依赖缺失应直接抛出真实错误
        if getattr(exc, "name", None) and exc.name != "test_run":
            raise

    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        exe_dir = os.path.dirname(sys.executable)
        candidates.extend([
            os.path.join(meipass, "test_run.py") if meipass else None,
            os.path.join(exe_dir, "test_run.py"),
            RUN_SCRIPT,
        ])
    else:
        candidates.append(RUN_SCRIPT)

    for path in candidates:
        if path and os.path.exists(path):
            module_dir = os.path.dirname(path)
            if module_dir and module_dir not in sys.path:
                sys.path.insert(0, module_dir)
            spec = importlib.util.spec_from_file_location("test_run", path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module

    if getattr(sys, "frozen", False):
        raise ModuleNotFoundError(
            "打包环境未找到 test_run，请在打包参数中加入 --hidden-import test_run，"
            "并添加 --add-data test_run.py;. 后重新打包"
        )
    raise ModuleNotFoundError("无法加载 test_run 模块，请确认 test_run.py 存在")


TEST_RUN = _load_test_run_module()


def _maybe_run_internal_worker_cli(argv=None):
    """Hidden worker entry for frozen subprocess execution (no GUI)."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--internal-worker", action="store_true")
    parser.add_argument("--worker-test-file", default=None)
    parser.add_argument("--worker-allure-results", default=None)
    args, _ = parser.parse_known_args(argv)

    if not args.internal_worker:
        return False

    if not args.worker_test_file or not args.worker_allure_results:
        print("WORKER_PARAM_ERROR=missing worker-test-file or worker-allure-results")
        sys.exit(2)

    try:
        TEST_RUN.ensure_runtime_env_vars()
        exit_code = TEST_RUN.execute_test(args.worker_test_file, args.worker_allure_results)
    except Exception as exc:
        print(f"WORKER_EXCEPTION={exc}\n{traceback.format_exc()}")
        exit_code = 2

    print(f"WORKER_EXIT_CODE={exit_code}")
    sys.exit(exit_code)


class QueueWriter:
    def __init__(self, out_queue):
        self.out_queue = out_queue

    def write(self, text):
        if text:
            self.out_queue.put(text)

    def flush(self):
        return

    def fileno(self):
        raise UnsupportedOperation("fileno")

    def isatty(self):
        return False


class ClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("一休云测试客户端")
        # self.root.geometry("1080x720")
        self.root.minsize(1080, 720)
        self.root.state('zoomed')

        self.process = None
        self.run_thread = None
        self.output_queue = queue.Queue()
        self.latest_report_url = None
        self.latest_report_error = None
        self.report_http_server = None
        self.report_http_thread = None
        self.report_http_port = None
        self.report_http_dir = None

        self.env_var = tk.StringVar(value="fat")
        self.mode_var = tk.StringVar(value="order")

        self.order_vars = {}
        self.order_selection_order = []

        self.together_vars = {}
        self.together_manual_selected = set()
        self.together_auto_required_count = {}
        self.together_task_map = {item["file"]: item for item in TEST_RUN.TOGETHER_TASKS}
        self.together_dep_closure_map = self._build_together_dep_closure_map()

        self.picture_num_var = tk.IntVar(value=self._safe_default_picture_num("fat"))
        self.address_no_var = tk.IntVar(value=1)
        self.threads_var = tk.IntVar(value=1)
        yixiu_defaults = self._safe_yixiu_values("fat")
        self.space_name_var = tk.StringVar(value=yixiu_defaults["space_name"])
        self.space_id_var = tk.StringVar(value=yixiu_defaults["space_id"])
        self.product_code_var = tk.StringVar(value=yixiu_defaults["product_code"])
        self.report_var = tk.StringVar(value="")

        self._build_ui()
        self._refresh_mode_area()
        self._poll_output()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_toggle_button(self, parent, text, variable, command):
        btn = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            command=command,
            indicatoron=False,
            anchor="w",
            padx=10,
            pady=6,
            relief="raised",
            bd=1,
            selectcolor="#4472C4",
            activebackground="#E8F4F8",
            bg="white",
            activeforeground="#1F4E78",
            font=("Microsoft YaHei UI", 10),
            cursor="hand2"
        )
        btn.pack(fill=tk.X, pady=3)
        return btn

    def _create_grid_toggle_button(self, parent, text, variable, command, row, column):
        btn = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            command=command,
            indicatoron=False,
            anchor="w",
            padx=10,
            pady=6,
            relief="raised",
            bd=1,
            selectcolor="#4472C4",
            activebackground="#E8F4F8",
            bg="white",
            activeforeground="#1F4E78",
            font=("Microsoft YaHei UI", 10),
            cursor="hand2"
        )
        btn.grid(row=row, column=column, sticky="ew", padx=3, pady=3)
        return btn

    def _safe_default_picture_num(self, env):
        try:
            return TEST_RUN.get_picture_num_by_env(env)
        except Exception:
            return 1

    def _safe_yixiu_values(self, env):
        try:
            values = TEST_RUN.get_yixiu_values_by_env(env)
            return {
                "space_name": values.get("space_name", ""),
                "space_id": values.get("space_id", ""),
                "product_code": values.get("product_code", ""),
            }
        except Exception:
            return {"space_name": "", "space_id": "", "product_code": ""}

    def _build_together_dep_closure_map(self):
        closure_map = {}
        for file_path in self.together_task_map:
            deps = set()
            try:
                resolved = TEST_RUN.resolve_together_tasks([file_path])
                deps = {item["file"] for item in resolved if item["file"] != file_path}
            except Exception:
                # 回退到本地DFS，确保递归依赖仍可用
                stack = list((self.together_task_map.get(file_path) or {}).get("deps") or [])
                while stack:
                    dep = stack.pop()
                    if dep in deps:
                        continue
                    deps.add(dep)
                    dep_task = self.together_task_map.get(dep) or {}
                    stack.extend(dep_task.get("deps") or [])
            closure_map[file_path] = deps
        return closure_map

    def _build_ui(self):
        self._setup_style()

        # === 顶部控制区 ===
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, padx=10, pady=(10, 0))

        env_group = ttk.LabelFrame(top, text="环境选择", padding=10, style="Option.TLabelframe")
        env_group.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Radiobutton(env_group, text="FAT-测试环境", variable=self.env_var, value="fat", command=self._on_env_change).pack(side=tk.LEFT, padx=8)
        ttk.Radiobutton(env_group, text="PROD-生产环境", variable=self.env_var, value="prod", command=self._on_env_change).pack(side=tk.LEFT, padx=8)

        mode_group = ttk.LabelFrame(top, text="执行模式", padding=10, style="Option.TLabelframe")
        mode_group.pack(side=tk.LEFT, padx=(0, 15), expand=True)
        ttk.Radiobutton(mode_group, text="顺序执行", variable=self.mode_var, value="order", command=self._refresh_mode_area).pack(side=tk.LEFT, padx=8)
        ttk.Radiobutton(mode_group, text="并行执行", variable=self.mode_var, value="together", command=self._refresh_mode_area).pack(side=tk.LEFT, padx=8)
        ttk.Radiobutton(mode_group, text="推图", variable=self.mode_var, value="push", command=self._refresh_mode_area).pack(side=tk.LEFT, padx=8)

        # === 全局一休参数（对所有模式生效）===
        yixiu_group = ttk.LabelFrame(self.root, text="一休基础参数(全模式生效)", padding=10, style="Option.TLabelframe")
        yixiu_group.pack(fill=tk.X, padx=10, pady=(8, 0))
        ttk.Label(yixiu_group, text="空间名称:", font=("Microsoft YaHei UI", 10)).grid(row=0, column=0, sticky=tk.W, padx=8, pady=4)
        ttk.Entry(yixiu_group, textvariable=self.space_name_var, width=26, font=("Microsoft YaHei UI", 10)).grid(row=0, column=1, sticky=tk.W, padx=8, pady=4)
        ttk.Label(yixiu_group, text="空间ID:", font=("Microsoft YaHei UI", 10)).grid(row=0, column=2, sticky=tk.W, padx=8, pady=4)
        ttk.Entry(yixiu_group, textvariable=self.space_id_var, width=26, font=("Microsoft YaHei UI", 10)).grid(row=0, column=3, sticky=tk.W, padx=8, pady=4)
        ttk.Label(yixiu_group, text="产品编号:", font=("Microsoft YaHei UI", 10)).grid(row=0, column=4, sticky=tk.W, padx=8, pady=4)
        ttk.Entry(yixiu_group, textvariable=self.product_code_var, width=22, font=("Microsoft YaHei UI", 10)).grid(row=0, column=5, sticky=tk.W, padx=8, pady=4)

        # === 执行控制区 ===
        action = ttk.Frame(self.root)
        action.pack(fill=tk.X, padx=10, pady=8)

        self.start_btn = ttk.Button(action, text="▶  开始执行", command=self.start_execution, style="Action.TButton")
        self.start_btn.pack(side=tk.LEFT, padx=4)

        self.stop_btn = ttk.Button(action, text="⏹  停止执行", command=self.stop_execution, state=tk.DISABLED, style="Action.TButton")
        self.stop_btn.pack(side=tk.LEFT, padx=4)

        self.reset_btn = ttk.Button(action, text="↺  重置选择", command=self.reset_selection, style="Action.TButton")
        self.reset_btn.pack(side=tk.LEFT, padx=4)

        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10)
        ttk.Label(status_frame, text="执行状态:", font=("Microsoft YaHei UI", 10, "bold")).pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="待执行")
        self.status_label = tk.Label(
            status_frame,
            textvariable=self.status_var,
            font=("Microsoft YaHei UI", 10),
            fg="#1F1F1F",
            bg="#F5F5F5",
            anchor="w",
        )
        self.status_label.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(status_frame, text="  Allure报告:", font=("Microsoft YaHei UI", 10, "bold")).pack(side=tk.LEFT, padx=(16, 0))
        report_label = tk.Label(
            status_frame,
            textvariable=self.report_var,
            font=("Consolas", 9),
            fg="#1F4E78",
            bg="#F5F5F5",
            cursor="hand2",
            anchor="w",
        )
        report_label.pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)
        report_label.bind("<Button-1>", self._open_report_url)

        # === 可拖拽主体区 ===
        body = tk.PanedWindow(
            self.root,
            orient=tk.VERTICAL,
            sashrelief=tk.RAISED,
            sashwidth=8,
            showhandle=True,
            handlesize=8,
            bg="#D6D6D6",
            bd=0,
        )
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 10))

        # 选项区（上部）
        mode_panel = ttk.Frame(body)
        self.mode_frame = ttk.Frame(mode_panel)
        self.mode_frame.pack(fill=tk.BOTH, expand=True)
        body.add(mode_panel, minsize=260, stretch="always")

        # 日志区（下部）
        log_frame = ttk.LabelFrame(body, text="执行日志", padding=10, style="Log.TLabelframe")

        log_content = ttk.Frame(log_frame)
        log_content.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_content,
            wrap=tk.WORD,
            height=12,
            font=("Consolas", 9),
            bg="#F9F9F9",
            fg="#1F1F1F",
            insertbackground="#4472C4",
            selectbackground="#4472C4"
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.log_text.bind("<ButtonPress-2>", lambda event: self.log_text.scan_mark(event.x, event.y))
        self.log_text.bind("<B2-Motion>", lambda event: self.log_text.scan_dragto(event.x, event.y, gain=1))

        scrollbar = ttk.Scrollbar(log_content, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        body.add(log_frame, minsize=180)

    def _set_status(self, text, color=None):
        self.status_var.set(text)
        if hasattr(self, "status_label"):
            self.status_label.configure(fg=color or "#1F1F1F")

    def _setup_style(self):
        style = ttk.Style(self.root)

        # 颜色定义
        primary_bg = "#F5F5F5"
        button_fg = "white"

        # 主窗口背景
        self.root.configure(bg=primary_bg)

        # LabelFrame 样式（选项区）
        style.configure(
            "Option.TLabelframe",
            background=primary_bg,
            padding=10,
            relief="ridge"
        )
        style.configure(
            "Option.TLabelframe.Label",
            font=("Microsoft YaHei UI", 11, "bold"),
            background=primary_bg,
            foreground="#1F4E78"
        )

        # LabelFrame 样式（日志区）
        style.configure(
            "Log.TLabelframe",
            background=primary_bg,
            padding=10,
            relief="sunken"
        )
        style.configure(
            "Log.TLabelframe.Label",
            font=("Microsoft YaHei UI", 11, "bold"),
            background=primary_bg,
            foreground="#2F5496"
        )

        # 按钮样式
        style.configure(
            "Action.TButton",
            padding=(16, 6),
            font=("Microsoft YaHei UI", 10)
        )
        style.map(
            "Action.TButton",
            foreground=[("pressed", button_fg), ("active", button_fg)],
            background=[("pressed", "#2F5496"), ("active", "#5B8FD9")]
        )

        style.configure(
            "ReadonlyGrpc.TEntry",
            foreground="#666666",
            fieldbackground="#D9D9D9",
            background="#D9D9D9"
        )
        style.map(
            "ReadonlyGrpc.TEntry",
            fieldbackground=[("readonly", "#D9D9D9")],
            foreground=[("readonly", "#666666")]
        )

        # 单选按钮
        style.configure(
            "TRadiobutton",
            font=("Microsoft YaHei UI", 10),
            background=primary_bg,
            padding=4
        )

        # 标签
        style.configure("TLabel", background=primary_bg, font=("Microsoft YaHei UI", 10))

        # Frame 背景
        style.configure("TFrame", background=primary_bg)

    def _build_scrollable_checklist(self, parent, title):
        group = ttk.LabelFrame(parent, text=title, padding=10, style="Option.TLabelframe")
        holder = ttk.Frame(group)
        holder.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(
            holder,
            highlightthickness=1,
            highlightbackground="#D0D0D0",
            bg="white"
        )
        scrollbar = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        content = ttk.Frame(canvas, padding=4)
        win_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_content_config(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_config(event):
            canvas.itemconfigure(win_id, width=event.width)

        def _on_mousewheel(event):
            delta = int(-1 * (event.delta / 120))
            if delta:
                canvas.yview_scroll(delta, "units")

        def _bind_mousewheel(_event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(_event):
            canvas.unbind_all("<MouseWheel>")

        content.bind("<Configure>", _on_content_config)
        canvas.bind("<Configure>", _on_canvas_config)
        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        return group, content

    def _on_env_change(self):
        env = self.env_var.get()
        self.picture_num_var.set(self._safe_default_picture_num(env))
        self.address_no_var.set(1 if env == "fat" else 2)
        yixiu_values = self._safe_yixiu_values(env)
        self.space_name_var.set(yixiu_values["space_name"])
        self.space_id_var.set(yixiu_values["space_id"])
        self.product_code_var.set(yixiu_values["product_code"])

    def _refresh_mode_area(self):
        for child in self.mode_frame.winfo_children():
            child.destroy()

        mode = self.mode_var.get()
        if mode == "order":
            self._build_order_area()
        elif mode == "together":
            self._build_together_area()
        else:
            self._build_push_area()

    def _build_order_area(self):
        left, left_content = self._build_scrollable_checklist(self.mode_frame, "📋 待执行模块")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        right = ttk.LabelFrame(self.mode_frame, text="📋 执行顺序", padding=10, style="Option.TLabelframe")
        right.configure(width=360)
        right.pack(side=tk.LEFT, fill=tk.Y)
        right.pack_propagate(False)

        columns = 4
        for col in range(columns):
            left_content.grid_columnconfigure(col, weight=1, uniform="order_col")

        for idx, item in enumerate(TEST_RUN.ORDER_TEST_MODULES):
            file_path = item["file"]
            var = self.order_vars.get(file_path)
            if var is None:
                var = tk.IntVar(value=0)
                self.order_vars[file_path] = var

            self._create_grid_toggle_button(
                left_content,
                text=item['name'],
                variable=var,
                command=lambda f=file_path: self._toggle_order_item(f),
                row=idx // columns,
                column=idx % columns,
            )

        self.order_listbox = tk.Listbox(
            right,
            height=14,
            font=("Microsoft YaHei UI", 10),
            bg="white",
            fg="#1F4E78",
            selectmode=tk.SINGLE,
            activestyle="none",
            selectbackground="#4472C4",
            selectforeground="white",
            bd=1,
            relief="solid"
        )
        self.order_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        order_scrollbar = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.order_listbox.yview)
        order_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.order_listbox.configure(yscrollcommand=order_scrollbar.set)
        self._refresh_order_listbox()

    def _toggle_order_item(self, file_path):
        selected = self.order_vars[file_path].get() == 1
        if selected and file_path not in self.order_selection_order:
            self.order_selection_order.append(file_path)
        if not selected and file_path in self.order_selection_order:
            self.order_selection_order.remove(file_path)
        self._refresh_order_listbox()

    def _refresh_order_listbox(self):
        if not hasattr(self, "order_listbox"):
            return
        try:
            if not self.order_listbox.winfo_exists():
                return
        except tk.TclError:
            return
        self.order_listbox.delete(0, tk.END)
        for idx, file_path in enumerate(self.order_selection_order, start=1):
            name = next((x["name"] for x in TEST_RUN.ORDER_TEST_MODULES if x["file"] == file_path), file_path)
            self.order_listbox.insert(tk.END, f"{idx}. {name}")

    def _build_together_area(self):
        no_dep, no_dep_content = self._build_scrollable_checklist(self.mode_frame, "◆ 无依赖任务")
        no_dep.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        with_dep, with_dep_content = self._build_scrollable_checklist(self.mode_frame, "◇ 有依赖任务(自动勾选依赖)")
        with_dep.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        columns = 4
        for col in range(columns):
            no_dep_content.grid_columnconfigure(col, weight=1, uniform="together_no_dep_col")
            with_dep_content.grid_columnconfigure(col, weight=1, uniform="together_with_dep_col")

        no_dep_index = 0
        with_dep_index = 0

        for item in TEST_RUN.TOGETHER_TASKS:
            file_path = item["file"]
            var = self.together_vars.get(file_path)
            if var is None:
                var = tk.IntVar(value=0)
                self.together_vars[file_path] = var

            label = item['name']
            if item.get("deps"):
                self._create_grid_toggle_button(
                    with_dep_content,
                    text=label,
                    variable=var,
                    command=lambda f=file_path: self._toggle_together_item(f),
                    row=with_dep_index // columns,
                    column=with_dep_index % columns,
                )
                with_dep_index += 1
            else:
                self._create_grid_toggle_button(
                    no_dep_content,
                    text=label,
                    variable=var,
                    command=lambda f=file_path: self._toggle_together_item(f),
                    row=no_dep_index // columns,
                    column=no_dep_index % columns,
                )
                no_dep_index += 1

    def _toggle_together_item(self, file_path):
        is_checked = self.together_vars[file_path].get() == 1
        deps = self.together_dep_closure_map.get(file_path, set())

        if is_checked:
            self.together_manual_selected.add(file_path)
            for dep in deps:
                self.together_auto_required_count[dep] = self.together_auto_required_count.get(dep, 0) + 1
                self.together_vars[dep].set(1)
        else:
            required = self.together_auto_required_count.get(file_path, 0)
            if required > 0:
                messagebox.showinfo("依赖提示", "该任务是其他已选任务的依赖，不能取消。")
                self.together_vars[file_path].set(1)
                return

            if file_path in self.together_manual_selected:
                self.together_manual_selected.remove(file_path)

            for dep in deps:
                old = self.together_auto_required_count.get(dep, 0)
                if old > 1:
                    self.together_auto_required_count[dep] = old - 1
                elif old == 1:
                    self.together_auto_required_count.pop(dep, None)
                    if dep not in self.together_manual_selected:
                        self.together_vars[dep].set(0)

    def _build_push_area(self):
        frame = ttk.LabelFrame(self.mode_frame, text="⚙ Bash 推图参数", padding=12, style="Option.TLabelframe")
        frame.pack(fill=tk.X)

        config_frame = ttk.Frame(frame)
        config_frame.pack(fill=tk.X, pady=6)

        ttk.Label(config_frame, text="GRPC编号(按环境自动带入):", font=("Microsoft YaHei UI", 10)).grid(row=0, column=0, sticky=tk.W, padx=8, pady=6)
        grpc_readonly = ttk.Entry(
            config_frame,
            textvariable=self.address_no_var,
            width=12,
            font=("Microsoft YaHei UI", 10),
            state="readonly",
            style="ReadonlyGrpc.TEntry",
            cursor="arrow"
        )
        grpc_readonly.grid(row=0, column=1, sticky=tk.W, padx=8, pady=6)

        ttk.Label(config_frame, text="推图数量:", font=("Microsoft YaHei UI", 10)).grid(row=0, column=2, sticky=tk.W, padx=8, pady=6)
        ttk.Spinbox(config_frame, from_=1, to=9999, textvariable=self.picture_num_var, width=12, font=("Microsoft YaHei UI", 10)).grid(row=0, column=3, sticky=tk.W, padx=8, pady=6)

        grpc_hint = (
            "1 -- qa-bash-grpc.svfactory.com:9198 -- 测试环境\n"
            "2 -- bash-grpc.idmaic.cn:9182 -- 生产环境"
        )
        ttk.Label(frame, text=grpc_hint, font=("Consolas", 10), foreground="#1F4E78").pack(anchor="w", padx=8, pady=(6, 2))

    def _collect_run_kwargs(self):
        mode = self.mode_var.get()
        env = self.env_var.get()
        kwargs = {
            "mode": mode,
            "env": env,
            "order_files": None,
            "together_files": None,
            "picture_num": None,
            "address_no": None,
            "threads": 1,
            "space_name": self.space_name_var.get().strip() or None,
            "space_id": self.space_id_var.get().strip() or None,
            "product_code": self.product_code_var.get().strip() or None,
        }

        if mode == "order":
            if not self.order_selection_order:
                raise ValueError("请至少选择一个顺序执行模块")
            kwargs["order_files"] = list(self.order_selection_order)

        elif mode == "together":
            selected = [f for f, var in self.together_vars.items() if var.get() == 1]
            if not selected:
                raise ValueError("请至少选择一个并行任务")
            kwargs["together_files"] = selected

        else:
            kwargs["picture_num"] = int(self.picture_num_var.get())
            kwargs["address_no"] = int(self.address_no_var.get())
            kwargs["threads"] = 1

        return kwargs

    def _build_command(self, kwargs):
        cmd = [sys.executable, RUN_SCRIPT, "--mode", kwargs["mode"], "--env", kwargs["env"]]
        if kwargs.get("space_name") is not None:
            cmd.extend(["--space-name", kwargs["space_name"]])
        if kwargs.get("space_id") is not None:
            cmd.extend(["--space-id", kwargs["space_id"]])
        if kwargs.get("product_code") is not None:
            cmd.extend(["--product-code", kwargs["product_code"]])
        if kwargs["mode"] == "order" and kwargs["order_files"]:
            cmd.extend(["--order-files", *kwargs["order_files"]])
        elif kwargs["mode"] == "together" and kwargs["together_files"]:
            cmd.extend(["--together-files", *kwargs["together_files"]])
        elif kwargs["mode"] == "push":
            cmd.extend([
                "--picture-num", str(kwargs["picture_num"]),
                "--address-no", str(kwargs["address_no"]),
                "--threads", "1",
            ])
        return cmd

    def _clear_report_url(self):
        self.latest_report_url = None
        self.latest_report_error = None
        self.report_var.set("")

    def _capture_report_url_from_output(self, text):
        match = ALLURE_REPORT_LINE_RE.search(text or "")
        if match:
            self.latest_report_url = match.group(1).strip()
            self.latest_report_error = None
            self.report_var.set(self.latest_report_url)
            return

        missing_match = ALLURE_REPORT_MISSING_RE.search(text or "")
        if missing_match:
            self.latest_report_error = f"报告文件不存在: {missing_match.group(1).strip()}"
            self.report_var.set("报告未生成")
            return

        cli_missing_match = ALLURE_CLI_MISSING_RE.search(text or "")
        if cli_missing_match:
            self.latest_report_error = cli_missing_match.group(1).strip()
            self.report_var.set("报告未生成")
            return

        gen_err_match = ALLURE_GENERATE_ERR_RE.search(text or "")
        if gen_err_match:
            self.latest_report_error = gen_err_match.group(1).strip()
            self.report_var.set("报告未生成")

    def _set_report_url_on_done(self):
        mode = self.mode_var.get()
        if mode not in {"order", "together"}:
            return

        if self.latest_report_url:
            self.report_var.set(self.latest_report_url)
            return

        report_dir = getattr(TEST_RUN, "allure_report", "") or ""
        fallback_index = Path(report_dir).resolve().joinpath("index.html") if report_dir else None
        if fallback_index and fallback_index.exists():
            self.report_var.set(fallback_index.as_uri())
        else:
            self.report_var.set("报告未生成")

    def _open_report_url(self, _event=None):
        url = self.latest_report_url or self.report_var.get().strip()
        if not url or url == "报告未生成":
            detail = self.latest_report_error or "当前没有可打开的报告地址"
            messagebox.showinfo("提示", detail)
            return
        try:
            parsed = urlparse(url)
            if parsed.scheme == "file":
                local_path = self._file_url_to_local_path(url)
                if not os.path.exists(local_path):
                    messagebox.showerror("报告不存在", f"未找到报告文件:\n{local_path}")
                    return
                report_http_url = self._start_or_reuse_report_http_server(local_path)
                webbrowser.open_new_tab(report_http_url)
                return

            webbrowser.open_new_tab(url)
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开报告地址: {e}")

    def _file_url_to_local_path(self, file_url):
        parsed = urlparse(file_url)
        local_path = unquote(parsed.path)
        # Windows file URI: /C:/path -> C:/path
        if os.name == "nt" and len(local_path) >= 3 and local_path[0] == "/" and local_path[2] == ":":
            local_path = local_path[1:]
        return local_path

    def _start_or_reuse_report_http_server(self, report_index_path):
        report_dir = str(Path(report_index_path).resolve().parent)

        if self.report_http_server and self.report_http_thread and self.report_http_thread.is_alive() and self.report_http_dir == report_dir:
            return f"http://127.0.0.1:{self.report_http_port}/index.html"

        self._stop_report_http_server()

        class _ReportHandler(http.server.SimpleHTTPRequestHandler):
            # 关闭默认请求日志，避免污染 GUI 日志
            def log_message(self, format, *args):
                return

        handler = functools.partial(_ReportHandler, directory=report_dir)
        last_err = None
        for port in range(8080, 8091):
            try:
                server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
                server.daemon_threads = True
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()

                report_url = f"http://127.0.0.1:{port}/index.html"
                if not self._wait_report_http_ready(report_url):
                    server.shutdown()
                    server.server_close()
                    last_err = RuntimeError(f"本地服务端口 {port} 启动后未就绪")
                    continue

                self.report_http_server = server
                self.report_http_thread = thread
                self.report_http_port = port
                self.report_http_dir = report_dir
                return report_url
            except OSError as e:
                last_err = e
                continue

        raise RuntimeError(f"启动本地报告服务失败: {last_err}")

    def _wait_report_http_ready(self, report_url, retries=20, delay=0.1):
        for _ in range(retries):
            try:
                with urlopen(report_url, timeout=1.5) as resp:
                    if int(getattr(resp, "status", 200)) in (200, 304):
                        return True
            except URLError:
                pass
            except Exception:
                pass
            time.sleep(delay)
        return False

    def _stop_report_http_server(self):
        if self.report_http_server is None:
            return
        try:
            self.report_http_server.shutdown()
            self.report_http_server.server_close()
        except Exception:
            pass
        finally:
            self.report_http_server = None
            self.report_http_thread = None
            self.report_http_port = None
            self.report_http_dir = None

    def _on_close(self):
        self._stop_report_http_server()
        try:
            if self.process is not None:
                self._terminate_process_tree(self.process.pid)
        except Exception:
            pass
        self.root.destroy()

    def start_execution(self):
        if self.process is not None or self.run_thread is not None:
            messagebox.showwarning("提示", "已有任务在执行，请先停止或等待完成")
            return

        try:
            kwargs = self._collect_run_kwargs()
        except Exception as e:
            messagebox.showerror("参数错误", str(e))
            return

        self.log_text.delete("1.0", tk.END)
        self._clear_report_url()

        if getattr(sys, "frozen", False):
            self.log_text.insert(tk.END, "\n>>> 启动内置执行模式\n")
            self.log_text.insert(tk.END, f">>> mode={kwargs['mode']} env={kwargs['env']}\n")
            self.log_text.insert(tk.END, f">>> order_files={kwargs['order_files']} together_files={kwargs['together_files']}\n\n")
            self.log_text.see(tk.END)
            self._set_running_controls(True)
            self._set_status("执行中")
            self.run_thread = threading.Thread(target=self._run_in_process_worker, args=(kwargs,), daemon=True)
            self.run_thread.start()
            return

        cmd = self._build_command(kwargs)

        self.log_text.insert(tk.END, "\n>>> 启动命令:\n" + " ".join(cmd) + "\n\n")
        self.log_text.see(tk.END)

        self.process = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        self._set_running_controls(True)
        self._set_status("执行中")

        threading.Thread(target=self._read_output_worker, daemon=True).start()
        threading.Thread(target=self._wait_worker, daemon=True).start()

    def stop_execution(self):
        if self.run_thread is not None:
            messagebox.showinfo("提示", "打包版内置执行暂不支持中断，如需终止可关闭客户端，重新启动")
            return
        if self.process is None:
            return
        self._terminate_process_tree(self.process.pid)
        self._set_status("已停止")

    def reset_selection(self):
        if self.process is not None or self.run_thread is not None:
            messagebox.showwarning("提示", "执行中不能重置选择，请先等待任务完成")
            return

        for var in self.order_vars.values():
            var.set(0)
        self.order_selection_order.clear()
        if self.mode_var.get() == "order":
            self._refresh_order_listbox()

        self.together_vars = {
            item["file"]: tk.IntVar(value=0)
            for item in TEST_RUN.TOGETHER_TASKS
        }
        self.together_manual_selected.clear()
        self.together_auto_required_count.clear()

        # 重建当前模式区域，确保并行模式下按钮视觉状态与变量状态一致
        self._refresh_mode_area()

    def _run_in_process_worker(self, kwargs):
        writer = QueueWriter(self.output_queue)
        try:
            # 仅重定向 stdout，不重定向 stderr，避免 pytest faulthandler 无法访问 stderr
            with contextlib.redirect_stdout(writer):
                code = TEST_RUN.run_app(**kwargs)
        except Exception as e:
            self.output_queue.put(f"\n>>> 执行异常: {e}\n{traceback.format_exc()}\n")
            code = 1
        self.output_queue.put(f"\n>>> 进程结束，退出码: {code}\n")
        self.output_queue.put(("_PROCESS_DONE_", code))

    def _read_output_worker(self):
        if self.process is None or self.process.stdout is None:
            return
        for line in self.process.stdout:
            self.output_queue.put(line)

    def _wait_worker(self):
        if self.process is None:
            return
        code = self.process.wait()
        self.output_queue.put(f"\n>>> 进程结束，退出码: {code}\n")
        self.output_queue.put(("_PROCESS_DONE_", code))

    def _poll_output(self):
        while True:
            try:
                item = self.output_queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(item, tuple) and item and item[0] == "_PROCESS_DONE_":
                self.process = None
                self.run_thread = None
                self._set_running_controls(False)
                code = item[1]
                if code == 0:
                    self._set_status("执行成功", color="#2E7D32")
                else:
                    self._set_status(f"执行失败({code})", color="#C62828")
                self._set_report_url_on_done()
                continue

            text_item = str(item)
            self._capture_report_url_from_output(text_item)
            self.log_text.insert(tk.END, text_item)
            self.log_text.see(tk.END)

        self.root.after(120, self._poll_output)

    def _terminate_process_tree(self, pid):
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                child.terminate()
            parent.terminate()
        except Exception as e:
            self.log_text.insert(tk.END, f"\n停止进程失败: {e}\n")
            self.log_text.see(tk.END)

    def _set_running_controls(self, is_running):
        if is_running:
            self.start_btn.configure(text="⏳ 执行中...", state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
        else:
            self.start_btn.configure(text="▶  开始执行", state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)


def main():
    if _maybe_run_internal_worker_cli(sys.argv[1:]):
        return

    root = tk.Tk()
    root.title("一休云测试客户端 v2.0")

    # 设置窗口图标和样式
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    app = ClientApp(root)
    root.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()

