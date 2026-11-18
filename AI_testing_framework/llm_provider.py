"""影响面分析的LLM回退提供者。

该模块故意提供安全的本地默认值，以便AI管道
可以不依赖外部API运行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol


class LLMProvider(Protocol):
    """模块推断回退接口。"""

    def infer_modules(self, text: str, module_names: List[str]) -> List[str]:
        """从自由文本推断受影响的模块名。"""


@dataclass
class NoopLLMProvider:
    """无操作回退提供者。

    保持行为确定性：不返回任何模块，让调用者运行完整测试。
    """

    def infer_modules(self, text: str, module_names: List[str]) -> List[str]:
        return []


@dataclass
class KeywordVoteLLMProvider:
    """用作访谈/演示回退的本地启发式提供者。

    不调用外部LLM API。通过令牌重叠对模块进行评分，
    返回最高评分的模块。
    """

    min_score: int = 1

    def infer_modules(self, text: str, module_names: List[str]) -> List[str]:
        tokens = [t for t in _tokenize(text) if len(t) >= 2]
        if not tokens:
            return []

        scored = []
        for module_name in module_names:
            score = 0
            lowered = module_name.lower()
            for token in tokens:
                if token in lowered:
                    score += 1
            if score >= self.min_score:
                scored.append((module_name, score))

        if not scored:
            return []

        max_score = max(score for _, score in scored)
        return [name for name, score in scored if score == max_score]


def _tokenize(text: str) -> List[str]:
    normalized = text.lower()
    separators = ["\n", "\t", ",", ".", ":", ";", "(", ")", "[", "]", "{", "}", "/", "\\", "|", "-", "_", "=", "\"", "'", "`"]
    for sep in separators:
        normalized = normalized.replace(sep, " ")
    return [part.strip() for part in normalized.split(" ") if part.strip()]

