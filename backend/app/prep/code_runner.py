"""Sandboxed code execution adapter for the preparation workspace.

The API process never executes candidate code locally. A Judge0-compatible
service must be configured explicitly through JUDGE0_URL, and every submission
is sent with bounded resource limits and networking disabled.
"""

import base64
import json
import os
import shutil
import subprocess
import time
from typing import Any

import httpx


LANGUAGE_IDS = {
    "python": 71,
    "javascript": 63,
    "typescript": 74,
    "java": 62,
    "cpp": 54,
}

MAX_SOURCE_LENGTH = 20_000
MAX_STDIN_LENGTH = 5_000
POLL_INTERVAL_SECONDS = 0.25
POLL_TIMEOUT_SECONDS = 15.0


class SandboxUnavailableError(RuntimeError):
    """Raised when no isolated execution service has been configured."""


class SandboxExecutionError(RuntimeError):
    """Raised when the sandbox cannot accept or return a submission."""


def _config() -> tuple[str, str | None]:
    url = os.getenv("JUDGE0_URL", "").strip().rstrip("/")
    token = os.getenv("JUDGE0_TOKEN", "").strip() or None
    if not url:
        raise SandboxUnavailableError(
            "Code execution is not configured. Set JUDGE0_URL to a private Judge0-compatible sandbox."
        )
    return url, token


def _request_with_powershell(url: str, token: str | None, *, method: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if not executable:
        raise SandboxExecutionError("No HTTP transport is available for the code sandbox.")

    encode = lambda value: base64.b64encode(value.encode("utf-8")).decode("ascii")
    url_data = encode(url)
    body_data = encode(json.dumps(body)) if body is not None else ""
    script = f"""
$ErrorActionPreference = 'Stop'
$uri = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{url_data}'))
$headers = @{{ Accept = 'application/json' }}
if ($env:EVALIA_JUDGE0_TOKEN) {{ $headers['X-Auth-Token'] = $env:EVALIA_JUDGE0_TOKEN }}
if ('{body_data}') {{
  $body = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{body_data}'))
  $response = Invoke-RestMethod -Uri $uri -Method '{method}' -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec {int(POLL_TIMEOUT_SECONDS)}
}} else {{
  $response = Invoke-RestMethod -Uri $uri -Method '{method}' -Headers $headers -TimeoutSec {int(POLL_TIMEOUT_SECONDS)}
}}
$response | ConvertTo-Json -Depth 20 -Compress
"""
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    environment = os.environ.copy()
    environment["EVALIA_JUDGE0_TOKEN"] = token or ""

    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_script],
            capture_output=True,
            text=True,
            check=True,
            env=environment,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise SandboxExecutionError("The code sandbox could not be reached.") from exc

    if not isinstance(payload, dict):
        raise SandboxExecutionError("The code sandbox returned an invalid response.")
    return payload


