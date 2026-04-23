import importlib.util
from pathlib import Path
import sys


def _load_test_run_module():
    module_path = Path(__file__).resolve().parent / "test_run.py"
    project_root = str(module_path.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    spec = importlib.util.spec_from_file_location("test_run", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


test_run = _load_test_run_module()


def test_push_mode_runs_prerequisites_before_push(monkeypatch):
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

