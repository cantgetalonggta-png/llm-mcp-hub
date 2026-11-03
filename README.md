# LLM MCP Hub (OpenAI · Anthropic · xAI · Gemini)

Local multi-provider **MCP server** for Grok, plus a **Vercel HTTP** surface.

## Local MCP (stdio)

```bash
pip install -r requirements.txt
cp .env.example .env   # fill keys
python3 llm_mcp_hub.py
```

Tools: `provider_healthcheck`, `query_openai`, `query_anthropic`, `query_xai`, `query_gemini`, `multi_provider_consult`

## Vercel (HTTP)

Entrypoint: `api/index.py` → FastAPI `app`  
Declared in `pyproject.toml` as `[tool.vercel] entrypoint = "api.index:app"`.

```bash
# after link/login
vercel --prod
```

Set project env vars: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY` or `GROK_API_KEY`, `GOOGLE_API_KEY` or `GEMINI_API_KEY`.

HTTP routes: `/`, `/health`, `/tools/*`.

## Fix note (PYTHON_ENTRYPOINT_NOT_FOUND)

Vercel detected Python but the primary script is named `llm_mcp_hub.py` (stdio MCP), not a web entrypoint. This repo now ships:

- `api/index.py` — ASGI FastAPI app
- `pyproject.toml` — `[tool.vercel] entrypoint = "api.index:app"`
- `vercel.json` — builds/routes to `api/index.py`
- `main.py` — root fallback importing `app`
