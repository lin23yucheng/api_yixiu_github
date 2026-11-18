"""
语义感知断言引擎

目标：在接口返回 2xx 且传统断言通过时，补充语义层面的异常检测，识别潜在"假通过"。
"""
import json
import os
import re
import glob
import ast
import fnmatch
import threading
import functools
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse
from collections import Counter

from common.Log import MyLog
from AI.ai_analyzer import _load_ai_config, call_llm_api
from AI.semantic_record_filters import annotate_semantic_record


ERROR_KEYWORDS = ["error", "fail", "failed", "exception", "traceback", "错误", "失败", "异常"]
SUCCESS_KEYWORDS = ["success", "ok", "成功", "完成"]

# ─── 线程级 suppress-context 支持 ────────────────────────────────────────────
_suppress_local = threading.local()
_expected_failure_local = threading.local()
_step_local = threading.local()


def _get_step_stack():
    stack = getattr(_step_local, "stack", None)
    if stack is None:
        stack = []
        _step_local.stack = stack
    return stack


class _TrackedAllureStep:
    """Wrap allure.step return value to keep a thread-local step stack for runtime audit."""

    def __init__(self, inner_step, title):
        self._inner_step = inner_step
        self._title = str(title or "")

    def __enter__(self):
        _get_step_stack().append(self._title)
        try:
            return self._inner_step.__enter__()
        except Exception:
            stack = _get_step_stack()
            if stack:
                stack.pop()
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return self._inner_step.__exit__(exc_type, exc_val, exc_tb)
        finally:
            stack = _get_step_stack()
            if stack:
                stack.pop()

    def __call__(self, func):
        wrapped = self._inner_step(func)

        @functools.wraps(wrapped)
        def _decorated(*args, **kwargs):
            title = self._title
            try:
                title = self._title.format(*args, **kwargs)
            except Exception:
                # 格式化失败时回退为模板原文，避免影响原始执行。
                pass

            _get_step_stack().append(title)
            try:
                return wrapped(*args, **kwargs)
            finally:
                stack = _get_step_stack()
                if stack:
                    stack.pop()

        return _decorated

    def __getattr__(self, item):
        return getattr(self._inner_step, item)


def _install_allure_step_tracker():
    try:
        import allure
    except Exception:
        return

    if getattr(allure, "_semantic_step_tracker_installed", False):
        return

    original_step = getattr(allure, "step", None)
    if not callable(original_step):
        return

    @functools.wraps(original_step)
    def _tracked_step(title):
        return _TrackedAllureStep(original_step(title), title)

    allure.step = _tracked_step
    allure._semantic_step_tracker_installed = True


@contextmanager
def semantic_no_audit(reason: str = ""):
    """
    上下文管理器：在 with 块内的所有接口调用跳过语义审计写入。
    适用于测试用例中已知预期中间失败态的重试步骤。

    用法::

        from AI.semantic_assertion_engine import semantic_no_audit

        with semantic_no_audit("撤回样本首次可能返回 ES 插入中错误，属于正常重试"):
            response = self.api_xxx.dataset_withdraw(dataset_id)
    """
    _suppress_local.active = True
    _suppress_local.reason = reason or "caller suppressed"
    try:
        yield
    finally:
        _suppress_local.active = False
        _suppress_local.reason = ""


def _is_caller_suppressed():
    return getattr(_suppress_local, "active", False)


@contextmanager
def semantic_expected_failure(reason: str = ""):
    """
    标记 with 块内的接口调用为“预期业务失败”。

    用于负向用例中明确断言接口应返回 success=False / 非成功业务 code 的场景。
    它不会跳过语义审计，只会让汇总报告把该记录归入“预期异常/负向场景”。
    """
    previous_active = getattr(_expected_failure_local, "active", False)
    previous_reason = getattr(_expected_failure_local, "reason", "")
    _expected_failure_local.active = True
    _expected_failure_local.reason = reason or "expected business failure"
    try:
        yield
    finally:
        _expected_failure_local.active = previous_active
        _expected_failure_local.reason = previous_reason


def get_expected_failure_context():
    return {
        "semantic_expected": bool(getattr(_expected_failure_local, "active", False)),
        "expected_reason": getattr(_expected_failure_local, "reason", ""),
    }


