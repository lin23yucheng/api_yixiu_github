import os
import sys
import time
import json
import argparse
import importlib
import importlib.util
import configparser
import builtins
import traceback
import subprocess
import pytest
import shutil
import psutil
import signal
import threading
from pathlib import Path
from common.Log import MyLog, set_log_level
from multiprocessing import Process, Manager

# 添加全局变量来跟踪是否需要生成报告
should_generate_report = True

if getattr(sys, "frozen", False):
    # 打包模式：首先尝试从 _MEIPASS（PyInstaller 资源目录）读取
    PROJECT_ROOT = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    # 如果找不到 config，说明资源没有被打包，改为指向源代码目录
    if not os.path.exists(os.path.join(PROJECT_ROOT, "config")):
        # 尝试找到源代码目录（通常是上两级目录）
        potential_source = os.path.dirname(os.path.dirname(sys.executable))
        if os.path.exists(os.path.join(potential_source, "config")):
            PROJECT_ROOT = potential_source
    # 打包环境下，报告生成在用户主目录下的 .yixiu_client 目录
    user_report_dir = os.path.expanduser("~/.yixiu_client/report")
    allure_results = os.path.join(user_report_dir, "allure-results")
    allure_report = os.path.join(user_report_dir, "allure-report")
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    # 开发环境下，报告生成在项目目录下
    allure_results = os.path.join(os.getcwd(), "report", "allure-results")
    allure_report = os.path.join(os.getcwd(), "report", "allure-report")

ENV_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "env_config.ini")

FILE_NAME_LABELS_CN = {
    "test_get_accesstoken.py": "DMP系统获取机台Token",
    "test_bash.py": "验证Bash系统",
    "test_bash_ui.py": "Bash自动化分拣流程",
    "test_standard_push_map.py": "机台推图",
    "test_2D_label.py": "单产品-2D标注流程",
    "test_3D_label.py": "单产品-3D标注流程",
    "test_controller.py": "综合样本库前置数据校验",
    "test_deep_model_training_v8.py": "目标检测模型训练-v8",
    "test_deep_model_training_v11.py": "目标检测模型训练-v11",
    "test_deep_model_training_v12.py": "目标检测模型训练-v12",
    "test_class_cut_model_training_v8.py": "分类切图模型训练-v8",
    "test_class_original_model_training_v8.py": "分类大图模型训练-v8",
    "test_model_training_metrics.py": "实例分割模型训练指标对比",
    "test_data_training_task.py": "数据训练任务流程",
    "test_model_base.py": "模型库流程",
    "test_eiir_label.py": "EIIR标注流程",
    "test_eiir_model_training.py": "EIIR模型训练流程",
    "test_product_information.py": "产品资料流程",
    "test_product_samples.py": "产品样例流程",
}

PUSH_PREREQ_TEST_FILES = [
    "testcase/test_get_accesstoken.py",
    "testcase/test_bash.py",
]


def _guess_cn_name(file_name):
    if file_name in FILE_NAME_LABELS_CN:
        return FILE_NAME_LABELS_CN[file_name]
    base = os.path.splitext(file_name)[0]
    if base.startswith("test_"):
        base = base[5:]
    return base.replace("_", "-")


