"""
AI 测试报告分析器
使用 OpenAI-compatible LLM API 自动分析 Allure 测试报告
功能：
  1. 识别 passed 但实际可能失败的用例（断言不充分、只验证状态码等）
  2. 找出可优化的用例（重复断言、缺少边界判断、步骤设计问题等）
  3. 生成结构化中文分析报告
"""
import os
import json
import glob
import ast
import re
import requests
from datetime import datetime
from collections import Counter
from common.Log import MyLog
from AI.semantic_record_filters import annotate_semantic_record, decode_unicode_escapes


ERROR_KEYWORDS = ["error", "fail", "failed", "exception", "traceback", "错误", "失败", "异常"]

_PROVIDER_SETTINGS = {
    "github": {
        "label": "GitHub Models",
        "model_key": "github_model",
        "default_model": "gpt-4o",
        "api_url_key": "github_models_api_url",
        "default_api_url": "https://models.inference.ai.azure.com/chat/completions",
        "token_key": "github_token",
        "default_token_env": "GITHUB_TOKEN",
        "token_env_aliases": ["GITHUB_TOKEN"],
        "model_env": "GITHUB_MODEL",
        "api_url_env": "GITHUB_MODELS_API_URL",
    },
    "deepseek": {
        "label": "DeepSeek",
        "model_key": "deepseek_model",
        "default_model": "deepseek-v4-pro",
        "api_url_key": "deepseek_models_api_url",
        "default_api_url": "https://api.deepseek.com/chat/completions",
        "token_key": "deepseek_apikeys",
        "default_token_env": "APIKEYS_DS",
        "token_env_aliases": ["APIKEYS_DS", "DEEPSEEK_API_KEY", "DEEPSEEK_TOKEN"],
        "model_env": "DEEPSEEK_MODEL",
        "api_url_env": "DEEPSEEK_MODELS_API_URL",
    },
}

_ENV_REF_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


# ─── 配置读取 ─────────────────────────────────────────────────────────────────

