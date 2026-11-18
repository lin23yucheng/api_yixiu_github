"""
质量度量收集器
放到 conftest.py 中，每次pytest执行自动收集

三个核心指标：
  1. 漏测率 = 线上缺陷数 / (线上缺陷数 + 测试发现缺陷数)
  2. 自动化有效率 = 自动化发现真正缺陷数 / 自动化用例总数
  3. 语义断言捕获率 = 语义断言额外捕获问题数 / 传统断言能捕获问题数

产出：metrics/ 目录下的JSON文件，按日期归档
"""

import json
import os
from datetime import datetime
import pytest

# ============ 以下代码追加到 conftest.py ============

METRICS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics")

# 执行统计
_stats = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "errors": 0,
    "by_module": {},
    "by_marker": {},
    "semantic_assertion_hits": 0,
    "traditional_assertion_hits": 0,
    "bug_caught_by_auto": 0,
    "start_time": None,
    "end_time": None,
}

# nodeid -> {"module": str, "markers": List[str]}
_item_meta = {}


def _to_int(value):
    """将统计值安全转换为整数，避免类型检查告警。"""
    return value if isinstance(value, int) else 0


def _get_module_name(item):
    """从测试项的marker获取模块名"""
    for marker in item.iter_markers("module"):
        return marker.args[0] if marker.args else None
    return "unknown"


def _get_markers(item):
    """获取测试项的所有marker"""
    return [m.name for m in item.iter_markers()]


def pytest_collection_modifyitems(session, config, items):
    """在收集阶段缓存每个测试项的module/marker信息，供执行阶段统计使用。"""
    del session, config
    global _item_meta
    _item_meta = {}
    for item in items:
        nodeid = getattr(item, "nodeid", "")
        if not nodeid:
            continue
        _item_meta[nodeid] = {
            "module": _get_module_name(item),
            "markers": _get_markers(item),
        }


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logreport(report):
    """收集每个测试的执行结果"""
    global _stats

    if report.when != "call":
        return

    _stats["total"] += 1

    if report.passed:
        _stats["passed"] += 1
    elif report.failed:
        _stats["failed"] += 1
    elif report.skipped:
        _stats["skipped"] += 1

    # 按nodeid获取收集阶段缓存的元信息，避免依赖report.item。
    meta = _item_meta.get(getattr(report, "nodeid", ""), {})
    module = meta.get("module", "unknown")
    markers = meta.get("markers", [])

    if module not in _stats["by_module"]:
        _stats["by_module"][module] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    _stats["by_module"][module]["total"] += 1
    if report.passed:
        _stats["by_module"][module]["passed"] += 1
    elif report.failed:
        _stats["by_module"][module]["failed"] += 1
    elif report.skipped:
        _stats["by_module"][module]["skipped"] += 1

    # 按marker统计（保持原有字段结构兼容）。
    for marker_name in markers:
        if marker_name not in _stats["by_marker"]:
            _stats["by_marker"][marker_name] = {"total": 0, "passed": 0, "failed": 0}
        _stats["by_marker"][marker_name]["total"] += 1
        if report.passed:
            _stats["by_marker"][marker_name]["passed"] += 1
        elif report.failed:
            _stats["by_marker"][marker_name]["failed"] += 1


def pytest_sessionstart(session):
    """记录开始时间"""
    _stats["start_time"] = datetime.now().isoformat()


def pytest_sessionfinish(session, exitstatus):
    """会话结束，保存度量数据"""
    del session, exitstatus
    _stats["end_time"] = datetime.now().isoformat()

    # 计算通过率
    total = _to_int(_stats.get("total"))
    passed = _to_int(_stats.get("passed"))
    if total > 0:
        _stats["pass_rate"] = round(passed / total * 100, 2)
    else:
        _stats["pass_rate"] = 0

    # 保存（先清理旧文件，只保留最新一份）
    os.makedirs(METRICS_DIR, exist_ok=True)
    for old_file in os.listdir(METRICS_DIR):
        if old_file.startswith("metrics_") and old_file.endswith(".json"):
            try:
                os.remove(os.path.join(METRICS_DIR, old_file))
            except OSError:
                pass
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(METRICS_DIR, f"metrics_{date_str}.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(_stats, f, ensure_ascii=False, indent=2)

    print(f"\n[质量度量] 本次执行统计:")
    print(f"  总用例: {_stats['total']}")
    print(f"  通过: {_stats['passed']} | 失败: {_stats['failed']} | 跳过: {_stats['skipped']}")
    print(f"  通过率: {_stats['pass_rate']}%")
    print(f"  度量数据已保存: {output_file}")


# ============ 质量度量计算（独立脚本，定期运行） ============


def calc_leakage_rate(online_bugs, test_bugs):
    """
    漏测率 = 线上缺陷数 / (线上缺陷数 + 测试发现缺陷数)

    online_bugs: 线上发现的缺陷数（需手动维护）
    test_bugs: 测试阶段发现的缺陷数（需手动维护）

    示例: calc_leakage_rate(3, 27) → 10%
    """
    if online_bugs + test_bugs == 0:
        return 0
    return round(online_bugs / (online_bugs + test_bugs) * 100, 2)


def calc_auto_effective_rate(bugs_caught_by_auto, total_auto_cases):
    """
    自动化有效率 = 自动化发现的真正缺陷数 / 自动化用例总数

    bugs_caught_by_auto: 自动化用例发现的真正bug数（需手动维护）
    total_auto_cases: 自动化用例总数（从metrics自动获取）

    示例: calc_auto_effective_rate(5, 267) → 1.87%
    """
    if total_auto_cases == 0:
        return 0
    return round(bugs_caught_by_auto / total_auto_cases * 100, 2)


def calc_semantic_capture_rate(semantic_extra_hits, traditional_hits):
    """
    语义断言捕获率 = 语义断言额外捕获问题数 / 传统断言能捕获问题数

    semantic_extra_hits: 语义断言比传统断言多捕获的问题数
    traditional_hits: 传统断言能捕获的问题数

    示例: calc_semantic_capture_rate(8, 15) → 53.3%
    """
    if traditional_hits == 0:
        return 0
    return round(semantic_extra_hits / traditional_hits * 100, 2)


if __name__ == "__main__":
    # 手动计算质量度量指标
    print("=== 质量度量计算器 ===\n")

    # 示例数据，实际需替换
    print("1. 漏测率")
    print(f"   示例: 线上3个bug，测试发现27个 → {calc_leakage_rate(3, 27)}%\n")

    print("2. 自动化有效率")
    print(f"   示例: 自动化发现5个bug，267个用例 → {calc_auto_effective_rate(5, 267)}%\n")

    print("3. 语义断言捕获率")
    print(f"   示例: 语义断言多捕获8个问题，传统断言捕获15个 → {calc_semantic_capture_rate(8, 15)}%\n")

    print("提示: 三个指标的分子需要手动维护，分母可从metrics/目录自动获取")
