# DrillPrint Monitor UI (M6)

React + Vite + R3F instrument for `/ws/monitor`.

## Dev

```bash
# terminal 1 — API
uvicorn api.main:app --reload --port 8000

# terminal 2 — UI (proxies API)
cd frontend && npm run dev
```

Open http://127.0.0.1:5173 — use **Replay whirl** / **Replay stick-slip**.

## Production build

```bash
cd frontend && npm run build   # → ../frontend_dist
uvicorn api.main:app --port 8000
```

Same-origin dual-serve: UI + API on one port.
