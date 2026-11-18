"""
conftest.py 追加内容 — 支持 --run-until 参数
放到现有 conftest.py 末尾即可

作用：算法服务发布时，跑部分流程（如只到创建完成）
用法：pytest --run-until=create_complete
"""

import pytest


def pytest_addoption(parser):
    """注册自定义命令行参数"""
    parser.addoption(
        "--run-until",
        action="store",
        default=None,
        help="控制流程执行到哪一步停止。可选值: create_complete, training_complete, submit_complete, full (默认full)"
    )


@pytest.fixture(scope="session")
def run_until(request):
    """
    获取 run_until 参数，供测试方法判断执行到哪一步

    使用方式（在测试方法中）:
        def test_training_flow(self, run_until):
            self.create_task()
            if run_until == "create_complete":
                return  # 到这就停
            self.start_training()
            if run_until == "training_complete":
                return
            self.submit_task()

    run_until 可选值:
        - None / "full": 跑全流程（默认）
        - "create_complete": 跑到创建完成
        - "training_complete": 跑到训练完成
        - "submit_complete": 跑到提交完成
    """
    value = request.config.getoption("--run-until")
    return value  # None 表示全流程
