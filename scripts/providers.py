"""Minimal stdlib HTTP clients for live verification (Gemini, OpenAI, Anthropic).

Keys are read from the environment and never logged. Error text is scrubbed of request ids.
Used only by maintainer scripts (probe.py, record_verdicts.py); never shipped in packages.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

_SCRUB = [
    (re.compile(r"req_[A-Za-z0-9]+"), "req_<redacted>"),
    (re.compile(r"org-[A-Za-z0-9]+"), "org-<redacted>"),
    (re.compile(r"[A-Za-z0-9_\-]{32,}"), "<redacted>"),
]


def scrub(text: str) -> str:
    for pat, repl in _SCRUB:
        text = pat.sub(repl, text)
    return text[:500]


@dataclass
class CallResult:
    status: str  # "accepted" | "rejected" | "error"
    http_status: int
    error: str | None
    args: Any  # function-call arguments if the model called the tool


def _post(url: str, body: dict[str, Any], headers: dict[str, str], retries: int = 3) -> tuple[int, Any]:
    data = json.dumps(body).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            try:
                payload = json.load(e)
            except Exception:
                payload = {"error": {"message": e.reason}}
            return e.code, payload
    raise RuntimeError("unreachable")


def _err_message(payload: Any) -> str:
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return str(err.get("message", ""))
        if isinstance(err, str):
            return err
    return json.dumps(payload)[:300]


def available(provider: str) -> bool:
    return bool(os.environ.get(ENV_KEYS[provider]))


ENV_KEYS = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def call_tool(
    provider: str,
    *,
    model: str,
    schema: dict[str, Any],
    prompt: str,
    strict: bool,
    temperature: float = 0.0,
    tool_name: str = "t",
) -> CallResult:
    key = os.environ[ENV_KEYS[provider]]
    if provider == "gemini":
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"functionDeclarations": [{"name": tool_name, "description": "test tool", "parametersJsonSchema": schema}]}],
            "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
            "generationConfig": {"maxOutputTokens": 512, "temperature": temperature},
        }
        code, payload = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            body,
            {"x-goog-api-key": key},
        )
        if code != 200:
            return CallResult("rejected" if code == 400 else "error", code, scrub(_err_message(payload)), None)
        args = None
        for part in payload.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            if "functionCall" in part:
                args = part["functionCall"].get("args", {})
        return CallResult("accepted", code, None, args)
    if provider == "openai":
        # UNVERIFIED in-repo until an OPENAI_API_KEY is configured (see docs/live-verification.md).
        body = {
            "model": model,
            "input": prompt,
            "tools": [{"type": "function", "name": tool_name, "description": "test tool", "parameters": schema, "strict": strict}],
            "tool_choice": "required",
            "max_output_tokens": 512,
        }
        code, payload = _post("https://api.openai.com/v1/responses", body, {"authorization": f"Bearer {key}"})
        if code != 200:
            return CallResult("rejected" if code == 400 else "error", code, scrub(_err_message(payload)), None)
        args = None
        for item in payload.get("output", []):
            if item.get("type") == "function_call":
                args = json.loads(item.get("arguments") or "{}")
        return CallResult("accepted", code, None, args)
    if provider == "anthropic":
        # UNVERIFIED in-repo until an ANTHROPIC_API_KEY is configured (see docs/live-verification.md).
        tool: dict[str, Any] = {"name": tool_name, "description": "test tool", "input_schema": schema}
        if strict:
            tool["strict"] = True
        body = {
            "model": model,
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [tool],
        }
        code, payload = _post(
            "https://api.anthropic.com/v1/messages",
            body,
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
        )
        if code != 200:
            return CallResult("rejected" if code == 400 else "error", code, scrub(_err_message(payload)), None)
        args = None
        for block in payload.get("content", []):
            if block.get("type") == "tool_use":
                args = block.get("input")
        return CallResult("accepted", code, None, args)
    raise ValueError(f"unknown provider {provider}")
