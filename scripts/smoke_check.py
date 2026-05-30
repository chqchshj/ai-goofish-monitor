#!/usr/bin/env python3
"""Read-only HTTP smoke check for xianyu-tools.

The script intentionally performs GET requests only. It does not create tasks,
write settings, or mutate application data.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class CheckResult:
    path: str
    status: int
    ok: bool
    detail: str


def fetch(base_url: str, path: str, timeout_seconds: float) -> tuple[int, bytes, str]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(url, method="GET", headers={"User-Agent": "xianyu-tools-smoke/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - local smoke URL is operator-provided
            return response.status, response.read(512_000), response.headers.get("content-type", "")
    except HTTPError as exc:
        return exc.code, exc.read(512_000), exc.headers.get("content-type", "")


def check_health(base_url: str, request_timeout: float) -> CheckResult:
    status, body, content_type = fetch(base_url, "/health", request_timeout)
    if status != 200:
        return CheckResult("/health", status, False, "expected HTTP 200")
    if "json" in content_type.lower():
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            return CheckResult("/health", status, False, f"invalid JSON: {exc}")
        text = json.dumps(payload, ensure_ascii=False).lower()
        if any(token in text for token in ("ok", "healthy", "success")):
            return CheckResult("/health", status, True, "healthy JSON payload")
        return CheckResult("/health", status, True, "HTTP 200 JSON payload")
    return CheckResult("/health", status, True, "HTTP 200")


def check_index(base_url: str, request_timeout: float) -> CheckResult:
    status, body, _ = fetch(base_url, "/", request_timeout)
    if status != 200:
        return CheckResult("/", status, False, "expected HTTP 200")
    text = body[:20_000].decode("utf-8", errors="ignore").lower()
    if "html" in text and ("/assets/" in text or "vite" in text or "xianyu" in text):
        return CheckResult("/", status, True, "web UI shell detected")
    return CheckResult("/", status, False, "response does not look like the Web UI shell")


def check_docs(base_url: str, request_timeout: float) -> CheckResult:
    status, _body, _ = fetch(base_url, "/docs", request_timeout)
    if status in {200, 401, 403}:
        return CheckResult("/docs", status, True, "reachable or intentionally protected")
    return CheckResult("/docs", status, False, "expected HTTP 200/401/403")


def run_once(base_url: str, request_timeout: float) -> list[CheckResult]:
    return [
        check_health(base_url, request_timeout),
        check_index(base_url, request_timeout),
        check_docs(base_url, request_timeout),
    ]


def format_results(results: Iterable[CheckResult]) -> str:
    lines = []
    for result in results:
        mark = "OK" if result.ok else "FAIL"
        lines.append(f"[{mark}] {result.path} status={result.status} {result.detail}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only xianyu-tools HTTP smoke check")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL to check")
    parser.add_argument("--timeout", type=float, default=30.0, help="Total seconds to wait for readiness")
    parser.add_argument("--request-timeout", type=float, default=5.0, help="Seconds per HTTP request")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between retries")
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    last_error = ""
    last_results: list[CheckResult] = []

    while True:
        try:
            last_results = run_once(args.base_url, args.request_timeout)
            if all(result.ok for result in last_results):
                print(format_results(last_results))
                return 0
        except (URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)

        if time.monotonic() >= deadline:
            break
        time.sleep(args.interval)

    if last_results:
        print(format_results(last_results), file=sys.stderr)
    if last_error:
        print(f"Last connection error: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