def run_allure_generate(results_dir, report_dir):
    def _resolve_allure_command():
        config_allure_cmd = ""
        try:
            config = configparser.ConfigParser()
            config.read(ENV_CONFIG_PATH, encoding="utf-8")
            config_allure_cmd = config.get("environment", "allure_cmd", fallback="").strip()
        except Exception:
            config_allure_cmd = ""

        env_allure_cmd = os.environ.get("ALLURE_CMD", "").strip()
        which_allure = shutil.which("allure")

        candidates = [env_allure_cmd, config_allure_cmd, which_allure]
        for cmd in candidates:
            if not cmd:
                continue
            if os.path.isabs(cmd) and not os.path.exists(cmd):
                continue
            return cmd
        return None

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    allure_cmd = _resolve_allure_command()
    if not allure_cmd:
        msg = "ALLURE_CLI_MISSING=未找到allure命令，请设置系统PATH或环境变量ALLURE_CMD，或在config/env_config.ini[environment]里配置allure_cmd"
        MyLog.error(msg)
        print(msg)
        return False

    try:
        proc = subprocess.run(
            [allure_cmd, "generate", results_dir, "-o", report_dir, "--clean"],
            check=False,
            creationflags=creationflags,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        report_index = Path(report_dir).resolve().joinpath("index.html")
        if proc.returncode != 0:
            MyLog.error(f"allure generate 执行失败，退出码: {proc.returncode}")
            if proc.stderr:
                MyLog.error(proc.stderr.strip()[-500:])
                print(f"ALLURE_GENERATE_ERROR={proc.stderr.strip()[-500:]}")
            if proc.stdout:
                MyLog.error(proc.stdout.strip()[-500:])
                print(f"ALLURE_GENERATE_OUTPUT={proc.stdout.strip()[-500:]}")
            return False
        if not report_index.exists():
            MyLog.error(f"allure 报告未生成 index.html: {report_index}")
            print(f"ALLURE_REPORT_MISSING={report_index}")
            return False
        return True
    except Exception as e:
        MyLog.error(f"调用allure生成报告失败: {e}")
        print(f"ALLURE_GENERATE_EXCEPTION={e}")
        return False


def get_allure_report_url(report_dir):
    return Path(report_dir).resolve().joinpath("index.html").as_uri()


def emit_allure_report_url(report_dir):
    report_index = Path(report_dir).resolve().joinpath("index.html")
    if not report_index.exists():
        missing_msg = f"ALLURE_REPORT_MISSING={report_index}"
        MyLog.error(missing_msg)
        print(missing_msg)
        return None

    report_url = report_index.as_uri()
    MyLog.info(f"ALLURE_REPORT_URL={report_url}")
    print(f"ALLURE_REPORT_URL={report_url}")
    return report_url


def discover_order_test_modules():
    modules = []
    testcase_dir = os.path.join(PROJECT_ROOT, "testcase")
    excluded = {"__init__.py", "conftest.py", "test_mirror（镜像）.py", "test_simulation（仿真）.py"}

    for root, _, files in os.walk(testcase_dir):
        for file_name in files:
            if not file_name.endswith(".py"):
                continue
            if file_name in excluded:
                continue
            abs_path = os.path.join(root, file_name)
            rel_path = os.path.relpath(abs_path, PROJECT_ROOT).replace("\\", "/")
            display_name = _guess_cn_name(file_name)
            modules.append({"name": display_name, "file": rel_path})

    modules.sort(key=lambda item: item["file"])
    return modules


ORDER_TEST_MODULES = discover_order_test_modules()

TOGETHER_TASKS = [
    {"name": "验证Bash系统", "file": "testcase/test_bash.py", "deps": None},
    {"name": "DMP系统获取机台Token", "file": "testcase/test_get_accesstoken.py", "deps": None},
    {"name": "模型训练前置数据校验", "file": "testcase/test_controller.py", "deps": None},
    {"name": "模型库流程", "file": "testcase/test_model_base.py", "deps": None},
    {"name": "产品资料流程", "file": "testcase/test_product_information.py", "deps": None},
    {"name": "产品样例流程", "file": "testcase/test_product_samples.py", "deps": None},
    {"name": "EIIR标注流程", "file": "testcase/test_eiir_label.py", "deps": None},
    {
        "name": "机台推图",
        "file": "testcase/test_standard_push_map.py",
        "deps": ["testcase/test_get_accesstoken.py"],
        "require_success": True
    },
    {
        "name": "Bash自动化分拣流程",
        "file": "testcase/test_bash_ui.py",
        "deps": ["testcase/test_bash.py", "testcase/test_get_accesstoken.py"],
        "require_success": True
    },
    {"name": "单产品-2D标注流程", "file": "testcase/test_2D_label.py", "deps": ["testcase/test_bash_ui.py"],
     "require_success": True},
    {"name": "单产品-3D标注流程", "file": "testcase/test_3D_label.py", "deps": ["testcase/test_standard_push_map.py"],
     "require_success": True},
    {"name": "深度模型训练v8", "file": "testcase/test_deep_model_training_v8.py",
     "deps": ["testcase/test_controller.py"], "require_success": True},
    {"name": "深度模型训练v11", "file": "testcase/test_deep_model_training_v11.py",
     "deps": ["testcase/test_controller.py"], "require_success": True},
    {"name": "深度模型训练v12", "file": "testcase/test_deep_model_training_v12.py",
     "deps": ["testcase/test_controller.py"], "require_success": True},
    {"name": "分类切图模型训练v8", "file": "testcase/test_class_cut_model_training_v8.py",
     "deps": ["testcase/test_controller.py"], "require_success": True},
    {"name": "分类大图模型训练v8", "file": "testcase/test_class_original_model_training_v8.py",
     "deps": ["testcase/test_controller.py"], "require_success": True},
    {"name": "数据训练任务流程", "file": "testcase/test_data_training_task.py", "deps": ["testcase/test_controller.py"],
     "require_success": True},
    {"name": "EIIR模型训练流程", "file": "testcase/test_eiir_model_training.py",
     "deps": ["testcase/test_eiir_label.py"], "require_success": True},
    {
        "name": "模型训练指标对比",
        "file": "testcase/test_model_training_metrics.py",
        "deps": ["testcase/test_class_original_model_training_v8.py"],
        "require_success": True
    }
]

# 设置全局日志级别
set_log_level('info')


def get_default_order_files():
    return [item["file"] for item in ORDER_TEST_MODULES]


def get_default_together_tasks():
    return [dict(item) for item in TOGETHER_TASKS]


def set_execution_env(env):
    env = (env or "").strip().lower()
    if env not in {"fat", "prod"}:
        raise ValueError(f"不支持的环境: {env}")
    config = configparser.ConfigParser()
    config.read(ENV_CONFIG_PATH, encoding="utf-8")
    if not config.has_section("environment"):
        config.add_section("environment")
    config.set("environment", "execution_env", env)
    with open(ENV_CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)


def get_picture_num_by_env(env):
    env = (env or "").strip().lower()
    section = f"{env}-bash"
    config = configparser.ConfigParser()
    config.read(ENV_CONFIG_PATH, encoding="utf-8")
    return int(config.get(section, "picture_num", fallback="1"))


def set_picture_num_by_env(env, picture_num):
    env = (env or "").strip().lower()
    section = f"{env}-bash"
    config = configparser.ConfigParser()
    config.read(ENV_CONFIG_PATH, encoding="utf-8")
    if not config.has_section(section):
        raise ValueError(f"配置不存在: {section}")
    config.set(section, "picture_num", str(int(picture_num)))
    with open(ENV_CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)


def get_yixiu_values_by_env(env):
    env = (env or "").strip().lower()
    section = f"{env}-yixiu"
    config = configparser.ConfigParser()
    config.read(ENV_CONFIG_PATH, encoding="utf-8")
    return {
        "space_name": config.get(section, "space_name", fallback=""),
        "space_id": config.get(section, "miaispacemanageid", fallback=""),
        "product_code": config.get(section, "miai-product-code", fallback=""),
    }


def set_yixiu_values_by_env(env, space_name=None, space_id=None, product_code=None):
    env = (env or "").strip().lower()
    section = f"{env}-yixiu"
    config = configparser.ConfigParser()
    config.read(ENV_CONFIG_PATH, encoding="utf-8")
    if not config.has_section(section):
        raise ValueError(f"配置不存在: {section}")

    if space_name is not None:
        config.set(section, "space_name", str(space_name).strip())
    if space_id is not None:
        config.set(section, "miaispacemanageid", str(space_id).strip())
    if product_code is not None:
        config.set(section, "miai-product-code", str(product_code).strip())

    with open(ENV_CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)


def ensure_runtime_env_vars():
    os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
    os.environ['WDM_SSL_VERIFY'] = '0'
    os.environ['WDM_LOG_LEVEL'] = '0'
    os.environ['WDM_PRINT_FIRST_LINE'] = 'False'
    os.environ['WDM_CHROMEDRIVER_REPO'] = 'https://cdn.npmmirror.com/binaries/chromedriver'


def run_push_images_manual_non_interactive(env, picture_num=None, address_no=None, threads=1):
    # 推图数量仅作用于本次执行，不写回配置文件
    loops = int(picture_num) if picture_num is not None else get_picture_num_by_env(env)
    addr = int(address_no) if address_no else (1 if env == "fat" else 2)

    from bash.push.client_bash import push_images_manual

    values = iter([str(addr), str(int(threads)), str(int(loops))])
    original_input = builtins.input
    try:
        builtins.input = lambda _: next(values)
        push_images_manual()
    finally:
        builtins.input = original_input


def run_push_token_prerequisite():
    """推图模式前置：先执行前置模块，全部成功后才允许推图。"""
    if PROJECT_ROOT not in sys.path:
        sys.path.append(PROJECT_ROOT)
    os.makedirs(allure_results, exist_ok=True)

    for test_file in PUSH_PREREQ_TEST_FILES:
        file_name = os.path.basename(test_file)
        module_label = FILE_NAME_LABELS_CN.get(file_name, file_name)
        MyLog.info(f"推图前置检查开始: {module_label}")
        print(f">>> 推图前置检查开始: {module_label}")

        exit_code = execute_test(test_file, allure_results)
        if exit_code != 0:
            MyLog.critical(f"推图前置检查失败: {module_label}，退出码: {exit_code}")
            print(f">>> 推图前置检查失败，已阻断推图。退出码: {exit_code}")
            return exit_code

        MyLog.info(f"推图前置检查通过: {module_label}")
        print(f">>> 推图前置检查通过: {module_label}")

    return 0


def signal_handler(sig, frame):
    """处理中断信号"""
    global should_generate_report
    MyLog.info("接收到中断信号，正在优雅退出...")
    print("\n接收到中断信号，正在生成测试报告...")

    # 设置标志位，让程序知道需要生成报告
    should_generate_report = True

    # 如果已经初始化了报告路径，则生成报告
    if allure_results and allure_report:
        generate_report_on_exit()

    MyLog.info("测试报告已生成，程序退出")
    sys.exit(0)


def generate_report_on_exit():
    """在退出时生成报告"""
    global allure_results, allure_report

    if allure_results and os.path.exists(allure_results):
        try:
            if run_allure_generate(allure_results, allure_report):
                report_url = emit_allure_report_url(allure_report)
                if report_url:
                    MyLog.info(f"测试报告生成成功: {report_url}")
                    print(f"测试报告生成成功: {report_url}")
            else:
                emit_allure_report_url(allure_report)
        except Exception as e:
            MyLog.error(f"生成报告时出错: {e}")


def format_time(seconds):
    """将秒数转换为 'X分X秒' 格式"""
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    return f"{minutes}分{remaining_seconds}秒"


def reset_logs():
    """清除之前的日志内容（通过关闭处理器并重新初始化）"""
    from common.Log import logger, MyLog

    # 获取正确的日志目录路径
    log_dir = MyLog.get_log_dir()
    print(f"日志目录: {log_dir}")

    # 关闭所有处理器
    for handler in logger.handlers[:]:
        try:
            handler.flush()
            handler.close()
        except Exception as e:
            print(f"关闭日志处理器失败: {e}")
        finally:
            logger.removeHandler(handler)

    # 等待确保文件句柄释放
    time.sleep(1)

    # 删除日志目录
    if os.path.exists(log_dir):
        try:
            shutil.rmtree(log_dir)
            print(f"已删除日志目录: {log_dir}")
        except Exception as e:
            print(f"删除日志目录失败: {e}")

    # 重新创建目录
    os.makedirs(log_dir, exist_ok=True)

    # 重新初始化日志处理器
    MyLog.reinit_handlers()

    MyLog.info("已清除历史日志文件")


def _purge_runtime_modules():
    """清理与环境强相关的模块缓存，避免同进程重复执行时沿用旧环境。"""
    project_root_norm = os.path.normcase(os.path.abspath(PROJECT_ROOT))
    purge_prefixes = ("api", "testcase", "bash")
    removed = []

    for name, module in list(sys.modules.items()):
        try:
            if name == "test_run":
                continue
            if not any(name == p or name.startswith(f"{p}.") for p in purge_prefixes):
                continue

            module_file = getattr(module, "__file__", None)
            if not module_file:
                continue
            module_path_norm = os.path.normcase(os.path.abspath(module_file))
            if not module_path_norm.startswith(project_root_norm):
                continue

            removed.append(name)
            sys.modules.pop(name, None)
        except Exception:
            continue

    if removed:
        MyLog.info(f"已清理模块缓存: {len(removed)} 个")


def execute_test(test_file, allure_results):
    """执行单个测试文件（添加资源隔离）"""
    MyLog.info(f"开始执行测试文件: {test_file}")

    # GUI内置模式会在同一进程多次调用pytest，先清理模块缓存确保环境切换生效
    _purge_runtime_modules()

    # 构建目标路径
    target_path = os.path.join(PROJECT_ROOT, test_file.replace('/', os.sep))
    if not os.path.exists(target_path):
        MyLog.error(f"错误：测试文件 {target_path} 不存在！")
        print(f"错误：测试文件 {target_path} 不存在！")
        return 1

    # 创建独立的工作目录（避免文件冲突）
    test_name = os.path.splitext(os.path.basename(test_file))[0]
    results_dir = str(allure_results)
    test_workspace = os.path.join(os.path.dirname(results_dir), "workspaces", str(test_name))
    os.makedirs(test_workspace, exist_ok=True)

    # 设置环境变量供测试用例使用
    os.environ["TEST_WORKSPACE"] = str(test_workspace)
    os.environ["CURRENT_TEST_FILE"] = str(target_path)

    def _has_module(module_name):
        return importlib.util.find_spec(module_name) is not None

    def _can_import_module(module_name):
        if not _has_module(module_name):
            return False
        try:
            importlib.import_module(module_name)
            return True
        except Exception as exc:
            MyLog.error(f"插件模块加载失败 {module_name}: {exc}")
            return False

    has_allure_plugin = _can_import_module("allure_pytest.plugin")
    has_random_order_plugin = _can_import_module("random_order.plugin")
    use_explicit_plugin_load = getattr(sys, "frozen", False)

    # 执行参数（插件参数按可用性动态启用，避免打包后参数无法识别）
    log_file = os.path.join(str(test_workspace), 'pytest.log')
    base_pytest_args = [
        "-v", "-s", "-x",
        target_path,
        f"--log-file={log_file}"  # 使用转换后的变量
    ]

    pytest_args = list(base_pytest_args)

    # 打包模式下禁用 faulthandler 避免 stderr 相关问题
    if use_explicit_plugin_load:
        pytest_args.append("-p")
        pytest_args.append("no:faulthandler")

    if has_allure_plugin:
        if use_explicit_plugin_load:
            pytest_args.extend(["-p", "allure_pytest.plugin"])
        pytest_args.extend([f"--alluredir={allure_results}"])
    else:
        MyLog.error("未检测到 allure_pytest 插件，已跳过 --alluredir 参数")

    if has_random_order_plugin:
        if use_explicit_plugin_load:
            pytest_args.extend(["-p", "random_order.plugin"])
        pytest_args.extend(["--random-order"])
    else:
        MyLog.error("未检测到 random_order(pytest-random-order) 插件，已跳过 --random-order 参数")

    def _tail_log(path, lines=120):
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.readlines()
            return "".join(content[-lines:])
        except Exception:
            return ""

    def _run_pytest(args, disable_autoload):
        old_disable_autoload = os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD")
        if disable_autoload:
            os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        try:
            return pytest.main(args)
        except Exception:
            MyLog.error(f"pytest执行异常: {test_file}\n{traceback.format_exc()}")
            print(traceback.format_exc())
            return 2
        finally:
            if disable_autoload:
                if old_disable_autoload is None:
                    os.environ.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
                else:
                    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = old_disable_autoload

    exit_code = _run_pytest(pytest_args, disable_autoload=use_explicit_plugin_load)

    # 某些打包场景下插件存在但无法正确注册参数，降级重试保证主流程可执行
    if exit_code == 4 and ("--alluredir=" in " ".join(pytest_args) or "--random-order" in pytest_args):
        MyLog.error("检测到pytest参数解析失败(退出码4)，将移除插件参数后重试一次")
        print("检测到pytest参数解析失败(退出码4)，将移除插件参数后重试一次")
        exit_code = _run_pytest(base_pytest_args, disable_autoload=False)

    if exit_code == 0:
        MyLog.info(f"测试文件 {test_file} 全部通过")
    elif exit_code == 1:
        MyLog.error(f"测试文件 {test_file} 存在失败用例")  # 明确标记为错误
    else:
        MyLog.critical(f"测试文件 {test_file} 执行错误，退出码: {exit_code}")

    if exit_code != 0:
        tail = _tail_log(log_file, lines=120)
        if tail:
            msg = f"测试文件 {test_file} 失败，pytest.log末尾输出:\n{tail}"
            MyLog.error(msg)
            print(msg)

    # 清理环境变量
    os.environ.pop("TEST_WORKSPACE", None)
    os.environ.pop("CURRENT_TEST_FILE", None)

    if exit_code in [0, 1]:
        MyLog.info(f"测试文件 {test_file} 执行完成")
    else:
        MyLog.error(f"测试文件 {test_file} 执行失败，退出码: {exit_code}")

    return exit_code


def process_task(file, deps, require_success, event_dict, result_dict, allure_results):
    """执行测试并处理依赖关系（进程版本）"""
    # 如果有依赖，等待所有依赖完成且检查状态
    if deps:
        MyLog.info(f"任务 {file} 依赖: {deps}")
        for dep in deps:
            event_dict[dep].wait()  # 等待依赖事件完成
            dep_result = result_dict.get(dep)
            MyLog.info(f"依赖 {dep} 状态: {dep_result}")

            if require_success:
                # 严格检查：只有0才是完全成功
                if dep_result != 0:  # 修改这里
                    MyLog.info(f"跳过 {file}，因为依赖文件 {dep} 执行失败")
                    result_dict[file] = -1
                    event_dict[file].set()
                    return
            else:
                if dep_result == -1 or dep_result > 1:
                    MyLog.info(f"跳过 {file}，因为依赖文件 {dep} 未完成")
                    result_dict[file] = -1
                    event_dict[file].set()
                    return

    # 执行测试
    MyLog.info(f"开始执行测试文件: {file}")
    exit_code = execute_test(file, allure_results)
    result_dict[file] = exit_code
    event_dict[file].set()


# -------------------------------------------------------------------------------------------------------------------- #


"""顺序执行（一旦执行失败立即停止，生成allure报告）"""


def run_order_tests(test_files=None):
    """执行指定测试文件（遇到任何失败立即终止，但确保生成报告）"""
    global allure_results, allure_report

    reset_logs()  # 清除之前的日志
    MyLog.info("===== 开始执行测试任务 =====")

    # 定义要执行的测试文件列表
    test_files = list(test_files) if test_files else get_default_order_files()

    # 添加项目根目录到Python路径
    if PROJECT_ROOT not in sys.path:
        sys.path.append(PROJECT_ROOT)

    # 清空结果目录（使用全局定义的报告路径）
    if os.path.exists(allure_results):
        shutil.rmtree(allure_results)
    os.makedirs(allure_results, exist_ok=True)
    MyLog.info("已清理历史报告数据")

    # 记录开始时间
    start_time = time.time()
    MyLog.info(f"开始执行所有测试文件 at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")

    # 初始化耗时统计变量
    total_elapsed_time = 0.0  # 累加总耗时
    file_times = {}  # 存储每个文件的耗时

    # 定义报告生成函数（确保在失败时也能调用）
    def generate_report():
        # 计算整体耗时
        end_time = time.time()
        overall_time = end_time - start_time
        formatted_overall = format_time(overall_time)

        # 生成报告
        generated = run_allure_generate(allure_results, allure_report)

        # 在Allure报告中添加执行时间信息
        report_env_file = os.path.join(allure_report, 'widgets', 'environment.json')
        if generated and os.path.exists(report_env_file):
            try:
                with open(report_env_file, 'r', encoding='utf-8') as f:
                    env_data = json.load(f)

                # 添加执行时间信息
                env_data.append({
                    "name": "执行时间",
                    "values": [f"整体耗时: {formatted_overall}"]
                })

                with open(report_env_file, 'w', encoding='utf-8') as f:
                    json.dump(env_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                MyLog.error(f"更新Allure环境信息失败: {e}")

        report_url = emit_allure_report_url(allure_report)
        if report_url:
            MyLog.info(f"测试报告生成成功: {report_url}")
        else:
            MyLog.error("测试报告生成失败，未找到 index.html")
        return formatted_overall

    try:
        # 迭代执行测试文件
        for test_file in test_files:
            # 记录单个文件开始时间
            file_start_time = time.time()

            exit_code = execute_test(test_file, allure_results)

            # 计算单个文件耗时
            file_elapsed_time = time.time() - file_start_time
            total_elapsed_time += file_elapsed_time
            file_times[test_file] = file_elapsed_time

            # 使用新的时间格式
            formatted_time = format_time(file_elapsed_time)
            MyLog.info(f"测试文件 {test_file} 执行完成，耗时: {formatted_time}")

            # 遇到任何失败（包括测试用例失败）立即终止
            if exit_code != 0:  # 0表示全部通过，其他值都视为失败
                failure_type = "测试用例失败" if exit_code == 1 else "框架错误"
                MyLog.critical(f"执行测试文件 {test_file} 发生{failure_type}，程序终止")

                # 生成报告后返回失败状态
                formatted_overall = generate_report()

                # 在控制台显示整体耗时
                print(f"\033[32m一休云接口自动化测试-整体耗时: {formatted_overall}\033[0m")
                return exit_code

            # 输出耗时统计（使用新格式）
            MyLog.info("===== 测试文件耗时明细 =====")
            for file, time_taken in file_times.items():
                formatted_time = format_time(time_taken)
                MyLog.info(f"{file}: {formatted_time}")

            # 格式化并输出总耗时
            formatted_total = format_time(total_elapsed_time)
            MyLog.info(f"测试文件累加总耗时: {formatted_total}")

    except KeyboardInterrupt:
        MyLog.info("用户中断测试执行")
        print("\n用户中断测试执行，正在生成报告...")

    finally:
        # 无论成功还是失败，都生成报告
        if os.path.exists(allure_results) and os.listdir(allure_results):
            formatted_overall = generate_report()
            MyLog.info(f"一休云接口自动化测试-整体耗时: {formatted_overall}")
            print(f"\033[32m一休云接口自动化测试-整体耗时: {formatted_overall}\033[0m")
        else:
            emit_allure_report_url(allure_report)
            MyLog.info("没有生成测试结果，跳过报告生成")
        MyLog.info("===== 测试任务完成 =====")

    return 0


# -------------------------------------------------------------------------------------------------------------------- #

"""并行执行（存在依赖关系）"""


def run_together_tests(tasks=None):
    """使用进程实现依赖关系的并行测试执行"""
    global allure_results, allure_report

    reset_logs()
    MyLog.info("===== 开始并行执行测试 =====")

    # 定义任务依赖关系
    tasks = list(tasks) if tasks else get_default_together_tasks()

    # 添加项目根目录到Python路径
    if PROJECT_ROOT not in sys.path:
        sys.path.append(PROJECT_ROOT)

    # 清空结果目录（使用全局定义的报告路径）
    if os.path.exists(allure_results):
        shutil.rmtree(allure_results)
    os.makedirs(allure_results, exist_ok=True)
    MyLog.info("已清理历史报告数据")

    # 记录开始时间
    start_time = time.time()
    start_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))
    MyLog.info(f"开始并行测试 at {start_time_str}")

    processes = []
    workers = []

    try:
        # 冻结后使用多进程会触发子进程重新拉起 GUI，这里强制改为线程并行执行
        use_threads = getattr(sys, "frozen", False)
        if use_threads:
            MyLog.info("检测到打包环境，使用线程并行执行以避免重复拉起客户端窗口")

        # 收集所有需要管理的文件（包括任务文件和依赖文件）
        all_files = set()
        for task in tasks:
            all_files.add(task["file"])
            if task.get("deps"):
                for dep in task["deps"]:
                    all_files.add(dep)

        if use_threads:
            event_dict = {test_file: threading.Event() for test_file in all_files}
            result_dict = {test_file: None for test_file in all_files}

            for test_file in all_files:
                MyLog.info(f"初始化事件和结果字典 for: {test_file}")

            for task in tasks:
                t = threading.Thread(
                    target=process_task,
                    args=(
                        task["file"],
                        task.get("deps", []),
                        task.get("require_success", False),
                        event_dict,
                        result_dict,
                        allure_results,
                    ),
                    daemon=True,
                )
                t.start()
                workers.append(t)
                MyLog.info(f"启动线程执行 {task['file']}")

            for t in workers:
                t.join()
                MyLog.info("线程完成")
        else:
            with Manager() as manager:
                event_dict = manager.dict()
                result_dict = manager.dict()

                for test_file in all_files:
                    event_dict[test_file] = manager.Event()
                    result_dict[test_file] = None
                    MyLog.info(f"初始化事件和结果字典 for: {test_file}")

                for task in tasks:
                    p = Process(
                        target=process_task,
                        args=(
                            task["file"],
                            task.get("deps", []),
                            task.get("require_success", False),
                            event_dict,
                            result_dict,
                            allure_results,
                        ),
                    )
                    p.start()
                    processes.append(p)
                    MyLog.info(f"启动进程: {p.pid} 执行 {task['file']}")

                for p in processes:
                    p.join()
                    MyLog.info(f"进程完成: {p.pid}")

    except KeyboardInterrupt:
        MyLog.info("用户中断测试执行")
        print("\n用户中断测试执行，正在等待当前进程完成...")
        # 给进程一些时间完成当前任务
        for p in processes:
            if p.is_alive():
                p.join(timeout=5)  # 等待最多5秒
        for t in workers:
            if t.is_alive():
                t.join(timeout=5)
        print("正在生成报告...")

    # 记录结束时间
    end_time = time.time()
    overall_time = end_time - start_time
    formatted_time = format_time(overall_time)

    MyLog.info(f"完成并行测试 at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")
    MyLog.info(f"一休云接口自动化测试-整体耗时: {formatted_time}")

    # 在控制台显示整体耗时
    print(f"\033[32m一休云接口自动化测试-整体耗时: {formatted_time}\033[0m")

    # 生成报告
    if os.path.exists(allure_results) and os.listdir(allure_results):
        generated = run_allure_generate(allure_results, allure_report)

        # 在Allure报告中添加执行时间信息
        report_env_file = os.path.join(allure_report, 'widgets', 'environment.json')
        if generated and os.path.exists(report_env_file):
            try:
                with open(report_env_file, 'r', encoding='utf-8') as f:
                    env_data = json.load(f)

                # 添加执行时间信息
                env_data.append({
                    "name": "执行时间",
                    "values": [f"总耗时: {formatted_time}"]
                })

                with open(report_env_file, 'w', encoding='utf-8') as f:
                    json.dump(env_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                MyLog.error(f"更新Allure环境信息失败: {e}")

        report_url = emit_allure_report_url(allure_report)
        if report_url:
            MyLog.info(f"测试报告生成成功: {report_url}")
        else:
            MyLog.error("测试报告生成失败，未找到 index.html")
    else:
        emit_allure_report_url(allure_report)
        MyLog.info("没有生成测试结果，跳过报告生成")

    MyLog.info("===== 并行测试完成 =====")
    return 0


# -------------------------------------------------------------------------------------------------------------------- #


def _task_map():
    return {task["file"]: dict(task) for task in TOGETHER_TASKS}


def resolve_together_tasks(selected_files=None):
    base_map = _task_map()
    if not selected_files:
        return get_default_together_tasks()

    selected = set(selected_files)
    visited = set()

    def add_with_deps(file_path):
        if file_path in visited:
            return
        if file_path not in base_map:
            raise ValueError(f"并行任务不存在: {file_path}")
        visited.add(file_path)
        for dep in base_map[file_path].get("deps") or []:
            add_with_deps(dep)

    for item in selected:
        add_with_deps(item)

    resolved = []
    for task in TOGETHER_TASKS:
        if task["file"] in visited:
            resolved.append(dict(task))
    return resolved


def run_app(
        mode,
        env,
        order_files=None,
        together_files=None,
        picture_num=None,
        address_no=None,
        threads=1,
        space_name=None,
        space_id=None,
        product_code=None,
):
    mode = (mode or "").strip().lower()
    env = (env or "").strip().lower()
    if mode not in {"order", "together", "push"}:
        raise ValueError(f"不支持的模式: {mode}")

    set_execution_env(env)
    ensure_runtime_env_vars()

    set_yixiu_values_by_env(
        env=env,
        space_name=space_name,
        space_id=space_id,
        product_code=product_code,
    )

    if mode == "order":
        return run_order_tests(test_files=order_files)

    if mode == "together":
        resolved_tasks = resolve_together_tasks(together_files)
        return run_together_tests(tasks=resolved_tasks)

    prerequisite_code = run_push_token_prerequisite()
    if prerequisite_code != 0:
        return prerequisite_code

    run_push_images_manual_non_interactive(
        env=env,
        picture_num=picture_num,
        address_no=address_no,
        threads=threads
    )
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="测试执行控制入口")
    parser.add_argument("--mode", choices=["order", "together", "push"], default="order")
    parser.add_argument("--env", choices=["fat", "prod"], default="fat")
    parser.add_argument("--order-files", nargs="*", default=None, help="顺序执行的测试文件列表")
    parser.add_argument("--together-files", nargs="*", default=None, help="并行执行的任务文件列表(会自动补依赖)")
    parser.add_argument("--picture-num", type=int, default=None, help="推图循环次数(仅本次生效，不写回配置)")
    parser.add_argument("--address-no", type=int, default=None, help="推图GRPC请求编号，fat默认1，prod默认2")
    parser.add_argument("--threads", type=int, default=1, help="推图线程数")
    parser.add_argument("--space-name", default=None, help="推图前写入当前环境的一休空间名称(space_name)")
    parser.add_argument("--space-id", default=None, help="推图前写入当前环境的一休空间ID(miaispacemanageid)")
    parser.add_argument("--product-code", default=None, help="推图前写入当前环境的产品编号(miai-product-code)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    ensure_runtime_env_vars()

    print("===== 测试执行程序启动 =====")
    MyLog.info("===== 测试执行程序启动 =====")

    try:
        args = parse_args()
        exit_code = run_app(
            mode=args.mode,
            env=args.env,
            order_files=args.order_files,
            together_files=args.together_files,
            picture_num=args.picture_num,
            address_no=args.address_no,
            threads=args.threads,
            space_name=args.space_name,
            space_id=args.space_id,
            product_code=args.product_code,
        )
        sys.exit(exit_code)

    finally:
        current_process = psutil.Process()
        children = current_process.children(recursive=True)
        for child in children:
            child.terminate()
