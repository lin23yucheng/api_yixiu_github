import pytest
import time
import os

from common.Log import MyLog, AllureReporter


# 线程级变量：记录当前正在执行的测试函数名
_current_test_name = None


def pytest_addoption(parser):
    """注册按阶段停止执行的可选参数。"""
    parser.addoption(
        "--run-until",
        action="store",
        default=None,
        help="控制流程执行到哪一步停止: create_complete, training_complete, submit_complete, full",
    )


@pytest.fixture(scope="session")
def run_until(request):
    """向测试用例暴露 run-until 参数，None 表示全流程执行。"""
    value = request.config.getoption("--run-until")
    if value in (None, "", "full"):
        return None
    return value


def format_time(seconds):
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    return f"{minutes}分{remaining_seconds}秒"


@pytest.hookimpl(trylast=True)
def pytest_runtest_setup(item):
    """捕获当前正在执行的测试函数名，供语义检查使用"""
    global _current_test_name
    _current_test_name = item.name
    # 同时记录到环境变量，供 Request_Response 装饰器读取
    os.environ["CURRENT_TEST_NAME"] = item.name
    class_name = item.cls.__name__ if item.cls else ""
    os.environ["CURRENT_TEST_CLASS"] = class_name


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session):
    """确保 Allure 上下文正确关闭"""
    try:
        AllureReporter.close()
        MyLog.info("Allure 上下文已安全关闭")
    except Exception as e:
        MyLog.error(f"关闭Allure上下文失败: {e}")


@pytest.fixture(scope="session", autouse=True)
def start_running():
    start_time = None  # 初始化变量
    try:
        start_time = time.time()  # 安全赋值
        message = "---马上开始执行自动化测试---"
        print(message)
        MyLog.info(message)
        yield
    finally:
        # 只有在 start_time 已赋值时才计算耗时
        if start_time is not None:
            end_time = time.time()
            duration = end_time - start_time
            formatted_duration = format_time(duration)
            message = f"---自动化测试完成，总耗时: {formatted_duration}---"
            print(message)
            MyLog.info(message)
        else:
            # 处理初始化失败的情况
            error_msg = "---自动化测试启动失败，无法计算耗时---"
            print(error_msg)
            MyLog.error(error_msg)
