#!/usr/bin/env python3
"""
LLM MCP Hub — multi-provider local MCP server for Grok
Providers: OpenAI, Anthropic, xAI (Grok API), Google Gemini (optional via REST)
Traffic: this machine → provider only. No proxy.
"""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from mcp.server import MCPServer

_DIR = Path(__file__).resolve().parent
load_dotenv(_DIR / ".env")
load_dotenv()

mcp = MCPServer("llm-mcp-hub")
TIMEOUT = float(os.getenv("LLM_TIMEOUT_S", "120"))


def _mask(k: str) -> str:
    k = (k or "").strip()
    if not k:
        return "(missing)"
    return k[:4] + "…" + k[-4:] if len(k) > 12 else "(set)"


def _http_json(url: str, headers: dict, payload: Optional[dict] = None, method: str = "GET") -> dict:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body) if body else {}


@mcp.tool()
def provider_healthcheck() -> str:
    """Report which LLM API keys are present (masked) and which providers respond to a lightweight probe."""
    keys = {
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
        "xai": os.getenv("XAI_API_KEY", "") or os.getenv("GROK_API_KEY", ""),
        "google": os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", ""),
    }
    lines = ["LLM MCP Hub health:"]
    for name, key in keys.items():
        lines.append(f"- {name}: key={_mask(key)}")
        if not key.strip():
            lines.append(f"  status: SKIP (no key)")
            continue
        try:
            if name == "openai":
                _http_json(
                    "https://api.openai.com/v1/models",
                    {"Authorization": f"Bearer {key.strip()}"},
                )
            elif name == "anthropic":
                _http_json(
                    "https://api.anthropic.com/v1/models",
                    {
                        "x-api-key": key.strip(),
                        "anthropic-version": "2023-06-01",
                    },
                )
            elif name == "xai":
                _http_json(
                    "https://api.x.ai/v1/models",
                    {"Authorization": f"Bearer {key.strip()}"},
                )
            elif name == "google":
                _http_json(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key.strip()}",
                    {},
                )
            lines.append("  status: OK")
        except Exception as e:
            lines.append(f"  status: FAIL {type(e).__name__}: {e}")
    return "\n".join(lines)


@mcp.tool()
def query_openai(user_prompt: str, model: str = "gpt-4o-mini", system_prompt: str = "Be precise and concise.") -> str:
    """Call OpenAI Chat Completions. Requires OPENAI_API_KEY."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return "Error: OPENAI_API_KEY missing"
    try:
        out = _http_json(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            method="POST",
        )
        return out["choices"][0]["message"]["content"]
    except Exception as e:
        return f"OpenAI error: {type(e).__name__}: {e}"


@mcp.tool()
def query_anthropic(user_prompt: str, model: str = "claude-sonnet-4-20250514", system_prompt: str = "Be precise and concise.", max_tokens: int = 2048) -> str:
    """Call Anthropic Messages API. Requires ANTHROPIC_API_KEY."""
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return "Error: ANTHROPIC_API_KEY missing"
    try:
        out = _http_json(
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            method="POST",
        )
        parts = out.get("content") or []
        texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
        return "\n".join(texts) if texts else json.dumps(out)[:4000]
    except Exception as e:
        return f"Anthropic error: {type(e).__name__}: {e}"


@mcp.tool()
def query_xai(user_prompt: str, model: str = "grok-3-mini", system_prompt: str = "Be precise and concise.") -> str:
    """Call xAI Grok API (OpenAI-compatible). Requires XAI_API_KEY or GROK_API_KEY."""
    key = (os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY") or "").strip()
    if not key:
        return "Error: XAI_API_KEY / GROK_API_KEY missing"
    try:
        out = _http_json(
            "https://api.x.ai/v1/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            method="POST",
        )
        return out["choices"][0]["message"]["content"]
    except Exception as e:
        return f"xAI error: {type(e).__name__}: {e}"


@mcp.tool()
def query_gemini(user_prompt: str, model: str = "gemini-2.0-flash") -> str:
    """Call Google Gemini generateContent. Requires GOOGLE_API_KEY or GEMINI_API_KEY."""
    key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        return "Error: GOOGLE_API_KEY / GEMINI_API_KEY missing"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        out = _http_json(
            url,
            {},
            {"contents": [{"parts": [{"text": user_prompt}]}]},
            method="POST",
        )
        cands = out.get("candidates") or []
        if not cands:
            return json.dumps(out)[:4000]
        parts = cands[0].get("content", {}).get("parts") or []
        return "\n".join(p.get("text", "") for p in parts)
    except Exception as e:
        return f"Gemini error: {type(e).__name__}: {e}"


@mcp.tool()
def multi_provider_consult(user_prompt: str, providers: str = "openai,anthropic,xai") -> str:
    """
    Fan-out the same prompt to multiple providers (comma-separated: openai,anthropic,xai,gemini).
    Returns labeled answers for cross-check / red-team style comparison.
    """
    wanted = [p.strip().lower() for p in providers.split(",") if p.strip()]
    blocks = []
    for p in wanted:
        if p == "openai":
            blocks.append("### OpenAI\n" + query_openai(user_prompt))
        elif p == "anthropic":
            blocks.append("### Anthropic\n" + query_anthropic(user_prompt))
        elif p == "xai":
            blocks.append("### xAI\n" + query_xai(user_prompt))
        elif p in ("gemini", "google"):
            blocks.append("### Gemini\n" + query_gemini(user_prompt))
        else:
            blocks.append(f"### {p}\nUnknown provider")
    return "\n\n".join(blocks)


if __name__ == "__main__":
    mcp.run()