def get_current_allure_context():
    """获取当前 Allure 上下文信息（step 名、test 名等）"""
    import os
    context = {
        "test_file": os.environ.get("CURRENT_TEST_FILE", ""),
        "test_name": os.environ.get("CURRENT_TEST_NAME", ""),
        "test_class": os.environ.get("CURRENT_TEST_CLASS", ""),
    }
    context.update(get_expected_failure_context())

    _install_allure_step_tracker()
    step_stack = _get_step_stack()
    if step_stack:
        context["step_name"] = step_stack[-1]
        return context

    # 尝试从 allure 上下文获取当前 step 信息
    try:
        import allure
        if hasattr(allure, "_allure") and hasattr(allure._allure, "lifecycle"):
            lifecycle = allure._allure.lifecycle
            if hasattr(lifecycle, "_container"):
                # 获取当前最内层的容器（step）
                container = getattr(lifecycle, "_container", None)
                if container:
                    step_name = getattr(container, "name", "")
                    context["step_name"] = step_name
    except Exception:
        pass

    return context


def _to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on", "y"}


def _safe_json_loads(text):
    try:
        return json.loads(text)
    except Exception:
        try:
            # 兼容 allure 附件中以 Python 字典字符串保存的响应体
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            pass
        return None


def normalize_endpoint(method, url):
    """将 URL 归一化成可聚合的 endpoint key。"""
    parsed = urlparse(url or "")
    path = parsed.path or "/"
    # 将数字ID统一替换，避免 baseline 过度碎片化
    path = re.sub(r"/\d+", "/{id}", path)
    method = (method or "GET").upper()
    return f"{method} {path}"


@dataclass
class SemanticFinding:
    level: str
    rule: str
    message: str


@dataclass
class SemanticResult:
    endpoint: str
    score: int = 100
    risk: str = "LOW"
    findings: list = field(default_factory=list)
    suppressed: bool = False
    suppress_reason: str = ""
    expected: bool = False
    expected_reason: str = ""

    @property
    def should_fail(self):
        return self.risk == "HIGH" and not self.suppressed and not self.expected


def _risk_from_score(score):
    if score < 60:
        return "HIGH"
    if score < 80:
        return "MEDIUM"
    return "LOW"


def _load_engine_config():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = {
        "enabled": bool(_to_bool(os.environ.get("SEMANTIC_ASSERT_ENABLED", "true"), True)),
        "strict": bool(_to_bool(os.environ.get("SEMANTIC_ASSERT_STRICT", "false"), False)),
        "baseline_file": os.environ.get(
            "SEMANTIC_ASSERT_BASELINE_FILE",
            os.path.join(base_dir, "config", "semantic_baseline.json"),
        ),
        "suppress_rules_file": os.path.join(base_dir, "config", "semantic_suppress_rules.json"),
    }

    ini_path = os.path.join(base_dir, "config", "semantic_assertion.ini")
    if os.path.exists(ini_path):
        import configparser

        parser = configparser.ConfigParser()
        parser.read(ini_path, encoding="utf-8")
        sec = "semantic_assertion"
        if parser.has_section(sec):
            cfg["enabled"] = bool(_to_bool(parser.get(sec, "enabled", fallback=str(cfg["enabled"])), cfg["enabled"]))
            cfg["strict"] = bool(_to_bool(parser.get(sec, "strict", fallback=str(cfg["strict"])), cfg["strict"]))
            cfg["baseline_file"] = parser.get(sec, "baseline_file", fallback=cfg["baseline_file"])
            cfg["suppress_rules_file"] = parser.get(sec, "suppress_rules_file", fallback=cfg["suppress_rules_file"])

    if cfg.get("baseline_file") and not os.path.isabs(str(cfg["baseline_file"])):
        cfg["baseline_file"] = os.path.join(base_dir, str(cfg["baseline_file"]))
    if cfg.get("suppress_rules_file") and not os.path.isabs(str(cfg["suppress_rules_file"])):
        cfg["suppress_rules_file"] = os.path.join(base_dir, str(cfg["suppress_rules_file"]))
    return cfg


