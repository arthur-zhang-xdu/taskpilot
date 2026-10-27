#!/usr/bin/env python3
"""使用环境变量验证智谱文本 API；仅使用 Python 标准库，不自动重试。"""

import argparse
import http.client
import json
import os
import socket
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    """避免重定向时把 Authorization 转发到其他地址。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=30,
                        help="请求超时秒数，范围 (0, 300]，默认 30")
    args = parser.parse_args()
    if not 0 < args.timeout <= 300:
        parser.error("--timeout 必须大于 0 且不超过 300 秒")
    key = os.environ.get("LLM_API_KEY", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "").strip().rstrip("/")
    model = os.environ.get("LLM_MODEL", "").strip()
    missing = [
        name for name, value in (
            ("LLM_API_KEY", key),
            ("LLM_BASE_URL", base_url),
            ("LLM_MODEL", model),
        ) if not value
    ]
    if missing:
        print("配置缺失：" + ", ".join(missing), file=sys.stderr)
        print("请在运行本脚本的同一终端 export 这些变量。", file=sys.stderr)
        return 1

    try:
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise ValueError
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "请只回复：TaskPilot API 测试成功"}],
            "thinking": {"type": "disabled"},
            "max_tokens": 64,
            "stream": False,
        }, ensure_ascii=False).encode("utf-8")
        request = Request(
            base_url + "/chat/completions",
            data=payload,
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
    except (ValueError, UnicodeError):
        print("配置无效：请检查 HTTPS 基础地址、模型和凭据格式。", file=sys.stderr)
        return 1

    started = time.monotonic()
    try:
        with build_opener(NoRedirect()).open(request, timeout=args.timeout) as response:
            result = json.load(response)
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            print("调用未通过：接口没有返回非空文本。", file=sys.stderr)
            return 1
        usage = result.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        # 仅输出白名单字段；不打印原始响应、请求头或异常详情。
        summary = {
            "success": True,
            "model": model,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "reply": content.strip()[:200],
            "usage": {
                field: usage.get(field, "未知")
                for field in ("prompt_tokens", "completion_tokens", "total_tokens")
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2).replace(key, "[REDACTED]"))
        return 0
    except HTTPError as exc:
        hints = {
            401: "请检查 API Key 是否有效。",
            403: "请检查账号和模型访问权限。",
            404: "请检查基础地址和模型标识。",
            429: "请求受限，请检查平台额度或频率限制。",
        }
        print(f"调用失败：HTTP {exc.code}。" + hints.get(exc.code, "请在平台核查请求状态。"), file=sys.stderr)
    except (TimeoutError, socket.timeout):
        elapsed = time.monotonic() - started
        print(f"调用失败：请求超时（设置 {args.timeout:g} 秒，已耗时 {elapsed:.1f} 秒），未自动重试。", file=sys.stderr)
        print("可先检查网络连通性，再使用 --timeout 120 手动重试一次。", file=sys.stderr)
    except URLError:
        print("调用失败：网络连接、DNS 或 TLS 异常，未自动重试。", file=sys.stderr)
    except (ValueError, KeyError, IndexError, TypeError):
        print("调用失败：响应不是预期的 JSON 对话格式。", file=sys.stderr)
    except (OSError, UnicodeError, http.client.HTTPException):
        print("调用失败：连接中断或请求编码异常。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
