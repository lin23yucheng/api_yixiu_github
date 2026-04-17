import os
import sys
import time
import json
import pytest
import shutil
import psutil
import signal
from common.Log import MyLog, set_log_level
from multiprocessing import Process, Manager

# 单独执行推图使用
from bash.push.client_bash import push_images_manual

# 添加全局变量来跟踪是否需要生成报告
should_generate_report = True
allure_results = os.path.join(os.getcwd(), "report", "allure-results")
allure_report = os.path.join(os.getcwd(), "report", "allure-report")

# 设置全局日志级别
set_log_level('info')


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
            os.system(f"allure generate {allure_results} -o {allure_report} --clean")
            MyLog.info(f"测试报告生成成功: file://{os.path.abspath(allure_report)}/index.html")
            print(f"测试报告生成成功: file://{os.path.abspath(allure_report)}/index.html")
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


def execute_test(test_file, allure_results):
    """执行单个测试文件（添加资源隔离）"""
    MyLog.info(f"开始执行测试文件: {test_file}")

    # 构建目标路径
    target_path = test_file.replace('/', os.sep)
    if not os.path.exists(target_path):
        MyLog.error(f"错误：测试文件 {target_path} 不存在！")
        return 1

    # 创建独立的工作目录（避免文件冲突）
    test_name = os.path.splitext(os.path.basename(test_file))[0]
    test_workspace = os.path.join(os.path.dirname(allure_results), "workspaces", test_name)
    os.makedirs(test_workspace, exist_ok=True)

    # 设置环境变量供测试用例使用
    os.environ["TEST_WORKSPACE"] = test_workspace
    os.environ["CURRENT_TEST_FILE"] = test_file

    # 执行参数
    log_file = os.path.join(str(test_workspace), 'pytest.log')
    pytest_args = [
        "-v", "-s", "-x",
        target_path,
        f"--alluredir={allure_results}",
        "--random-order",
        f"--log-file={log_file}"  # 使用转换后的变量
    ]

    # 执行测试
    exit_code = pytest.main(pytest_args)

    if exit_code == 0:
        MyLog.info(f"测试文件 {test_file} 全部通过")
    elif exit_code == 1:
        MyLog.error(f"测试文件 {test_file} 存在失败用例")  # 明确标记为错误
    else:
        MyLog.critical(f"测试文件 {test_file} 执行错误，退出码: {exit_code}")

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


def run_order_tests():
    """执行指定测试文件（遇到任何失败立即终止，但确保生成报告）"""
    global allure_results, allure_report

    reset_logs()  # 清除之前的日志
    MyLog.info("===== 开始执行测试任务 =====")

    # 定义要执行的测试文件列表
    test_files = [
        "testcase/test_get_accesstoken.py",
        "testcase/test_bash.py",
        "testcase/test_bash_ui.py",
        "testcase/test_2D_label.py"
    ]

    # 添加项目根目录到Python路径
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

    # 配置报告路径
    base_dir = os.path.dirname(os.path.abspath(__file__))
    allure_results = os.path.join(base_dir, "report", "allure-results")
    allure_report = os.path.join(base_dir, "report", "allure-report")

    # 清空结果目录
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
        os.system(f"allure generate {allure_results} -o {allure_report} --clean")

        # 在Allure报告中添加执行时间信息
        report_env_file = os.path.join(allure_report, 'widgets', 'environment.json')
        if os.path.exists(report_env_file):
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

        MyLog.info(f"测试报告生成成功: file://{os.path.abspath(allure_report)}/index.html")
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

                # 生成报告后再退出
                formatted_overall = generate_report()

                # 在控制台显示整体耗时
                print(f"\033[32m一休云接口自动化测试-整体耗时: {formatted_overall}\033[0m")
                sys.exit(exit_code)

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
            MyLog.info("没有生成测试结果，跳过报告生成")
        MyLog.info("===== 测试任务完成 =====")


# -------------------------------------------------------------------------------------------------------------------- #

"""并行执行（存在依赖关系）"""