def _load_llm_review_config():
    cfg = {
        "enabled": bool(_to_bool(os.environ.get("SEMANTIC_LLM_REVIEW_ENABLED", "true"), True)),
        "max_cases": int(os.environ.get("SEMANTIC_LLM_REVIEW_MAX_CASES", "8")),
    }

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(base_dir, "config", "semantic_assertion.ini")
    if os.path.exists(ini_path):
        import configparser

        parser = configparser.ConfigParser()
        parser.read(ini_path, encoding="utf-8")
        sec = "llm_second_review"
        if parser.has_section(sec):
            cfg["enabled"] = bool(_to_bool(parser.get(sec, "enabled", fallback=str(cfg["enabled"])), cfg["enabled"]))
            cfg["max_cases"] = int(parser.get(sec, "max_cases", fallback=str(cfg["max_cases"])))
    return cfg


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_semantic_report_dir():
    return os.path.join(_project_root(), "report", "semantic")


def get_semantic_runtime_dir(report_dir=None):
    base = report_dir or get_semantic_report_dir()
    return os.path.join(base, "runtime")


def append_semantic_audit(record, report_dir=None):
    """将单次语义检查结果写入 runtime 审计文件（按进程分片）。"""
    runtime_dir = get_semantic_runtime_dir(report_dir)
    os.makedirs(runtime_dir, exist_ok=True)
    pid = os.getpid()
    file_path = os.path.join(runtime_dir, f"semantic_audit_{pid}.jsonl")
    payload = dict(record)
    payload["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_semantic_audits(report_dir=None):
    runtime_dir = get_semantic_runtime_dir(report_dir)
    files = glob.glob(os.path.join(runtime_dir, "semantic_audit_*.jsonl"))
    records = []
    for file_path in files:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip().lstrip("\ufeff")
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
    return records


def _build_llm_second_review(high_risk_cases, report_stats):
    review_cfg = _load_llm_review_config()
    ai_cfg = _load_ai_config()
    model_name = ai_cfg.get("model", "unknown")
    provider_label = ai_cfg.get("provider_label", ai_cfg.get("provider", "LLM"))
    token_env = ai_cfg.get("token_env", "UNKNOWN")

    if not review_cfg["enabled"]:
        return f"LLM二次复核未启用。（已配置模型：{provider_label} {model_name}）"

    if not high_risk_cases:
        return (
            "本轮无 HIGH 风险样本，LLM 二次复核已跳过。\n\n"
            "- 结论：当前报告没有可供复核的高风险证据，避免输出经验性建议。\n"
            "- 建议：如需提升检出率，请补充 baseline 或扩展规则后再复核。"
        )

    if not ai_cfg.get("token"):
        return (
            f"LLM二次复核已启用，但未配置 {provider_label} Token（{token_env}），"
            f"已跳过。（已配置模型：{model_name}）"
        )

    max_cases = max(1, review_cfg["max_cases"])
    sample_cases = high_risk_cases[:max_cases]
    case_lines = []
    for idx, case in enumerate(sample_cases, 1):
        findings = case.get("findings", [])
        finding_text = "; ".join([f"{f.get('rule')}: {f.get('message')}" for f in findings])
        case_lines.append(
            f"[{idx}] endpoint={case.get('endpoint')} score={case.get('score')} risk={case.get('risk')} "
            f"status={case.get('status_code')} file={case.get('test_file', '')}\n"
            f"test={case.get('test_name', '')}\n"
            f"step={case.get('step_name', '')}\n"
            f"response={case.get('response_summary', '')[:300]}\n"
            f"findings={finding_text[:600]}"
        )

    prompt = (
        "你是资深接口测试专家。请对以下语义断言高风险结果进行二次复核。"
        "仅可基于样本中给出的 test、step、response、findings 证据下结论，不允许输出泛化经验建议。"
        "样本已排除 semantic_expected=true 的显式预期异常记录；不要仅凭 test 或 step 名称推断负向场景。"
        "输出中文结论，按以下结构：\n"
        "1) 误报可能性评估（逐条）\n"
        "2) 建议立即阻断的项\n"
        "3) 建议补充的断言模板（pytest风格）\n"
        "4) 本轮优先修复Top5\n\n"
        "补充要求：每条结论必须引用 rule 或 finding 原文；"
        "如果证据不足，请明确写'证据不足，不建议阻断'。\n\n"
        f"统计信息: {json.dumps(report_stats, ensure_ascii=False)}\n"
        f"高风险样本:\n{chr(10).join(case_lines)}"
    )
    return call_llm_api(prompt, ai_cfg)


def _cleanup_old_reports(directory: str, pattern: str, keep: int = 3) -> None:
    """清理旧报告，仅保留最新 `keep` 份匹配 `pattern` 的文件（按文件名降序）。"""
    matched = sorted(glob.glob(os.path.join(directory, pattern)), reverse=True)
    for path in matched[keep:]:
        try:
            os.remove(path)
            MyLog.info(f"已清理旧报告: {path}")
        except Exception as e:
            MyLog.warning(f"清理旧报告失败 {path}: {e}")


def generate_semantic_summary_report(report_dir=None, use_llm_review=True, keep: int = 3):
    """生成语义问题汇总报告（Markdown），以测试文件→用例→步骤分层展示，可选对高风险项进行 LLM 二次复核。"""
    base_dir = report_dir or get_semantic_report_dir()
    os.makedirs(base_dir, exist_ok=True)
    records = _load_semantic_audits(base_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(base_dir, f"semantic_summary_{timestamp}.md")

    def _write_and_latest(content):
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)
        latest_path = os.path.join(base_dir, "semantic_summary_latest.md")
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(content)
        # 只清理带时间戳的历史文件（以年份开头，避免误删 *_latest.md 等固定文件）
        _cleanup_old_reports(base_dir, "semantic_summary_2*.md", keep=keep)

    if not records:
        content = "# 语义问题汇总报告\n\n无可用语义审计数据。"
        _write_and_latest(content)
        return report_path

    records = [annotate_semantic_record(r) for r in records]
    total = len(records)
    with_findings = [r for r in records if r.get("findings")]

    # 区分：抑制、负向/预期异常、真实命中
    suppressed_recs = [r for r in with_findings if r.get("suppressed")]
    expected_recs = [
        r for r in with_findings
        if not r.get("suppressed") and r.get("semantic_expected")
    ]
    real_findings = [
        r for r in with_findings
        if not r.get("suppressed") and not r.get("semantic_expected")
    ]

    high_risk   = [r for r in real_findings if r.get("risk") == "HIGH"]
    medium_risk = [r for r in real_findings if r.get("risk") == "MEDIUM"]
    low_risk    = [r for r in real_findings if r.get("risk") == "LOW"]

    endpoint_counter = Counter([r.get("endpoint", "") for r in real_findings])
    rule_counter = Counter()
    for rec in real_findings:
        for f in rec.get("findings", []):
            rule_counter[f.get("rule", "unknown")] += 1

    report_stats = {
        "total_checks":    total,
        "with_findings":   len(with_findings),
        "real_findings":   len(real_findings),
        "suppressed":      len(suppressed_recs),
        "expected":        len(expected_recs),
        "high_risk":       len(high_risk),
        "medium_risk":     len(medium_risk),
        "low_risk":        len(low_risk),
    }

    # 读取当前 LLM 配置，报告中展示 provider + model，避免多 provider 时误判。
    ai_cfg = _load_ai_config()
    current_model = ai_cfg.get("model", "unknown")
    current_provider = ai_cfg.get("provider_label", ai_cfg.get("provider", "LLM"))

    lines = [
        "# 语义问题汇总报告",
        "",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 使用模型: {current_provider} ({current_model})",
        "",
        "## 统计概览",
        f"- 总检查次数: {report_stats['total_checks']}",
        f"- 命中问题次数: {report_stats['with_findings']} "
        f"（真实问题: {report_stats['real_findings']} | "
        f"预期异常/负向场景: {report_stats['expected']} | "
        f"已抑制/白名单: {report_stats['suppressed']}）",
        f"- HIGH: {report_stats['high_risk']} | MEDIUM: {report_stats['medium_risk']} | LOW: {report_stats['low_risk']}",
        "",
        "## Top 问题规则（仅真实命中）",
    ]
    if rule_counter:
        for rule, count in rule_counter.most_common(10):
            lines.append(f"- `{rule}`: {count}")
    else:
        lines.append("- 未发现真实规则命中")

    lines.extend(["", "## Top 风险接口（仅真实命中）"])
    if endpoint_counter:
        for endpoint, count in endpoint_counter.most_common(10):
            lines.append(f"- `{endpoint}`: {count}")
    else:
        lines.append("- 无")

    # ── 按测试文件分层展示，让用户一眼看出问题所在 ────────────────────────────
    lines.extend(["", "## 问题详情（按测试文件分层）"])

    # 按 test_file 分组
    by_test_file = {}
    for rec in real_findings:
        test_file = rec.get("test_file", "unknown")
        if test_file not in by_test_file:
            by_test_file[test_file] = []
        by_test_file[test_file].append(rec)

    if not by_test_file:
        lines.append("- 无")
    else:
        for test_file in sorted(by_test_file.keys()):
            recs_in_file = by_test_file[test_file]
            lines.append(f"### 📄 `{test_file}`")
            lines.append("")

            # 按 test_name 再分组
            by_test_name = {}
            for rec in recs_in_file:
                test_name = rec.get("test_name", "unknown")
                test_class = rec.get("test_class", "")
                key = f"{test_class}::{test_name}" if test_class else test_name
                if key not in by_test_name:
                    by_test_name[key] = []
                by_test_name[key].append(rec)

            for test_key in sorted(by_test_name.keys()):
                recs_in_test = by_test_name[test_key]
                lines.append(f"#### test_{test_key.split('::')[-1]}")
                lines.append("")

                # 展示该用例中的所有问题
                for idx, rec in enumerate(recs_in_test, 1):
                    step_name = rec.get("step_name", "")
                    endpoint = rec.get("endpoint", "")
                    status_code = rec.get("status_code", "")
                    risk = rec.get("risk", "")
                    request_summary = rec.get("request_summary", "")
                    response_summary = rec.get("response_summary", "")

                    lines.append(f"**{idx}. {endpoint}** (HTTP {status_code}) `[{risk}]`")
                    if step_name:
                        lines.append(f"   🧭 步骤: `{step_name}`")

                    # 显示请求/响应摘要，帮助用户快速定位问题
                    if request_summary:
                        lines.append(f"   📤 请求: `{request_summary}`")
                    if response_summary:
                        lines.append(f"   📥 响应: `{response_summary}`")

                    # 显示具体错误信息
                    findings = rec.get("findings", [])
                    if findings:
                        for f in findings:
                            lines.append(f"   - `{f.get('rule')}`: {f.get('message')}")

                    lines.append("")

    lines.extend(["", "## HIGH 风险明细"])
    if high_risk:
        for idx, rec in enumerate(high_risk[:20], 1):
            lines.append(
                f"{idx}. `{rec.get('endpoint')}` | score={rec.get('score')} | "
                f"status={rec.get('status_code')} | file={rec.get('test_file', '')}"
            )
            if rec.get("step_name"):
                lines.append(f"   step: {rec.get('step_name')}")

            # 显示请求/响应摘要
            if rec.get("request_summary"):
                lines.append(f"   req: `{rec.get('request_summary')}`")
            if rec.get("response_summary"):
                lines.append(f"   resp: `{rec.get('response_summary')}`")

            for f in rec.get("findings", []):
                lines.append(f"   - [{f.get('level')}] `{f.get('rule')}`: {f.get('message')}")
            lines.append("")
    else:
        lines.append("- 无")

    if expected_recs:
        lines.extend(["", "## 预期异常/负向场景记录"])
        lines.append(f"> 共 {len(expected_recs)} 条，已从风险统计中排除，仅供回顾。")
        lines.append("")

        expected_ep = Counter([r.get("endpoint", "") for r in expected_recs])
        lines.append("### Top 接口")
        for endpoint, count in expected_ep.most_common(10):
            lines.append(f"- `{endpoint}`: {count}")
        lines.append("")

        for idx, rec in enumerate(expected_recs[:20], 1):
            lines.append(
                f"{idx}. `{rec.get('endpoint')}` | risk={rec.get('risk')} | "
                f"status={rec.get('status_code')} | file={rec.get('test_file', '')}"
            )
            if rec.get("test_name"):
                lines.append(f"   test: {rec.get('test_name')}")
            if rec.get("step_name"):
                lines.append(f"   step: {rec.get('step_name')}")
            if rec.get("response_summary"):
                lines.append(f"   resp: `{rec.get('response_summary')}`")
            if rec.get("expected_reason"):
                lines.append(f"   reason: {rec.get('expected_reason')}")
            lines.append("")

    # 抑制记录单独汇总（透明可审查）
    if suppressed_recs:
        lines.extend(["", "## ⚑ 已抑制记录（白名单/预期中间状态）"])
        lines.append(f"> 共 {len(suppressed_recs)} 条，已从风险统计中排除，仅供回顾。")
        lines.append("")
        suppress_ep = Counter([r.get("endpoint", "") for r in suppressed_recs])
        for ep, cnt in suppress_ep.most_common():
            reason = next(
                (r.get("suppress_reason", "") for r in suppressed_recs if r.get("endpoint") == ep), ""
            )
            lines.append(f"- `{ep}`: {cnt} 次 — {reason}")

    if use_llm_review:
        lines.extend(["", "## LLM 二次复核", ""])
        try:
            review_text = _build_llm_second_review(high_risk, report_stats)
            lines.append(review_text)
        except Exception as e:
            lines.append(f"LLM二次复核失败: {e}")

    content = "\n".join(lines)
    _write_and_latest(content)
    return report_path


class SemanticAssertionEngine:
    def __init__(self, enabled=True, strict=False, baseline_file=None, suppress_rules_file=None):
        self.enabled = enabled
        self.strict = strict
        self.baseline_file = baseline_file
        self.suppress_rules_file = suppress_rules_file
        self.baseline = self._load_baseline()
        self.suppress_rules = self._load_suppress_rules()

    def _load_baseline(self):
        if not self.baseline_file or not os.path.exists(self.baseline_file):
            return {}
        try:
            with open(self.baseline_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("endpoints", {})
        except Exception as e:
            MyLog.warning(f"语义断言：加载baseline失败，将仅使用规则检测: {e}")
            return {}

    def _load_suppress_rules(self):
        if not self.suppress_rules_file or not os.path.exists(self.suppress_rules_file):
            return []
        try:
            with open(self.suppress_rules_file, "r", encoding="utf-8") as f:
                rules = json.load(f)
            MyLog.info(f"语义断言：加载 {len(rules)} 条抑制规则")
            return rules
        except Exception as e:
            MyLog.warning(f"语义断言：加载suppress_rules失败: {e}")
            return []

    def _match_suppress(self, endpoint, response_body):
        """
        检查是否命中抑制规则。
        返回 (matched: bool, rule_name: str, reason: str)
        """
        for rule in self.suppress_rules:
            pattern = rule.get("endpoint_pattern", "*")
            msg_filter = rule.get("msg_contains", "")

            # endpoint glob 匹配（先归一化同类斜杠方向，再匹配）
            ep_normalized = endpoint.replace("\\", "/")
            if not fnmatch.fnmatch(ep_normalized, pattern.replace("\\", "/")):
                continue

            # 可选：响应 msg 过滤
            if msg_filter:
                body_msg = ""
                if isinstance(response_body, dict):
                    body_msg = str(response_body.get("msg", "") or response_body.get("message", ""))
                if msg_filter not in body_msg:
                    continue

            return True, rule.get("name", "unnamed_rule"), rule.get("reason", "")

        return False, "", ""

    def evaluate(self, method, url, status_code, response_body):
        endpoint = normalize_endpoint(method, url)
        result = SemanticResult(endpoint=endpoint)

        if not self.enabled:
            return result

        self._apply_keyword_rules(status_code, response_body, result)
        self._apply_business_rules(status_code, response_body, result)
        self._apply_baseline_rules(endpoint, response_body, result)

        score = 100
        for finding in result.findings:
            if finding.level == "HIGH":
                score -= 30
            elif finding.level == "MEDIUM":
                score -= 15
            else:
                score -= 5
        result.score = max(0, score)
        result.risk = _risk_from_score(result.score)
        expected_context = get_expected_failure_context()
        result.expected = bool(expected_context["semantic_expected"])
        result.expected_reason = expected_context["expected_reason"]

        # ── 抑制规则匹配 ───────────────────────────────────────────────────────
        # 优先检查调用者显式 suppress 上下文
        if _is_caller_suppressed():
            result.suppressed = True
            result.suppress_reason = f"caller: {getattr(_suppress_local, 'reason', 'semantic_no_audit')}"
        elif result.findings:
            matched, rule_name, reason = self._match_suppress(endpoint, response_body)
            if matched:
                result.suppressed = True
                result.suppress_reason = f"rule '{rule_name}': {reason}"

        return result

    def _add_finding(self, result, level, rule, message):
        result.findings.append(SemanticFinding(level=level, rule=rule, message=message))

    def _apply_keyword_rules(self, status_code, body, result):
        """
        关键词规则（改进版）：只检查 msg/message 字段中的错误关键词。
        不扫描整个响应体，避免字段名/值中的无关关键词导致误报。
        """
        if not isinstance(body, dict):
            body_text = str(body).lower()
            has_error_kw = any(k in body_text for k in ERROR_KEYWORDS)
            if 200 <= int(status_code) < 300 and has_error_kw:
                self._add_finding(
                    result,
                    "HIGH",
                    "keyword_conflict",
                    "HTTP 2xx 但响应中包含错误关键词，疑似业务失败未被断言覆盖",
                )
            return

        # 只检查 msg/message 字段中的关键词（最可靠的业务状态指示符）
        msg = str(body.get("msg", "") or body.get("message", "")).lower()
        has_error_kw = any(k in msg for k in ERROR_KEYWORDS)
        has_success_kw = any(k in msg for k in SUCCESS_KEYWORDS)

        if 200 <= int(status_code) < 300 and has_error_kw:
            self._add_finding(
                result,
                "HIGH",
                "keyword_conflict",
                f"HTTP 2xx 但 msg 包含错误关键词 '{msg[:100]}'，疑似业务失败未被断言覆盖",
            )
        if int(status_code) >= 400 and has_success_kw:
            self._add_finding(
                result,
                "MEDIUM",
                "status_message_conflict",
                "HTTP 非2xx但 msg 含成功关键词，接口语义可能不一致",
            )

    def _apply_business_rules(self, status_code, body, result):
        if not isinstance(body, dict):
            return

        # success / ok 布尔标识冲突
        for key in ("success", "ok"):
            if key in body and body.get(key) is False and 200 <= int(status_code) < 300:
                self._add_finding(
                    result,
                    "HIGH",
                    "success_flag_false",
                    f"响应字段 {key}=False 且 HTTP 2xx，疑似假通过",
                )

        # code 语义冲突（常见成功码：0/200）
        if "code" in body:
            code_val = body.get("code")
            if isinstance(code_val, int) and 200 <= int(status_code) < 300 and code_val not in (0, 200):
                self._add_finding(
                    result,
                    "HIGH",
                    "business_code_unexpected",
                    f"业务 code={code_val} 不在常见成功码 [0, 200] 内",
                )

        # msg 提示成功但 data 为空，通常是弱风险，提示补充断言
        msg = str(body.get("msg", "") or body.get("message", "")).strip()
        data = body.get("data")
        if msg and any(kw in msg for kw in ["成功", "success", "ok"]):
            if data == [] or data == {} or data is None:
                self._add_finding(
                    result,
                    "LOW",
                    "empty_data_after_success",
                    "响应提示成功但 data 为空，建议补充核心字段断言",
                )

    def _apply_baseline_rules(self, endpoint, body, result):
        if not isinstance(body, dict):
            return
        profile = self.baseline.get(endpoint)
        if not profile:
            return

        required_top = profile.get("required_top_keys", [])
        for key in required_top:
            if key not in body:
                self._add_finding(
                    result,
                    "HIGH",
                    "missing_top_key",
                    f"缺少 baseline 要求的顶层字段: {key}",
                )

        required_data = profile.get("required_data_keys", [])
        data_obj = body.get("data", {})
        if required_data and isinstance(data_obj, dict):
            for key in required_data:
                if key not in data_obj:
                    self._add_finding(
                        result,
                        "MEDIUM",
                        "missing_data_key",
                        f"缺少 baseline 要求的 data 字段: {key}",
                    )

    @staticmethod
    def _body_to_text(body):
        if isinstance(body, (dict, list)):
            return json.dumps(body, ensure_ascii=False)
        return str(body)

    def format_markdown_report(self, semantic_result):
        lines = [
            f"Endpoint: `{semantic_result.endpoint}`",
            f"Score: **{semantic_result.score}** | Risk: **{semantic_result.risk}**",
        ]
        if semantic_result.suppressed:
            lines.append(f"⚑ SUPPRESSED — {semantic_result.suppress_reason}")
        if semantic_result.expected:
            lines.append(f"EXPECTED_FAILURE — {semantic_result.expected_reason}")
        if not semantic_result.findings:
            lines.append("- No semantic anomaly detected")
            return "\n".join(lines)

        lines.append("Findings:")
        for item in semantic_result.findings:
            prefix = "~~" if semantic_result.suppressed else ""
            suffix = "~~" if semantic_result.suppressed else ""
            lines.append(f"- [{item.level}] `{item.rule}`: {prefix}{item.message}{suffix}")
        return "\n".join(lines)


_DEFAULT_ENGINE = None


def get_default_engine():
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        cfg = _load_engine_config()
        _DEFAULT_ENGINE = SemanticAssertionEngine(
            enabled=bool(cfg["enabled"]),
            strict=bool(cfg["strict"]),
            baseline_file=cfg["baseline_file"],
            suppress_rules_file=cfg.get("suppress_rules_file"),
        )
        MyLog.info(
            "语义断言引擎初始化: "
            f"enabled={cfg['enabled']}, strict={cfg['strict']}, baseline={cfg['baseline_file']}, "
            f"suppress_rules={cfg.get('suppress_rules_file')}"
        )
    return _DEFAULT_ENGINE


def _extract_request_fields(text):
    method_match = re.search(r"Request Methoexample/local-input.zip", text)
    url_match = re.search(r"Request URexample/local-input.zip", text)
    return (
        method_match.group(1).strip() if method_match else "GET",
        url_match.group(1).strip() if url_match else "",
    )


def _extract_response_body(text):
    marker = "Response Bodexample/local-input.zip"
    idx = text.find(marker)
    if idx < 0:
        return None
    payload = text[idx + len(marker):].strip()
    return _safe_json_loads(payload)


def _iter_steps(test_result):
    stack = list(test_result.get("steps", []))
    while stack:
        step = stack.pop(0)
        yield step
        stack[0:0] = step.get("steps", [])


def build_baseline_from_allure(allure_results_dir, output_file):
    """从历史 passed 结果构建 endpoint 语义 baseline。"""
    result_files = glob.glob(os.path.join(allure_results_dir, "*-result.json"))
    attachment_cache = {}
    endpoint_samples = {}

    def read_attachment(source):
        if source in attachment_cache:
            return attachment_cache[source]
        path = os.path.join(allure_results_dir, source)
        if not os.path.exists(path):
            attachment_cache[source] = ""
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        attachment_cache[source] = text
        return text

    for rf in result_files:
        try:
            with open(rf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if data.get("status") != "passed":
            continue

        for step in _iter_steps(data):
            request_text = ""
            response_text = ""
            for att in step.get("attachments", []):
                name = att.get("name", "")
                source = att.get("source", "")
                if not source:
                    continue
                content = read_attachment(source)
                if name == "Request Details":
                    request_text = content
                elif name == "Response Details":
                    response_text = content
            if not request_text or not response_text:
                continue

            method, url = _extract_request_fields(request_text)
            body = _extract_response_body(response_text)
            if not isinstance(body, dict):
                continue

            endpoint = normalize_endpoint(method, url)
            sample = endpoint_samples.setdefault(endpoint, [])
            sample.append(body)

    endpoints = {}
    for endpoint, samples in endpoint_samples.items():
        if not samples:
            continue

        # 以出现频率 >= 80% 的 key 作为 baseline 必填字段
        threshold = max(1, int(len(samples) * 0.8))
        top_key_freq = {}
        data_key_freq = {}
        for body in samples:
            for k in body.keys():
                top_key_freq[k] = top_key_freq.get(k, 0) + 1
            if isinstance(body.get("data"), dict):
                for k in body["data"].keys():
                    data_key_freq[k] = data_key_freq.get(k, 0) + 1

        required_top_keys = sorted([k for k, v in top_key_freq.items() if v >= threshold])
        required_data_keys = sorted([k for k, v in data_key_freq.items() if v >= threshold])

        endpoints[endpoint] = {
            "samples": len(samples),
            "required_top_keys": required_top_keys,
            "required_data_keys": required_data_keys,
        }

    baseline = {
        "version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": allure_results_dir,
        "endpoints": endpoints,
    }

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)

    return baseline