def _load_env_file(env_file_path: str) -> dict:
    """读取简单 KEY=VALUE 的环境变量文件（忽略注释和空行）。"""
    values = {}
    if not env_file_path or not os.path.exists(env_file_path):
        return values

    try:
        with open(env_file_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip().lstrip("\ufeff")
                val = val.strip().strip('"').strip("'")
                if key:
                    values[key] = val
    except Exception as e:
        MyLog.warning(f"AI分析：读取本地密钥文件失败 {env_file_path}: {e}")

    return values


def _normalize_provider(provider: str) -> str:
    normalized = str(provider or "github").strip().lower()
    if normalized in _PROVIDER_SETTINGS:
        return normalized
    MyLog.warning(f"AI分析：不支持的 llm_provider={normalized}，已回退为 github")
    return "github"


def _looks_like_env_ref(value: str) -> bool:
    return bool(_ENV_REF_RE.fullmatch(str(value or "").strip()))


def _is_placeholder_token(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    return lowered in {"none", "null", "changeme"} or "your_" in lowered or "token_here" in lowered


def _as_int(value, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _resolve_llm_token(secret_ref: str, secret_values: dict, fallback_env_names: list) -> tuple:
    """
    解析 provider token。

    ini 中的 token 配置既兼容旧版“直接写 token”，也支持新版“写环境变量名”。
    优先级：系统环境变量 > secret.env > ini 直写 token。
    """
    secret_ref = str(secret_ref or "").strip()
    env_candidates = []
    if _looks_like_env_ref(secret_ref):
        env_candidates.append(secret_ref)
    env_candidates.extend(fallback_env_names or [])

    seen = set()
    env_candidates = [name for name in env_candidates if name and not (name in seen or seen.add(name))]
    token_env = env_candidates[0] if env_candidates else secret_ref

    for env_name in env_candidates:
        value = os.environ.get(env_name)
        if value:
            return value, env_name

    for env_name in env_candidates:
        value = secret_values.get(env_name)
        if value:
            return value, env_name

    if secret_ref and not _looks_like_env_ref(secret_ref) and not _is_placeholder_token(secret_ref):
        return secret_ref, token_env

    return "", token_env


def _load_ai_config() -> dict:
    """从环境变量 / 本地密钥文件 / config/ai_config.ini 读取 AI 配置。"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(base_dir, "config", "ai_config.ini")
    secret_env_path = os.path.join(base_dir, "config", "secret.env")
    parser = None
    sec = "ai_model"

    if os.path.exists(ini_path):
        try:
            import configparser
            parser = configparser.ConfigParser()
            parser.read(ini_path, encoding="utf-8")
        except Exception as e:
            parser = None
            MyLog.warning(f"AI分析：读取配置失败 {ini_path}: {e}")

    def ini_get(key: str, fallback: str = "") -> str:
        if parser is not None and parser.has_section(sec):
            return parser.get(sec, key, fallback=fallback).strip()
        return fallback

    provider = _normalize_provider(ini_get("llm_provider", "github"))
    provider = _normalize_provider(os.environ.get("LLM_PROVIDER", provider))
    settings = _PROVIDER_SETTINGS[provider]

    secret_file = os.environ.get(
        "AI_SECRET_ENV_FILE",
        ini_get("secret_env_file", secret_env_path)
    )
    if secret_file and not os.path.isabs(secret_file):
        secret_file = os.path.join(base_dir, secret_file)
    secret_values = _load_env_file(secret_file)

    model = ini_get(settings["model_key"], settings["default_model"])
    model = os.environ.get(settings["model_env"], os.environ.get("AI_MODEL", model))

    api_url = ini_get(settings["api_url_key"], settings["default_api_url"])
    api_url = os.environ.get(settings["api_url_env"], os.environ.get("AI_API_URL", api_url))

    timeout = _as_int(ini_get("ai_analyzer_timeout", "120"), 120)
    timeout = _as_int(os.environ.get("AI_ANALYZER_TIMEOUT", timeout), timeout)

    secret_ref = ini_get(settings["token_key"], settings["default_token_env"])
    token, token_env = _resolve_llm_token(
        secret_ref,
        secret_values,
        settings["token_env_aliases"],
    )

    return {
        "provider": provider,
        "provider_label": settings["label"],
        "token": token,
        "token_env": token_env,
        "model": model,
        "api_url": api_url,
        "timeout": timeout,
        "secret_env_file": secret_file,
    }


# ─── Allure 结果解析 ──────────────────────────────────────────────────────────

def _read_attachment(source: str, allure_results_dir: str, max_chars: int = 800) -> str:
    """读取 attachment 文件内容（截断过长内容）"""
    path = os.path.join(allure_results_dir, source)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars + 200)
        if len(content) > max_chars:
            content = content[:max_chars] + "...[截断]"
        return content.strip()
    except Exception:
        return ""


def _parse_steps(steps: list, allure_results_dir: str, depth: int = 0) -> list:
    """递归解析步骤，返回简洁的步骤摘要列表"""
    result = []
    indent = "  " * depth
    for step in steps:
        name   = step.get("name", "")
        status = step.get("status", "unknown")
        entry  = {"step": f"{indent}{name}", "status": status}

        # 收集关键附件（response + semantic，限制大小）
        attachments = step.get("attachments", [])
        response_snippets = []
        semantic_snippets = []
        for att in attachments:
            att_name = att.get("name", "")
            if "Response" in att_name or "response" in att_name:
                content = _read_attachment(att.get("source", ""), allure_results_dir, 600)
                if content:
                    response_snippets.append(f"[{att_name}]: {content}")
            if "Semantic Assertion" in att_name:
                content = _read_attachment(att.get("source", ""), allure_results_dir, 800)
                if content:
                    semantic_snippets.append(f"[{att_name}]: {content}")
        if response_snippets:
            entry["response"] = response_snippets[:2]  # 最多 2 个
        if semantic_snippets:
            entry["semantic"] = semantic_snippets[:1]  # 每步最多 1 个

        # 收集子步骤状态摘要（不深度展开）
        sub_steps = step.get("steps", [])
        if sub_steps:
            entry["sub_steps"] = _parse_steps(sub_steps, allure_results_dir, depth + 1)

        result.append(entry)
    return result


def collect_test_results(allure_results_dir: str) -> list:
    """
    扫描 allure-results 目录，收集所有测试结果
    返回结构化列表，按状态分组（failed/broken 优先）
    """
    pattern = os.path.join(allure_results_dir, "*-result.json")
    result_files = glob.glob(pattern)
    if not result_files:
        MyLog.warning(f"AI分析：未找到测试结果文件，目录：{allure_results_dir}")
        return []

    results = []
    for file_path in result_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            MyLog.warning(f"AI分析：读取结果文件失败 {file_path}: {e}")
            continue

        status    = data.get("status", "unknown")
        test_name = data.get("name", "")
        full_name = data.get("fullName", "")
        labels    = {lb["name"]: lb["value"] for lb in data.get("labels", [])}
        feature   = labels.get("feature", "")
        story     = labels.get("story", "")

        # 解析步骤
        steps = _parse_steps(data.get("steps", []), allure_results_dir)

        # 失败详情
        status_details = data.get("statusDetails", {})
        failure_msg    = status_details.get("message", "")
        failure_trace  = (status_details.get("trace", "") or "")[:500]

        # 日志附件（简要）
        log_snippet = ""
        for att in data.get("attachments", []):
            if att.get("name") == "log":
                log_snippet = _read_attachment(att.get("source", ""), allure_results_dir, 300)
                break

        entry = {
            "test_name":    test_name,
            "full_name":    full_name,
            "feature":      feature,
            "story":        story,
            "status":       status,
            "steps":        steps,
            "failure_msg":  failure_msg,
            "failure_trace": failure_trace,
            "log_snippet":  log_snippet,
        }
        results.append(decode_unicode_escapes(entry))

    # 排序：failed/broken 优先，然后 passed，最后 skipped
    order = {"failed": 0, "broken": 1, "passed": 2, "skipped": 3}
    results.sort(key=lambda x: order.get(x["status"], 9))
    return results


def _build_statistics(results: list) -> dict:
    """统计各状态用例数"""
    stats = {"total": len(results), "passed": 0, "failed": 0, "broken": 0, "skipped": 0, "other": 0}
    for r in results:
        s = r["status"]
        if s in stats:
            stats[s] += 1
        else:
            stats["other"] += 1
    return stats


def _iter_all_steps(steps: list):
    for step in steps:
        yield step
        for sub_step in _iter_all_steps(step.get("sub_steps", [])):
            yield sub_step


def _parse_response_payload(response_text: str):
    """从 response 摘要中尽量提取结构化 body。"""
    if not response_text:
        return None
    text = str(response_text)
    marker = "Response Body:"
    payload = text.split(marker, 1)[1].strip() if marker in text else text
    if payload.startswith("[") and "]:" in payload:
        payload = payload.split("]:", 1)[1].strip()

    try:
        return json.loads(payload)
    except Exception:
        try:
            parsed = ast.literal_eval(payload)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            pass
    return None


def _load_semantic_audits(semantic_report_dir: str) -> list:
    """读取语义审计运行数据（包含无问题记录），返回原始审计记录。"""
    semantic_runtime_dir = os.path.join(semantic_report_dir, "runtime")
    if not os.path.exists(semantic_runtime_dir):
        return []

    records = []
    pattern = os.path.join(semantic_runtime_dir, "semantic_audit_*.jsonl")
    files = glob.glob(pattern)

    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    line = line.strip().lstrip("\ufeff")
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        records.append(rec)
                    except Exception:
                        continue
        except Exception:
            continue

    return records


def _build_semantic_index(records: list) -> dict:
    """按用例聚合语义问题，仅保留真实问题，排除抑制和负向/预期异常场景。"""
    issues_by_test = {}
    for rec in records:
        rec = annotate_semantic_record(rec)
        if not rec.get("findings") or rec.get("suppressed") or rec.get("semantic_expected"):
            continue

        test_key = rec.get("full_name", "") or rec.get("test_name", "")
        if not test_key:
            continue

        if test_key not in issues_by_test:
            issues_by_test[test_key] = []
        issues_by_test[test_key].append(rec)
    return issues_by_test


def _build_semantic_stats(records: list) -> dict:
    """统计语义审计概览（总检查、命中、风险分布）。"""
    records = [annotate_semantic_record(r) for r in records]
    with_findings = [r for r in records if r.get("findings")]
    suppressed_recs = [r for r in with_findings if r.get("suppressed")]
    expected_recs = [
        r for r in with_findings
        if not r.get("suppressed") and r.get("semantic_expected")
    ]
    real_findings = [
        r for r in with_findings
        if not r.get("suppressed") and not r.get("semantic_expected")
    ]
    return {
        "total": len(records),
        "with_findings": len(with_findings),
        "real_findings": len(real_findings),
        "expected": len(expected_recs),
        "suppressed": len(suppressed_recs),
        "high_risk": sum(1 for r in real_findings if r.get("risk") == "HIGH"),
        "medium_risk": sum(1 for r in real_findings if r.get("risk") == "MEDIUM"),
        "low_risk": sum(1 for r in real_findings if r.get("risk") == "LOW"),
    }


def _collect_semantic_insights(issues_by_test: dict) -> str:
    """从语义问题中提取关键洞察，生成简要总结"""
    if not issues_by_test:
        return "未发现语义审计问题。"

    total_issues = sum(len(v) for v in issues_by_test.values())
    high_risk_count = sum(
        1 for issues in issues_by_test.values()
        for issue in issues if issue.get("risk") == "HIGH"
    )
    medium_risk_count = sum(
        1 for issues in issues_by_test.values()
        for issue in issues if issue.get("risk") == "MEDIUM"
    )

    summary_lines = [
        f"【语义审计发现】总计 {total_issues} 条问题",
        f"- HIGH 风险: {high_risk_count} 条",
        f"- MEDIUM 风险: {medium_risk_count} 条",
    ]

    # 收集高频问题规则
    rule_counter = Counter()
    for issues in issues_by_test.values():
        for issue in issues:
            for finding in issue.get("findings", []):
                rule = finding.get("rule", "unknown")
                rule_counter[rule] += 1

    if rule_counter:
        summary_lines.append("- 高频问题规则:")
        for rule, count in rule_counter.most_common(5):
            summary_lines.append(f"  • {rule}: {count} 条")

    return "\n".join(summary_lines)


def _collect_semantic_observability(results: list) -> dict:
    """统计语义断言在测试报告中的可观测性，避免LLM忽略语义附件。"""
    total_steps = 0
    semantic_steps = 0
    semantic_findings = 0
    high_or_medium_hits = 0

    for r in results:
        for step in _iter_all_steps(r.get("steps", [])):
            total_steps += 1
            semantic_list = step.get("semantic", [])
            if not semantic_list:
                continue
            semantic_steps += 1

            text = "\n".join(str(x) for x in semantic_list)
            if "EXPECTED_FAILURE" in text:
                continue
            if "Findings:" in text and "No semantic anomaly detected" not in text:
                semantic_findings += 1
            if "Risk: **HIGH**" in text or "Risk: **MEDIUM**" in text:
                high_or_medium_hits += 1

    coverage_ratio = (semantic_steps / total_steps) if total_steps else 0.0
    return {
        "total_steps": total_steps,
        "semantic_steps": semantic_steps,
        "semantic_coverage_ratio": round(coverage_ratio, 4),
        "semantic_findings_steps": semantic_findings,
        "semantic_medium_high_steps": high_or_medium_hits,
    }


def _step_has_expected_semantic(step: dict) -> bool:
    """当前步骤的语义断言附件显式标记为预期业务失败。"""
    semantic_text = "\n".join(str(item) for item in step.get("semantic", []))
    return "EXPECTED_FAILURE" in semantic_text


def _collect_false_pass_candidates(results: list, issues_by_test: dict = None) -> list:
    """仅基于可验证证据筛选 passed 用例候选，融合语义问题数据，避免经验性提示。"""
    candidates = []
    issues_by_test = issues_by_test or {}

    for r in results:
        if r.get("status") != "passed":
            continue

        score = 0
        evidence = []

        # 传统证据：检查响应数据
        for step in _iter_all_steps(r.get("steps", [])):
            if _step_has_expected_semantic(step):
                continue

            for resp in step.get("response", []):
                payload = _parse_response_payload(resp)
                if isinstance(payload, dict):
                    msg = str(payload.get("msg", "") or payload.get("message", ""))
                    msg_lower = msg.lower()
                    if msg and any(k in msg_lower for k in ERROR_KEYWORDS):
                        score += 3
                        evidence.append(f"step={step.get('step', '')} | msg疑似异常: {msg[:120]}")

                    for key in ("success", "ok"):
                        if key in payload and payload.get(key) is False:
                            score += 4
                            evidence.append(f"step={step.get('step', '')} | {key}=False")

                    code_val = payload.get("code")
                    if isinstance(code_val, int) and code_val not in (0, 200):
                        score += 3
                        evidence.append(f"step={step.get('step', '')} | code={code_val} (非常见成功码)")
                else:
                    # 文本响应仅在出现明确错误关键词时计为弱证据。
                    text = str(resp).lower()
                    if any(k in text for k in ERROR_KEYWORDS):
                        score += 1
                        evidence.append(f"step={step.get('step', '')} | 文本含错误关键词")

        # 融合语义审计发现：如果该用例有语义问题，增加可信度
        test_key = r.get("full_name", "")
        if test_key in issues_by_test:
            semantic_issues = issues_by_test[test_key]
            high_risk_in_test = sum(1 for issue in semantic_issues if issue.get("risk") == "HIGH")
            medium_risk_in_test = sum(1 for issue in semantic_issues if issue.get("risk") == "MEDIUM")

            if high_risk_in_test > 0:
                score += high_risk_in_test * 5
                evidence.append(f"语义审计: {high_risk_in_test} 条 HIGH 风险问题")
            if medium_risk_in_test > 0:
                score += medium_risk_in_test * 2
                evidence.append(f"语义审计: {medium_risk_in_test} 条 MEDIUM 风险问题")

        if score >= 3:
            confidence = "HIGH" if score >= 7 else "MEDIUM"
            candidates.append(
                {
                    "test_name": r.get("test_name", ""),
                    "full_name": r.get("full_name", ""),
                    "confidence": confidence,
                    "score": score,
                    "evidence": evidence[:5],
                }
            )
    return candidates


# ─── AI 分析提示词构建 ────────────────────────────────────────────────────────

def _build_prompt(results: list, stats: dict, issues_by_test: dict = None) -> str:
    """构建发送给 LLM 的分析提示词，融合语义审计数据"""
    issues_by_test = issues_by_test or {}

    # 序列化测试结果（限制总长度，避免超出 token 限制）
    results_text_parts = []
    total_chars = 0
    MAX_TOTAL = 30000  # 约 7500 token，安全范围

    for i, r in enumerate(results, 1):
        part = (
            f"【用例 {i}】名称: {r['test_name']}\n"
            f"  全路径: {r['full_name']}\n"
            f"  Feature: {r['feature']} | Story: {r['story']}\n"
            f"  状态: {r['status']}\n"
        )
        if r["failure_msg"]:
            part += f"  失败信息: {r['failure_msg'][:300]}\n"
        if r["failure_trace"]:
            part += f"  失败堆栈: {r['failure_trace'][:300]}\n"
        if r["log_snippet"]:
            part += f"  日志片段: {r['log_snippet'][:200]}\n"

        # 步骤摘要（只收集步骤名和状态）
        step_lines = []
        for s in r["steps"]:
            line = f"    - [{s['status']}] {s['step']}"
            if _step_has_expected_semantic(s):
                line += "\n      语义标记: EXPECTED_FAILURE（预期业务失败/负向场景，禁止作为假通过证据）"
                step_lines.append(line)
                continue
            # 附加一部分 response（帮助 LLM 判断断言质量）
            for resp in s.get("response", []):
                line += f"\n      响应: {resp[:300]}"
            for sem in s.get("semantic", []):
                line += f"\n      语义断言: {sem[:300]}"
            step_lines.append(line)
        if step_lines:
            part += "  步骤:\n" + "\n".join(step_lines[:15]) + "\n"  # 最多 15 步

        # 融合语义审计问题（如有）
        test_key = r.get("full_name", "")
        if test_key in issues_by_test:
            semantic_issues = issues_by_test[test_key]
            if semantic_issues:
                part += "  【语义审计问题】\n"
                for issue in semantic_issues[:3]:  # 最多3个问题
                    endpoint = issue.get("endpoint", "")
                    risk = issue.get("risk", "")
                    findings = issue.get("findings", [])
                    if findings:
                        msg = findings[0].get("message", "")
                        part += f"    - [{risk}] {endpoint}: {msg[:100]}\n"

        if total_chars + len(part) > MAX_TOTAL:
            results_text_parts.append("...[更多用例因长度限制已省略]")
            break
        results_text_parts.append(part)
        total_chars += len(part)

    results_text = "\n".join(results_text_parts)

    # 融合语义审计洞察
    semantic_insights = _collect_semantic_insights(issues_by_test)
    semantic_observability = _collect_semantic_observability(results)

    candidates = _collect_false_pass_candidates(results, issues_by_test)
    if candidates:
        candidate_lines = []
        for i, c in enumerate(candidates, 1):
            candidate_lines.append(
                f"[{i}] {c['test_name']} | confidence={c['confidence']} | score={c['score']}\n"
                f"    full_name={c['full_name']}\n"
                + "\n".join([f"    evidence: {e}" for e in c.get("evidence", [])])
            )
        candidate_text = "\n".join(candidate_lines)
    else:
        candidate_text = "未发现可验证证据候选。第二章必须写“未发现可验证的假通过用例”，禁止从测试结果详情另行挑选。"

    prompt = f"""你是一位资深自动化测试专家，请分析以下 pytest + allure 接口自动化测试报告，给出专业、有价值的中文分析意见。

## 测试统计
- 总用例数: {stats['total']}
- 通过(passed): {stats['passed']}
- 失败(failed): {stats['failed']}
- 异常(broken): {stats['broken']}
- 跳过(skipped): {stats['skipped']}

## 语义审计概览
{semantic_insights}

## 测试结果详情
{results_text}

## 基于证据的疑似假通过候选（程序预筛+语义融合）
{candidate_text}

## 语义断言引擎上下文（已接入）
- 本项目已接入语义感知断言引擎，接口请求会自动附带 `Semantic Assertion` 附件。
- 你不能建议“引入语义断言引擎”，只能评估“语义断言覆盖质量、证据质量、规则有效性”。
- `EXPECTED_FAILURE` / `semantic_expected=true` 表示调用端已声明为预期业务失败或负向场景，即使响应里有 `success=False`、`code=422`，也必须从假通过风险中排除。
- “疑似假通过”只能来自下方候选列表；候选为空时，不得基于测试详情重新挖掘或推断假通过。
- 若语义证据不足，请明确写“语义证据可观测性不足”，并指出缺失证据类型。
- 语义可观测性统计：{json.dumps(semantic_observability, ensure_ascii=False)}

---
请按以下结构输出分析报告：

### 一、整体质量评估
简述本次测试的整体质量，评分（1-10分）及理由。考虑：功能覆盖、断言充分性、语义问题发现等。

### 二、⚠️ 疑似"假通过"用例（passed 但可能实际失败）
仅允许从"基于证据的疑似假通过候选（程序预筛+语义融合）"中选择，用例必须有可验证证据。逐条说明：
- 用例名称
- 证据（引用候选中的原始证据行或语义问题发现）
- 疑似原因
- 改进建议

如果候选为空或证据不足，请写"未发现可验证的假通过用例"，不要给经验性提示。

### 三、🔴 失败/异常用例根因分析
对 failed/broken 用例逐条分析根本原因（环境问题？断言错误？接口变更？数据依赖？语义问题?），并给出修复建议。

补充约束：
- 禁止输出“建议引入语义断言引擎/语义规则”这类已完成事项。
- 允许输出“优化现有语义规则配置、可观测性、阈值、抑制规则治理”的建议。

注意：仅输出以上三个章节，不要额外扩展其他章节。"""
    return prompt


# ─── LLM API 调用 ──────────────────────────────────────────────────────────────

def call_llm_api(prompt: str, cfg: dict) -> str:
    """调用 OpenAI-compatible Chat Completions API，返回分析文本。"""
    provider_label = cfg.get("provider_label") or cfg.get("provider") or "LLM"
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一位专业的自动化测试专家，擅长分析 pytest/allure 接口测试报告，"
                    "能够发现假通过用例、提供优化建议，输出语言为中文。"
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens":  3000,
    }

    try:
        MyLog.info(f"AI分析：正在调用 {provider_label} ({cfg['model']}) API...")
        resp = requests.post(
            cfg["api_url"],
            headers=headers,
            json=payload,
            timeout=cfg["timeout"]
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        MyLog.info(f"AI分析：{provider_label} API 调用成功")
        return content
    except requests.exceptions.Timeout:
        msg = f"AI分析：{provider_label} API 请求超时（{cfg['timeout']}s），请检查网络连接"
        MyLog.error(msg)
        return f"❌ {msg}"
    except requests.exceptions.HTTPError as e:
        msg = f"AI分析：{provider_label} API HTTP 错误 {e.response.status_code}: {e.response.text[:500]}"
        MyLog.error(msg)
        return f"❌ {msg}"
    except Exception as e:
        msg = f"AI分析：{provider_label} API 调用异常: {e}"
        MyLog.error(msg)
        return f"❌ {msg}"


def call_github_models_api(prompt: str, cfg: dict) -> str:
    """兼容旧调用名。实际按 cfg.provider 调用对应 LLM。"""
    return call_llm_api(prompt, cfg)


def _enforce_false_pass_candidate_policy(analysis_text: str, has_candidates: bool) -> str:
    """候选为空时，禁止 LLM 在第二章自行扩展假通过用例。"""
    analysis_text = decode_unicode_escapes(analysis_text or "")
    if has_candidates:
        return analysis_text

    replacement = (
        "### 二、⚠️ 疑似\"假通过\"用例（passed 但可能实际失败）\n"
        "未发现可验证的假通过用例。\n\n"
        "> 说明：本轮程序预筛候选为空；语义审计中标记为 `EXPECTED_FAILURE` / "
        "`semantic_expected=true` 的负向场景已从假通过风险中排除。"
    )
    pattern = re.compile(r"### 二、.*?(?=\n### 三、)", re.S)
    if pattern.search(analysis_text):
        return pattern.sub(replacement + "\n", analysis_text, count=1)
    return analysis_text.rstrip() + "\n\n" + replacement


# ─── 报告保存 ─────────────────────────────────────────────────────────────────

def _cleanup_old_reports(directory: str, pattern: str, keep: int = 3) -> None:
    """
    清理旧报告，仅保留最新 `keep` 份匹配 `pattern` 的文件。
    按文件名（含时间戳）降序排列，超出部分删除。
    """
    matched = sorted(glob.glob(os.path.join(directory, pattern)), reverse=True)
    to_delete = matched[keep:]
    for path in to_delete:
        try:
            os.remove(path)
            MyLog.info(f"已清理旧报告: {path}")
        except Exception as e:
            MyLog.warning(f"清理旧报告失败 {path}: {e}")


def save_analysis_report(
    analysis_text: str,
    stats: dict,
    output_dir: str,
    keep: int = 3,
    model_name: str = "",
    semantic_stats: dict = None,
    provider_label: str = "",
) -> str:
    """将 AI 分析结果保存为 Markdown 文件，并清理超出 keep 份的旧报告"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"ai_analysis_{timestamp}.md"
    file_path = os.path.join(output_dir, file_name)

    model_for_display = model_name or "unknown"
    provider_for_display = provider_label or "LLM"
    semantic_stats = semantic_stats or {}
    analysis_text = decode_unicode_escapes(analysis_text)

    header = (
        f"# 🤖 AI 测试报告分析\n\n"
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
        f"> 分析模型：{provider_for_display} ({model_for_display})  \n"
        f"> 测试统计：总计 {stats['total']} 条 | "
        f"通过 {stats['passed']} | 失败 {stats['failed']} | "
        f"异常 {stats['broken']} | 跳过 {stats['skipped']}"
    )
    
    # 如果有语义统计，也添加到头部
    if semantic_stats:
        header += (
            f"  \n> 语义审计：总检查 {semantic_stats.get('total', 0)} | "
            f"真实问题 {semantic_stats.get('real_findings', 0)} | "
            f"预期异常 {semantic_stats.get('expected', 0)} | "
            f"HIGH {semantic_stats.get('high_risk', 0)} | "
            f"MEDIUM {semantic_stats.get('medium_risk', 0)} | "
            f"LOW {semantic_stats.get('low_risk', 0)}"
        )
    
    header += f"\n\n---\n\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(header + analysis_text)

    MyLog.info(f"AI分析报告已保存: {file_path}")
    # 只清理带时间戳的历史文件（以年份开头，避免误删 *_latest.md 等固定文件）
    _cleanup_old_reports(output_dir, "ai_analysis_2*.md", keep=keep)
    return file_path


# ─── 主入口 ───────────────────────────────────────────────────────────────────

def analyze_test_report(allure_results_dir: str, report_output_dir: str = None, semantic_report_dir: str = None) -> str:
    """
    主函数：分析 allure-results 目录并生成 AI 分析报告

    :param allure_results_dir:  allure-results 目录路径
    :param report_output_dir:   AI 报告输出目录（默认与 allure-results 同级的 ai-analysis 目录）
    :param semantic_report_dir: 语义审计报告目录（默认与 allure-results 同级的 semantic 目录）
    :return:                    分析报告文件路径
    """
    MyLog.info("=" * 60)
    MyLog.info("🤖 开始 AI 自动分析测试报告...")
    MyLog.info("=" * 60)

    # 确定输出目录
    if report_output_dir is None:
        report_output_dir = os.path.join(os.path.dirname(allure_results_dir), "ai-analysis")

    # 确定语义报告目录
    if semantic_report_dir is None:
        semantic_report_dir = os.path.join(os.path.dirname(allure_results_dir), "semantic")

    # 加载配置
    cfg = _load_ai_config()
    if not cfg["token"]:
        msg = (
            f"AI分析：未配置 {cfg.get('provider_label', cfg.get('provider', 'LLM'))} "
            f"Token（{cfg.get('token_env', 'UNKNOWN')}），跳过 AI 分析"
        )
        MyLog.warning(msg)
        print(f"\n⚠️  {msg}")
        return ""

    # 收集测试结果
    results = collect_test_results(allure_results_dir)
    if not results:
        msg = "AI分析：没有可分析的测试结果"
        MyLog.warning(msg)
        print(f"\n⚠️  {msg}")
        return ""

    stats = _build_statistics(results)
    MyLog.info(
        f"AI分析：收集到 {stats['total']} 条用例 "
        f"(passed={stats['passed']}, failed={stats['failed']}, "
        f"broken={stats['broken']}, skipped={stats['skipped']})"
    )

    # 加载语义审计数据（全量记录 + 真实问题索引）
    semantic_records = _load_semantic_audits(semantic_report_dir)
    semantic_stats = _build_semantic_stats(semantic_records)
    issues_by_test = _build_semantic_index(semantic_records)
    MyLog.info(
        "AI分析：语义审计统计 "
        f"(total={semantic_stats['total']}, with_findings={semantic_stats['with_findings']}, "
        f"real_findings={semantic_stats['real_findings']}, expected={semantic_stats.get('expected', 0)}, "
        f"suppressed={semantic_stats['suppressed']})"
    )

    # 构建提示词并调用 API（融合语义问题）
    false_pass_candidates = _collect_false_pass_candidates(results, issues_by_test)
    prompt   = _build_prompt(results, stats, issues_by_test)
    analysis = call_llm_api(prompt, cfg)
    analysis = _enforce_false_pass_candidate_policy(
        analysis,
        has_candidates=bool(false_pass_candidates),
    )


    # 保存报告（包含语义统计）
    report_path = save_analysis_report(
        analysis,
        stats,
        report_output_dir,
        model_name=cfg.get("model", ""),
        provider_label=cfg.get("provider_label", ""),
        semantic_stats=semantic_stats
    )
    print(f"\n\033[32m📄 AI测试报告分析: {report_path}\033[0m\n")
    MyLog.info("🤖 AI 测试报告分析完成")

    return report_path



