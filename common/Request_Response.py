import os
import json
import allure
import requests
import time
from functools import wraps
from requests.exceptions import HTTPError
from requests.exceptions import ConnectionError, Timeout
from AI.semantic_assertion_engine import get_default_engine, append_semantic_audit, get_current_allure_context


def log_allure_request_response(func):
    """
    Allure请求响应记录装饰器
    功能：自动记录接口的请求参数和响应结果
    适用：支持requests的get/post/put/delete等所有方法
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        semantic_engine = get_default_engine()
        method_from_args = kwargs.get('method')
        url_from_args = kwargs.get('url')
        # ApiClient.request* 通常以位置参数传 method/url: self, method, url
        if len(args) >= 3:
            method_from_args = method_from_args or args[1]
            url_from_args = url_from_args or args[2]

        # 捕获请求参数
        request_args = {
            'method': str(method_from_args or 'GET').upper(),
            'url': str(url_from_args or ''),
            'headers': kwargs.get('headers', {}),
            'json': kwargs.get('json'),
            'data': kwargs.get('data'),
            'params': kwargs.get('params'),
            'files': kwargs.get('files')
        }

        # 记录请求信息
        request_info = (
            f"Request Method: {request_args['method']}\n"
            f"Request URL: {request_args['url']}\n"
            f"Request Headers: {request_args['headers']}\n"
            f"Request Body: {request_args['json'] or request_args['data']}\n"
            f"Query Params: {request_args['params']}\n"
            f"Upload Files: {list(request_args['files'].keys()) if request_args['files'] else None}"
        )
        allure.attach(request_info, "Request Details", allure.attachment_type.TEXT)

        # 执行请求
        response = func(*args, **kwargs)

        # 记录响应信息
        try:
            response_body = response.json()
            attach_type = allure.attachment_type.JSON
        except ValueError:
            response_body = response.text
            attach_type = allure.attachment_type.TEXT

        response_info = (
            f"Status Code: {response.status_code}\n"
            f"Response Headers: {dict(response.headers)}\n"
            f"Response Bodexample/local-input.zip"
        )
        allure.attach(response_info, "Response Details", attach_type)

        # 语义层断言：识别"看起来通过"但业务语义异常的接口返回
        try:
            semantic_result = semantic_engine.evaluate(
                method=request_args['method'],
                url=request_args['url'],
                status_code=response.status_code,
                response_body=response_body,
            )
            semantic_report = semantic_engine.format_markdown_report(semantic_result)
            allure.attach(semantic_report, "Semantic Assertion", allure.attachment_type.TEXT)

            audit_context = get_current_allure_context()

            # 截取响应和请求的关键部分用于报告显示
            request_summary = ""
            if request_args.get('json'):
                req_json = request_args.get('json')
                if isinstance(req_json, dict):
                    request_summary = json.dumps(req_json, ensure_ascii=False)[:200]
                else:
                    request_summary = str(req_json)[:200]

            response_summary = ""
            if isinstance(response_body, dict):
                # 只提取关键字段：code, msg/message, success, error, exception 等
                key_fields = {}
                for k in ["code", "msg", "message", "success", "error", "exception", "status", "errorCode"]:
                    if k in response_body:
                        key_fields[k] = response_body[k]
                response_summary = json.dumps(key_fields, ensure_ascii=False)[:300] if key_fields else str(response_body)[:300]
            else:
                response_summary = str(response_body)[:300]

            append_semantic_audit({
                "endpoint": semantic_result.endpoint,
                "risk": semantic_result.risk,
                "score": semantic_result.score,
                "status_code": response.status_code,
                "method": request_args['method'],
                "url": request_args['url'],
                "test_file": audit_context.get("test_file", ""),
                "test_name": audit_context.get("test_name", ""),
                "test_class": audit_context.get("test_class", ""),
                "step_name": audit_context.get("step_name", ""),
                "request_summary": request_summary,
                "response_summary": response_summary,
                "semantic_expected": semantic_result.expected,
                "expected_reason": semantic_result.expected_reason,
                "suppressed": semantic_result.suppressed,
                "suppress_reason": semantic_result.suppress_reason,
                "findings": [
                    {"level": f.level, "rule": f.rule, "message": f.message}
                    for f in semantic_result.findings
                ],
            })

            if semantic_result.findings:
                print(
                    f"\n[SemanticCheck] {semantic_result.endpoint} | "
                    f"risk={semantic_result.risk} score={semantic_result.score}"
                )

            if semantic_engine.strict and semantic_result.should_fail:
                raise AssertionError(
                    f"语义断言失败: endpoint={semantic_result.endpoint}, "
                    f"risk={semantic_result.risk}, score={semantic_result.score}"
                )
        except AssertionError:
            raise
        except Exception as semantic_err:
            # 语义检查异常默认不阻塞业务请求，可通过 strict 让高风险直接失败
            allure.attach(
                f"Semantic engine exception: {semantic_err}",
                "Semantic Assertion Error",
                allure.attachment_type.TEXT,
            )

        return response

    return wrapper


class ApiClient:
    """封装的请求客户端"""

    def __init__(self, base_headers=None, default_timeout=60, retry_status_codes=None):
        self.session = requests.Session()
        self.base_headers = base_headers or {}
        self.default_timeout = default_timeout

        # 添加重试配置
        self.max_retry_seconds = 60  # 最大重试时间60秒
        self.retry_interval = 5  # 重试间隔5秒
        self.retry_status_codes = list(retry_status_codes) if retry_status_codes is not None else [422, 503]

    @log_allure_request_response
    def request_with_retry(self, method, url, **kwargs):
        """
        带重试机制的请求方法
        """
        start_time = time.time()
        attempt = 0
        request_headers = kwargs.pop('headers', {})
        raise_for_status = kwargs.pop("raise_for_status", True)
        kwargs.setdefault("timeout", self.default_timeout)

        while True:
            attempt += 1
            try:
                headers = {**self.base_headers, **request_headers}
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    **kwargs
                )

                # 检查是否需要重试的特定状态码
                if raise_for_status and response.status_code in self.retry_status_codes:
                    raise HTTPError(f"需要重试的状态码: {response.status_code}", response=response)

                if raise_for_status:
                    response.raise_for_status()  # 触发HTTP异常
                return response


            except (HTTPError, ConnectionError, Timeout) as e:
                # 判断是否可重试
                is_retryable = False
                error_type = "请求错误"
                # 1. 网络错误总是可重试
                if isinstance(e, (ConnectionError, Timeout)):
                    is_retryable = True
                    error_type = "网络错误"

                # 2. HTTP错误根据状态码判断
                elif isinstance(e, HTTPError) and hasattr(e, 'response'):
                    status_code = e.response.status_code
                    # 可重试状态码
                    if status_code in self.retry_status_codes:
                        is_retryable = True
                        error_type = f"{status_code}错误"

                    # 400错误特殊处理
                    elif status_code == 400:
                        # 直接抛出，不重试
                        raise ValueError("客户端请求错误，请检查参数") from e

                    # 其他HTTP错误
                    else:
                        error_type = f"HTTP错误({status_code})"
                # 不可重试的错误直接抛出
                if not is_retryable:
                    raise
                # 以下为可重试错误的处理逻辑
                elapsed = time.time() - start_time
                if elapsed > self.max_retry_seconds:
                    raise Exception(f"重试超过{self.max_retry_seconds}秒仍然失败") from e

                print(f"\r{error_type}: 正在重试 (尝试 {attempt}次, 已等待 {int(elapsed)}秒)", end="")

                time.sleep(self.retry_interval)

            except Exception as e:
                # 其他异常直接抛出
                raise

    @log_allure_request_response
    def request(self, method, url, **kwargs):
        """统一请求方法"""
        headers = {**self.base_headers, **kwargs.pop('headers', {})}
        raise_for_status = kwargs.pop("raise_for_status", False)
        kwargs.setdefault("timeout", self.default_timeout)
        response = self.session.request(
            method=method,
            url=url,
            headers=headers,
            **kwargs
        )
        if raise_for_status:
            response.raise_for_status()
        return response

    def request_no_raise(self, method, url, **kwargs):
        """带重试但不因HTTP状态码抛异常，便于负向用例断言响应体。"""
        kwargs["raise_for_status"] = False
        return self.request_with_retry(method, url, **kwargs)

    # 常用方法快捷方式（添加带重试版本）
    def post_with_retry(self, url, **kwargs):
        return self.request_with_retry('POST', url, **kwargs)

    def get_with_retry(self, url, **kwargs):
        return self.request_with_retry('GET', url, **kwargs)

    def post_no_raise(self, url, **kwargs):
        return self.request_no_raise('POST', url, **kwargs)

    def get_no_raise(self, url, **kwargs):
        return self.request_no_raise('GET', url, **kwargs)

    # 常用方法快捷方式
    def post(self, url, **kwargs):
        return self.request('POST', url, **kwargs)

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def put(self, url, **kwargs):
        return self.request('PUT', url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request('DELETE', url, **kwargs)
