"""Benchmark report REST (gate 5 / A19)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(tags=["bench"])

REPORT_PATH = Path(__file__).resolve().parent.parent / "bench" / "report.json"


@router.get("/bench/report")
def bench_report(request: Request):
    dp = request.app.state.dp
    if dp.bench_report is not None:
        return dp.bench_report
    if REPORT_PATH.exists():
        import json
        return json.loads(REPORT_PATH.read_text())
    return {
        "status": "missing",
        "hint": "python -m bench.run --full",
    }
