"""核心影响面分析引擎。

设计目标：
- 将AI管道逻辑与现有测试脚本隔离。
- 为访谈/演示场景提供可解释的输出。
- 支持后端提交触发和算法服务触发。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Union

import yaml

from AI_testing_framework.llm_provider import LLMProvider, NoopLLMProvider

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_MAPPING_FILE = os.path.join(SCRIPT_DIR, "module_mapping.yaml")


@dataclass
class DecisionTrace:
    decision_path: str
    matched_keywords: Dict[str, List[str]]
    changed_files: List[str]
    commit_message: str


@dataclass
class ImpactAnalysisResult:
    trigger: str
    affected_modules: List[Union[str, Dict[str, str]]]
    pytest_command: str
    trace: DecisionTrace

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        return payload


class ImpactEngine:
    def __init__(self, mapping_file: str = DEFAULT_MAPPING_FILE, llm_provider: Optional[LLMProvider] = None):
        self.mapping_file = mapping_file
        self.llm_provider = llm_provider or NoopLLMProvider()
        self.mapping = self._load_mapping()

    def _load_mapping(self) -> Dict[str, object]:
        with open(self.mapping_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data

    def get_changed_files(self) -> List[str]:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
            )
            if result.returncode != 0:
                return []
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            return []

    def get_latest_commit_message(self) -> str:
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%B"],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
            )
            if result.returncode != 0:
                return ""
            return result.stdout.strip()
        except Exception:
            return ""

    def keyword_match(self, text: str) -> Dict[str, List[str]]:
        text_lower = text.lower()
        hits: Dict[str, List[str]] = {}
        modules_raw = self.mapping.get("modules", {})
        modules = modules_raw if isinstance(modules_raw, dict) else {}
        for module_key, config in modules.items():
            config_dict = config if isinstance(config, dict) else {}
            keywords = config_dict.get("keywords", [])
            matched = [kw for kw in keywords if str(kw).lower() in text_lower]
            if matched:
                hits[module_key] = matched
        return hits

    def analyze_backend(
        self,
        commit_message: Optional[str] = None,
        changed_files: Optional[List[str]] = None,
        use_diff: bool = True,
    ) -> ImpactAnalysisResult:
        commit_message = commit_message if commit_message is not None else self.get_latest_commit_message()
        if changed_files is None:
            changed_files = self.get_changed_files() if use_diff else []

        merged_text = f"{commit_message} {' '.join(changed_files)}".strip()
        keyword_hits = self.keyword_match(merged_text)

        if keyword_hits:
            affected_modules: List[Union[str, Dict[str, str]]] = sorted(keyword_hits.keys())
            decision_path = "keyword"
        else:
            modules_raw = self.mapping.get("modules", {})
            modules = modules_raw if isinstance(modules_raw, dict) else {}
            module_names = list(modules.keys())
            llm_modules = self.llm_provider.infer_modules(merged_text, module_names)
            affected_modules = sorted(llm_modules)
            decision_path = "llm_fallback" if llm_modules else "full_regression"

        command = self.generate_pytest_command(affected_modules)
        trace = DecisionTrace(
            decision_path=decision_path,
            matched_keywords=keyword_hits,
            changed_files=changed_files,
            commit_message=commit_message,
        )
        return ImpactAnalysisResult(
            trigger="backend",
            affected_modules=affected_modules,
            pytest_command=command,
            trace=trace,
        )

    def analyze_algorithm(self, service_name: str) -> ImpactAnalysisResult:
        services_raw = self.mapping.get("algorithm_services", {})
        services = services_raw if isinstance(services_raw, dict) else {}
        service_config = services.get(service_name)

        affected_modules: List[Union[str, Dict[str, str]]] = []
        decision_path = "algorithm_rule"
        if service_config:
            item = {
                "module": service_config.get("module", ""),
                "run_mode": service_config.get("run_mode", "full"),
            }
            if service_config.get("run_until"):
                item["run_until"] = service_config["run_until"]
            affected_modules = [item]
        else:
            decision_path = "algorithm_rule_missing"

        command = self.generate_pytest_command(affected_modules)
        trace = DecisionTrace(
            decision_path=decision_path,
            matched_keywords={},
            changed_files=[],
            commit_message="",
        )
        return ImpactAnalysisResult(
            trigger="algorithm",
            affected_modules=affected_modules,
            pytest_command=command,
            trace=trace,
        )

    def generate_pytest_command(self, affected_modules: List[Union[str, Dict[str, str]]]) -> str:
        if not affected_modules:
            return "pytest testcase/ -v"

        markers: List[str] = []
        run_until = None
        modules_raw = self.mapping.get("modules", {})
        modules = modules_raw if isinstance(modules_raw, dict) else {}

        for item in affected_modules:
            if isinstance(item, dict):
                module_key = item.get("module")
                if module_key in modules:
                    module_cfg = modules[module_key] if isinstance(modules[module_key], dict) else {}
                    markers.extend(module_cfg.get("test_markers", []))
                if item.get("run_until"):
                    run_until = item["run_until"]
            elif item in modules:
                module_cfg = modules[item] if isinstance(modules[item], dict) else {}
                markers.extend(module_cfg.get("test_markers", []))

        # 保留marker顺序，同时删除重复项。
        unique_markers = list(dict.fromkeys(markers))
        if not unique_markers:
            return "pytest testcase/ -v"

        marker_expr = " or ".join(unique_markers)
        command = f'pytest -m "{marker_expr}" -v'
        if run_until:
            command += f" --run-until={run_until}"
        return command

