import pytest
import time
# 屏蔽 urllib3 的不安全 HTTPS 警告
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from common.Log import MyLog, AllureReporter


def format_time(seconds):
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    return f"{minutes}分{remaining_seconds}秒"


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
