"""用于访谈/演示的小型自检运行器。

执行：
1) 映射验证
2) 来自内联文本的后端分析
3) 算法分析示例
"""

from __future__ import annotations

import json
import os

from AI_testing_framework.impact_engine import ImpactEngine, SCRIPT_DIR
from AI_testing_framework.validate_mapping import validate, DEFAULT_MAPPING, DEFAULT_PYTEST_INI


def main() -> int:
    issues = validate(DEFAULT_MAPPING, DEFAULT_PYTEST_INI)
    if issues:
        print("[自检] 映射验证失败")
        for item in issues:
            print(f" - {item}")
        return 1

    engine = ImpactEngine()

    backend = engine.analyze_backend(
        commit_message="fix: 修复训练服务与v8模型创建逻辑",
        changed_files=["api/api_deep_training_tasks.py", "testcase/test_deep_model_training_v8.py"],
        use_diff=False,
    )

    algorithm = engine.analyze_algorithm("切图服务")

    output = {
        "backend": backend.to_dict(),
        "algorithm": algorithm.to_dict(),
    }

    out_file = os.path.join(SCRIPT_DIR, "selfcheck_result.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[自检] 成功，输出: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

