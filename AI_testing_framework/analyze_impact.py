"""影响面分析兼容CLI。

该文件保持原始命令风格，同时将逻辑委托给
`impact_engine.py`。输出现在写入AI_testing_framework文件夹。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Union

from AI_testing_framework.impact_engine import ImpactEngine, SCRIPT_DIR

OUTPUT_FILE = os.path.join(SCRIPT_DIR, "impact_analysis_result.json")
_engine = ImpactEngine()


def load_mapping() -> Dict[str, object]:
    return _engine.mapping


def get_changed_files() -> List[str]:
    return _engine.get_changed_files()


def get_commit_messages() -> str:
    return _engine.get_latest_commit_message()


def keyword_match(text: str, mapping: Optional[Dict[str, object]] = None) -> List[str]:
    hits = _engine.keyword_match(text)
    return sorted(hits.keys())


def ask_llm_fallback(text: str, module_names: List[str]) -> List[str]:
    # 保持旧函数签名以实现兼容性。
    return _engine.llm_provider.infer_modules(text, module_names)


def analyze_backend_commit(commit_message: Optional[str] = None, changed_files: Optional[List[str]] = None):
    result = _engine.analyze_backend(commit_message=commit_message, changed_files=changed_files, use_diff=changed_files is None)
    return result.affected_modules


def analyze_algorithm_deploy(service_name: str):
    result = _engine.analyze_algorithm(service_name)
    return result.affected_modules


def generate_pytest_command(affected_modules: List[Union[str, Dict[str, str]]], mapping: Optional[Dict[str, object]] = None) -> str:
    return _engine.generate_pytest_command(affected_modules)


def main() -> int:
    parser = argparse.ArgumentParser(description="AI影响面分析")
    parser.add_argument("--trigger", choices=["backend", "algorithm"], required=True)
    parser.add_argument("--source", help="commit message来源文件（backend模式）")
    parser.add_argument("--diff", action="store_true", help="自动从git diff获取变更（backend模式）")
    parser.add_argument("--service", help="算法服务名称（algorithm模式）")
    args = parser.parse_args()

    if args.trigger == "backend":
        commit_message = None
        if args.source:
            if not os.path.exists(args.source):
                print(f"[ERROR] source file not found: {args.source}")
                return 2
            with open(args.source, "r", encoding="utf-8") as f:
                commit_message = f.read().strip()

        result = _engine.analyze_backend(
            commit_message=commit_message,
            changed_files=None,
            use_diff=bool(args.diff),
        )
    else:
        if not args.service:
            print("[ERROR] 算法服务模式需要指定 --service 参数")
            return 2
        result = _engine.analyze_algorithm(args.service)

    print(f"[RESULT] trigger={result.trigger}, path={result.trace.decision_path}")
    print(f"[COMMAND] 执行命令: {result.pytest_command}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"[OUTPUT] 结果已写入: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
