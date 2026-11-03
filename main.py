"""
Root auto-detect fallback for Vercel (main:app).
Prefer api.index:app via pyproject.toml [tool.vercel] entrypoint.
"""
from __future__ import annotations

try:
    from api.index import app  # type: ignore
except Exception:
    # Inline minimal ASGI app if package import fails during local path edge cases
    from fastapi import FastAPI

    app = FastAPI(title="LLM MCP Hub", version="1.1.0")

    @app.get("/")
    @app.get("/health")
    def root():
        return {"status": "LLM MCP Hub operational", "mode": "main-fallback"}
