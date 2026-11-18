"""AI管道统一入口点。

所有AI测试系统文件都保存在AI_testing_framework下，以避免
影响现有脚本的直接执行。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from AI_testing_framework.impact_engine import ImpactEngine, SCRIPT_DIR, DEFAULT_MAPPING_FILE
from AI_testing_framework.llm_provider import NoopLLMProvider, KeywordVoteLLMProvider

DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "impact_analysis_result.json")


def build_llm_provider(provider_name: str):
    name = (provider_name or "noop").strip().lower()
    if name == "keyword_vote":
        return KeywordVoteLLMProvider()
    return NoopLLMProvider()


def read_source_file(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    source_path = Path(str(path))
    if not source_path.exists():
        raise FileNotFoundError(f"source file not found: {source_path}")
    with source_path.open("r", encoding="utf-8") as f:
        return f.read().strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI管道统一入口")
    parser.add_argument("--trigger", choices=["backend", "algorithm"], required=True)
    parser.add_argument("--service", help="当trigger=algorithm时的算法服务名称")
    parser.add_argument("--source", help="当trigger=backend时的提交信息源文件")
    parser.add_argument("--diff", action="store_true", help="为后端分析启用git diff")
    parser.add_argument("--mapping", default=DEFAULT_MAPPING_FILE, help="module_mapping.yaml的路径")
    parser.add_argument("--llm-provider", choices=["noop", "keyword_vote"], default="noop")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="输出JSON路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    provider = build_llm_provider(args.llm_provider)
    engine = ImpactEngine(mapping_file=args.mapping, llm_provider=provider)

    if args.trigger == "backend":
        commit_message = read_source_file(args.source)
        result = engine.analyze_backend(
            commit_message=commit_message,
            changed_files=None,
            use_diff=bool(args.diff),
        )
    else:
        if not args.service:
            print("[ERROR] --service is required when --trigger=algorithm")
            return 2
        result = engine.analyze_algorithm(service_name=args.service)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"[TRIGGER] {result.trigger}")
    print(f"[DECISION] {result.trace.decision_path}")
    print(f"[PYTEST] {result.pytest_command}")
    print(f"[OUTPUT] {os.path.abspath(args.output)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

