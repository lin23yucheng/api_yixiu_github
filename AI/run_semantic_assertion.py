"""语义断言引擎工具脚本。

功能：
1. 从历史 allure-results 构建 baseline
2. 对单条 JSON 响应做快速检查（便于本地试效果）
"""
import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from AI.semantic_assertion_engine import (
    SemanticAssertionEngine,
    build_baseline_from_allure,
    generate_semantic_summary_report,
)


def _load_json(json_text=None, json_file=None):
    if json_file:
        with open(json_file, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    if json_text:
        return json.loads(json_text)
    return None


def main():
    parser = argparse.ArgumentParser(description="语义断言引擎工具")
    parser.add_argument("--build-baseline", action="store_true", help="从allure-results构建baseline")
    parser.add_argument("--allure-dir", default="report/allure-results", help="allure-results目录")
    parser.add_argument("--baseline-file", default="config/semantic_baseline.json", help="baseline输出路径")

    parser.add_argument("--check", action="store_true", help="对单条响应进行语义检查")
    parser.add_argument("--method", default="GET", help="HTTP方法")
    parser.add_argument("--url", default="http://localhost/api/demo", help="请求URL")
    parser.add_argument("--status", type=int, default=200, help="HTTP状态码")
    parser.add_argument("--json", help="JSON字符串")
    parser.add_argument("--json-file", help="JSON文件路径")

    parser.add_argument("--summary", action="store_true", help="生成语义问题汇总报告")
    parser.add_argument("--summary-dir", default="report/semantic", help="语义汇总输出目录")
    parser.add_argument("--no-llm-review", action="store_true", help="汇总时禁用LLM二次复核")

    args = parser.parse_args()

    if args.build_baseline:
        baseline = build_baseline_from_allure(args.allure_dir, args.baseline_file)
        print(f"Baseline构建完成，endpoint数: {len(baseline.get('endpoints', {}))}")
        print(f"输出文件: {os.path.abspath(args.baseline_file)}")

    if args.check:
        body = _load_json(args.json, args.json_file)
        if body is None:
            raise ValueError("--check 模式需要提供 --json 或 --json-file")

        engine = SemanticAssertionEngine(enabled=True, strict=False, baseline_file=args.baseline_file)
        result = engine.evaluate(
            method=args.method,
            url=args.url,
            status_code=args.status,
            response_body=body,
        )
        print(engine.format_markdown_report(result))

    if args.summary:
        summary_path = generate_semantic_summary_report(
            report_dir=args.summary_dir,
            use_llm_review=not args.no_llm_review,
        )
        print(f"语义问题汇总报告: {os.path.abspath(summary_path)}")


if __name__ == "__main__":
    main()