def _request(url: str, token: str | None, *, method: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    # On Windows, PowerShell uses the system TLS/proxy path. This keeps the
    # local public CE setup usable where Python TLS is intercepted.
    if os.name == "nt" and (shutil.which("powershell.exe") or shutil.which("powershell")):
        return _request_with_powershell(url, token, method=method, body=body)

    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Auth-Token"] = token

    try:
        with httpx.Client(timeout=POLL_TIMEOUT_SECONDS, follow_redirects=True, trust_env=True) as client:
            response = client.request(method, url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SandboxExecutionError("The code sandbox could not be reached.") from exc

    if not isinstance(payload, dict):
        raise SandboxExecutionError("The code sandbox returned an invalid response.")
    return payload


def _decode(value: Any) -> str:
    if not value:
        return ""
    try:
        return base64.b64decode(value).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return str(value)


def execute_code(*, language: str, source_code: str, stdin: str = "", expected_output: str | None = None) -> dict[str, Any]:
    """Submit bounded source code and wait for its Judge0 result."""
    if language not in LANGUAGE_IDS:
        raise SandboxExecutionError("That language is not enabled for the prep workspace.")
    if len(source_code) > MAX_SOURCE_LENGTH or len(stdin) > MAX_STDIN_LENGTH:
        raise SandboxExecutionError("The code or input exceeds the workspace limit.")

    base_url, token = _config()
    encode = lambda value: base64.b64encode(value.encode("utf-8")).decode("ascii")
    payload: dict[str, Any] = {
        "language_id": LANGUAGE_IDS[language],
        "source_code": encode(source_code),
        "stdin": encode(stdin),
        "cpu_time_limit": 2,
        "wall_time_limit": 5,
        "memory_limit": 128000,
        "stack_limit": 64000,
        "max_processes_and_or_threads": 20,
        "max_file_size": 1024,
        "enable_network": False,
    }
    if expected_output is not None:
        payload["expected_output"] = encode(expected_output)

    created = _request(
        f"{base_url}/submissions/?base64_encoded=true&wait=false",
        token,
        method="POST",
        body=payload,
    )
    submission_token = created.get("token")
    if not isinstance(submission_token, str) or not submission_token:
        raise SandboxExecutionError("The code sandbox did not return a submission token.")

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = _request(
            f"{base_url}/submissions/{submission_token}?base64_encoded=true",
            token,
            method="GET",
        )
        status_id = (result.get("status") or {}).get("id")
        if status_id not in (1, 2):
            return {
                "language": language,
                "status": (result.get("status") or {}).get("description", "Unknown"),
                "stdout": _decode(result.get("stdout")),
                "stderr": _decode(result.get("stderr")),
                "compile_output": _decode(result.get("compile_output")),
                "time": result.get("time"),
                "memory": result.get("memory"),
            }
        time.sleep(POLL_INTERVAL_SECONDS)

    raise SandboxExecutionError("The code sandbox took too long to return a result.")


def execute_problem(
    *,
    language: str,
    source_code: str,
    harness: str,
    test_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run a database-defined problem harness against selected test cases."""
    if not harness:
        raise SandboxExecutionError("This problem has no execution harness for the selected language.")
    if not test_cases:
        raise SandboxExecutionError("This problem has no configured test cases.")

    results: list[dict[str, Any]] = []
    for test_case in test_cases:
        encoded_input = json.dumps(json.dumps(test_case["input"], separators=(",", ":")))
        test_source = f"{source_code.rstrip()}\n\n{harness.replace('{{INPUT}}', encoded_input)}"
        result = execute_code(
            language=language,
            source_code=test_source,
            expected_output=f"{test_case['expected_output']}\n",
        )
        passed = result.get("status") == "Accepted"
        results.append(
            {
                "id": test_case["id"],
                "title": test_case["title"],
                "passed": passed,
                "status": result.get("status", "Unknown"),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "compile_output": result.get("compile_output", ""),
                "time": result.get("time"),
                "memory": result.get("memory"),
                "is_hidden": bool(test_case.get("is_hidden")),
                **({} if test_case.get("is_hidden") else {"input": test_case["input"], "expected_output": test_case["expected_output"]}),
            }
        )
        if not passed:
            # A failing case is enough to report the submission; hidden cases
            # remain opaque while still contributing to the overall result.
            continue

    passed_tests = sum(1 for result in results if result["passed"])
    return {
        "language": language,
        "status": "Accepted" if passed_tests == len(results) else "Wrong Answer",
        "passed": passed_tests == len(results),
        "passed_tests": passed_tests,
        "total_tests": len(results),
        "tests": results,
        "stdout": results[-1].get("stdout", "") if results else "",
        "stderr": results[-1].get("stderr", "") if results else "",
        "compile_output": results[-1].get("compile_output", "") if results else "",
        "time": results[-1].get("time") if results else None,
        "memory": results[-1].get("memory") if results else None,
    }