def run_together_tests():
    """使用进程实现依赖关系的并行测试执行"""
    global allure_results, allure_report

    reset_logs()
    MyLog.info("===== 开始并行执行测试 =====")

    # 定义任务依赖关系
    tasks = [
        # 第一组：无依赖任务（并行执行）
        {"file": "testcase/test_bash.py", "deps": None},
        {"file": "testcase/test_get_accesstoken.py", "deps": None},
        {"file": "testcase/test_controller.py", "deps": None},
        {"file": "testcase/test_model_base.py", "deps": None},
        {"file": "testcase/test_product_information.py", "deps": None},
        {"file": "testcase/test_product_samples.py", "deps": None},
        # {"file": "testcase/test_eiir_label.py", "deps": None},

        # 第二组：有依赖任务
        {"file": "testcase/test_standard_push_map.py", "deps": ["testcase/test_get_accesstoken.py"],
         "require_success": True},
        {"file": "testcase/test_bash_ui.py", "deps": ["testcase/test_bash.py", "testcase/test_get_accesstoken.py"], "require_success": True},
        {"file": "testcase/test_2D_label.py", "deps": ["testcase/test_bash_ui.py"], "require_success": True},
        {"file": "testcase/test_3D_label.py", "deps": ["testcase/test_standard_push_map.py"], "require_success": True},
        {"file": "testcase/test_deep_model_training_v8.py", "deps": ["testcase/test_controller.py"],
         "require_success": True},
        {"file": "testcase/test_deep_model_training_v11.py", "deps": ["testcase/test_controller.py"],
         "require_success": True},
        {"file": "testcase/test_deep_model_training_v12.py", "deps": ["testcase/test_controller.py"],
         "require_success": True},
        {"file": "testcase/test_class_cut_model_training_v8.py", "deps": ["testcase/test_controller.py"],
         "require_success": True},
        {"file": "testcase/test_class_original_model_training_v8.py", "deps": ["testcase/test_controller.py"],
         "require_success": True},
        # {"file": "testcase/test_data_training_task.py", "deps": ["testcase/test_controller.py"],
        #  "require_success": True},
        # {"file": "testcase/test_eiir_model_training.py", "deps": ["testcase/test_eiir_label.py"],
        #  "require_success": True},
        {"file": "testcase/test_model_training_metrics.py", "deps": ["testcase/test_class_original_model_training_v8.py"],
         "require_success": True}
    ]

    # 添加项目根目录到Python路径
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

    # 配置报告路径
    base_dir = os.path.dirname(os.path.abspath(__file__))
    allure_results = os.path.join(base_dir, "report", "allure-results")
    allure_report = os.path.join(base_dir, "report", "allure-report")

    # 清空结果目录
    if os.path.exists(allure_results):
        shutil.rmtree(allure_results)
    os.makedirs(allure_results, exist_ok=True)
    MyLog.info("已清理历史报告数据")

    # 记录开始时间
    start_time = time.time()
    start_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))
    MyLog.info(f"开始并行测试 at {start_time_str}")

    try:
        # ==== 使用多进程替代多线程 ====
        with Manager() as manager:
            # 创建共享的事件字典和结果字典
            event_dict = manager.dict()
            result_dict = manager.dict()

            # 收集所有需要管理的文件（包括任务文件和依赖文件）
            all_files = set()
            for task in tasks:
                all_files.add(task["file"])
                if task.get("deps"):
                    for dep in task["deps"]:
                        all_files.add(dep)

            # 初始化事件和结果字典
            for test_file in all_files:
                event_dict[test_file] = manager.Event()
                result_dict[test_file] = None  # 初始化为未执行状态
                MyLog.info(f"初始化事件和结果字典 for: {test_file}")

            # 创建并启动进程
            processes = []
            for task in tasks:
                p = Process(
                    target=process_task,  # 使用外部函数
                    args=(
                        task["file"],
                        task.get("deps", []),  # 如果没有依赖，默认为空列表
                        task.get("require_success", False),  # 默认不要求依赖成功
                        event_dict,
                        result_dict,
                        allure_results
                    )
                )
                p.start()
                processes.append(p)
                MyLog.info(f"启动进程: {p.pid} 执行 {task['file']}")

            # 等待所有进程完成
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
        os.system(f"allure generate {allure_results} -o {allure_report} --clean")

        # 在Allure报告中添加执行时间信息
        report_env_file = os.path.join(allure_report, 'widgets', 'environment.json')
        if os.path.exists(report_env_file):
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

        MyLog.info(f"测试报告生成成功: file://{os.path.abspath(allure_report)}/index.html")
    else:
        MyLog.info("没有生成测试结果，跳过报告生成")

    MyLog.info("===== 并行测试完成 =====")


# -------------------------------------------------------------------------------------------------------------------- #

if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 添加环境变量
    os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
    # 添加 webdriver-manager 相关环境变量
    os.environ['WDM_SSL_VERIFY'] = '0'  # 禁用SSL验证
    os.environ['WDM_LOG_LEVEL'] = '0'  # 禁用 webdriver-manager 日志
    os.environ['WDM_PRINT_FIRST_LINE'] = 'False'  # 禁用首行打印
    # 添加国内镜像源
    os.environ['WDM_CHROMEDRIVER_REPO'] = 'https://cdn.npmmirror.com/binaries/chromedriver'

    print("===== 测试执行程序启动 =====")
    MyLog.info("===== 测试执行程序启动 =====")

    try:
        # 选择执行模式
        run_order_tests()  # 顺序执行
        # run_together_tests()  # 并行执行
        # push_images_manual()  # bash手动推图

    finally:
        current_process = psutil.Process()
        children = current_process.children(recursive=True)
        for child in children:
            child.terminate()

    MyLog.info("===== 测试执行程序结束 =====")
    print("===== 测试执行程序结束 =====")
