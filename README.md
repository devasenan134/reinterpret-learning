# Reinterpret

Self-hosted AI notebook. See `docs/PLAN.md`.

```
cp .env.example .env
cd backend && uv sync && uv run uvicorn app.main:app --reload      # :8000
cd frontend && npm install && npm run dev                          # :5173, proxies /api
cd backend && uv run pytest
```
