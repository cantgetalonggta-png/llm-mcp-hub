"""
Vercel Python ASGI entrypoint for LLM MCP Hub.
Local MCP remains: python3 llm_mcp_hub.py (stdio).
This module exposes an HTTP health + tool surface for serverless deploy.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = FastAPI(
    title="LLM MCP Hub",
    description="HTTP surface for multi-provider LLM tools (OpenAI · Anthropic · xAI · Gemini). Local MCP stdio: llm_mcp_hub.py",
    version="1.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


class PromptBody(BaseModel):
    user_prompt: str = Field(..., min_length=1)
    model: Optional[str] = None
    system_prompt: str = "Be precise and concise."
    max_tokens: int = 2048
    providers: str = "openai,anthropic,xai"


@app.get("/")
def root():
    return {
        "status": "LLM MCP Hub operational",
        "mode": "vercel-http",
        "local_mcp": "python3 llm_mcp_hub.py",
        "routes": ["/", "/health", "/tools/provider_healthcheck", "/tools/query_openai", "/tools/query_anthropic", "/tools/query_xai", "/tools/query_gemini", "/tools/multi_provider_consult"],
    }


@app.get("/health")
def health():
    return root()


@app.get("/tools/provider_healthcheck")
def provider_healthcheck():
    keys = {
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
        "xai": os.getenv("XAI_API_KEY", "") or os.getenv("GROK_API_KEY", ""),
        "google": os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", ""),
    }
    results = {}
    for name, key in keys.items():
        entry = {"key": _mask(key)}
        if not key.strip():
            entry["status"] = "SKIP"
            results[name] = entry
            continue
        try:
            if name == "openai":
                _http_json("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key.strip()}"})
            elif name == "anthropic":
                _http_json(
                    "https://api.anthropic.com/v1/models",
                    {"x-api-key": key.strip(), "anthropic-version": "2023-06-01"},
                )
            elif name == "xai":
                _http_json("https://api.x.ai/v1/models", {"Authorization": f"Bearer {key.strip()}"})
            elif name == "google":
                _http_json(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key.strip()}",
                    {},
                )
            entry["status"] = "OK"
        except Exception as e:
            entry["status"] = f"FAIL {type(e).__name__}: {e}"
        results[name] = entry
    return {"service": "llm-mcp-hub", "providers": results}


@app.post("/tools/query_openai")
def query_openai(body: PromptBody):
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise HTTPException(400, "OPENAI_API_KEY missing")
    model = body.model or "gpt-4o-mini"
    try:
        out = _http_json(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": body.system_prompt},
                    {"role": "user", "content": body.user_prompt},
                ],
                "temperature": 0.2,
            },
            method="POST",
        )
        return {"provider": "openai", "model": model, "content": out["choices"][0]["message"]["content"]}
    except Exception as e:
        raise HTTPException(502, f"OpenAI error: {type(e).__name__}: {e}")


@app.post("/tools/query_anthropic")
def query_anthropic(body: PromptBody):
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise HTTPException(400, "ANTHROPIC_API_KEY missing")
    model = body.model or "claude-sonnet-4-20250514"
    try:
        out = _http_json(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {
                "model": model,
                "max_tokens": body.max_tokens,
                "system": body.system_prompt,
                "messages": [{"role": "user", "content": body.user_prompt}],
            },
            method="POST",
        )
        parts = out.get("content") or []
        texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
        return {"provider": "anthropic", "model": model, "content": "\n".join(texts) if texts else json.dumps(out)[:4000]}
    except Exception as e:
        raise HTTPException(502, f"Anthropic error: {type(e).__name__}: {e}")


@app.post("/tools/query_xai")
def query_xai(body: PromptBody):
    key = (os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY") or "").strip()
    if not key:
        raise HTTPException(400, "XAI_API_KEY / GROK_API_KEY missing")
    model = body.model or "grok-3-mini"
    try:
        out = _http_json(
            "https://api.x.ai/v1/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": body.system_prompt},
                    {"role": "user", "content": body.user_prompt},
                ],
                "temperature": 0.2,
            },
            method="POST",
        )
        return {"provider": "xai", "model": model, "content": out["choices"][0]["message"]["content"]}
    except Exception as e:
        raise HTTPException(502, f"xAI error: {type(e).__name__}: {e}")


@app.post("/tools/query_gemini")
def query_gemini(body: PromptBody):
    key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise HTTPException(400, "GOOGLE_API_KEY / GEMINI_API_KEY missing")
    model = body.model or "gemini-2.0-flash"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        out = _http_json(url, {}, {"contents": [{"parts": [{"text": body.user_prompt}]}]}, method="POST")
        cands = out.get("candidates") or []
        if not cands:
            return {"provider": "gemini", "model": model, "content": json.dumps(out)[:4000]}
        parts = cands[0].get("content", {}).get("parts") or []
        return {"provider": "gemini", "model": model, "content": "\n".join(p.get("text", "") for p in parts)}
    except Exception as e:
        raise HTTPException(502, f"Gemini error: {type(e).__name__}: {e}")


@app.post("/tools/multi_provider_consult")
def multi_provider_consult(body: PromptBody):
    wanted = [p.strip().lower() for p in body.providers.split(",") if p.strip()]
    blocks = {}
    for p in wanted:
        try:
            if p == "openai":
                blocks["openai"] = query_openai(body).get("content")
            elif p == "anthropic":
                blocks["anthropic"] = query_anthropic(body).get("content")
            elif p == "xai":
                blocks["xai"] = query_xai(body).get("content")
            elif p in ("gemini", "google"):
                blocks["gemini"] = query_gemini(body).get("content")
            else:
                blocks[p] = "Unknown provider"
        except HTTPException as he:
            blocks[p] = he.detail
        except Exception as e:
            blocks[p] = f"{type(e).__name__}: {e}"
    return {"providers": body.providers, "results": blocks}
