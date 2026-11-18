"""
验证推图模式前置校验逻辑的回归测试。

文件作用：
1) 确保 `run_app(mode="push")` 会先执行前置测试（token + bash）再推图。
2) 确保任一前置测试失败时，推图流程被阻断，不会继续执行推图。

"""

import importlib.util
from pathlib import Path
import sys


def _load_test_run_module():
    # 项目根目录（当前文件已在 client/ 目录下）
    project_root = Path(__file__).resolve().parent.parent
    # 客户端执行入口模块
    module_path = project_root / "client" / "test_run.py"
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    if str(module_path.parent) not in sys.path:
        sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("test_run", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


test_run = _load_test_run_module()


def test_push_mode_runs_prerequisites_before_push(monkeypatch):
    # 记录调用顺序，验证前置任务是否先于推图执行
    calls = []

    monkeypatch.setattr(test_run, "set_execution_env", lambda env: None)
    monkeypatch.setattr(test_run, "ensure_runtime_env_vars", lambda: None)
    monkeypatch.setattr(
        test_run,
        "set_yixiu_values_by_env",
        lambda env, space_name=None, space_id=None, product_code=None: None,
    )

    def fake_execute_test(test_file, allure_results):
        calls.append(("prereq", test_file))
        return 0

    def fake_push(**kwargs):
        calls.append(("push", kwargs["env"]))

    monkeypatch.setattr(test_run, "execute_test", fake_execute_test)
    monkeypatch.setattr(test_run, "run_push_images_manual_non_interactive", fake_push)

    code = test_run.run_app(mode="push", env="fat", picture_num=1, address_no=1, threads=1)

    assert code == 0
    assert calls == [
        ("prereq", "testcase/test_get_accesstoken.py"),
        ("prereq", "testcase/test_bash.py"),
        ("push", "fat"),
    ]


def test_push_mode_stops_when_second_prerequisite_fails(monkeypatch):
    # 第二个前置任务失败时，推图函数不应被调用
    push_called = []
    execute_calls = []

    monkeypatch.setattr(test_run, "set_execution_env", lambda env: None)
    monkeypatch.setattr(test_run, "ensure_runtime_env_vars", lambda: None)
    monkeypatch.setattr(
        test_run,
        "set_yixiu_values_by_env",
        lambda env, space_name=None, space_id=None, product_code=None: None,
    )
    def fake_execute_test(test_file, allure_results):
        execute_calls.append(test_file)
        if test_file == "testcase/test_bash.py":
            return 1
        return 0

    monkeypatch.setattr(test_run, "execute_test", fake_execute_test)
    monkeypatch.setattr(
        test_run,
        "run_push_images_manual_non_interactive",
        lambda **kwargs: push_called.append(True),
    )

    code = test_run.run_app(mode="push", env="fat", picture_num=1, address_no=1, threads=1)

    assert code == 1
    assert execute_calls == ["testcase/test_get_accesstoken.py", "testcase/test_bash.py"]
    assert push_called == []


