"""验证AI模块映射配置。

检查：
1) module_mapping.yaml中的必需字段
2) pytest.ini中的marker存在
3) testcase/下的test_files存在
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Dict, List, Set

import yaml

SCRIPT_DIR: str = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT: str = os.path.dirname(SCRIPT_DIR)
DEFAULT_MAPPING: str = os.path.join(SCRIPT_DIR, "module_mapping.yaml")
DEFAULT_PYTEST_INI: str = os.path.join(PROJECT_ROOT, "pytest.ini")
TESTCASE_DIR: str = os.path.join(PROJECT_ROOT, "testcase")


def load_yaml(path: str) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_pytest_markers(pytest_ini: str) -> Set[str]:
    markers: Set[str] = set()
    marker_pattern = re.compile(r"^\s*([a-zA-Z0-9_]+)\s*:")
    with open(pytest_ini, "r", encoding="utf-8") as f:
        for line in f:
            matched = marker_pattern.match(line)
            if matched:
                markers.add(matched.group(1))
    return markers


def validate(mapping_path: str, pytest_ini: str) -> List[str]:
    issues: List[str] = []
    mapping = load_yaml(mapping_path)
    modules = mapping.get("modules", {})

    if not isinstance(modules, dict) or not modules:
        issues.append("module_mapping.yaml中modules为空或无效")
        return issues

    ini_markers = load_pytest_markers(pytest_ini)

    for module_key, cfg in modules.items():
        if not isinstance(cfg, dict):
            issues.append(f"模块{module_key}: 配置必须是字典")
            continue

        for key in ("keywords", "test_markers", "test_files"):
            if key not in cfg:
                issues.append(f"模块{module_key}: 缺少{key}")

        for marker in cfg.get("test_markers", []):
            if marker not in ini_markers:
                issues.append(f"模块{module_key}: marker {marker} 未在pytest.ini中找到")

        for test_file in cfg.get("test_files", []):
            target = os.path.join(TESTCASE_DIR, str(test_file))
            if not os.path.exists(target):
                issues.append(f"模块{module_key}: 测试文件缺失 {target}")

    services = mapping.get("algorithm_services", {})
    if isinstance(services, dict):
        for service_name, service_cfg in services.items():
            module = service_cfg.get("module") if isinstance(service_cfg, dict) else None
            if module and module not in modules:
                issues.append(f"算法服务{service_name}: 模块{module} 未在modules中找到")

    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证AI测试映射")
    parser.add_argument("--mapping", default=DEFAULT_MAPPING)
    parser.add_argument("--pytest-ini", default=DEFAULT_PYTEST_INI)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    issues = validate(args.mapping, args.pytest_ini)
    if issues:
        print("[失败] 映射验证失败:")
        for item in issues:
            print(f" - {item}")
        return 1

    print("[成功] 映射验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

