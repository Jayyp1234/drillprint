"""WebSocket ingest + monitor (A14 / A15 / §17)."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from ingest.channels import observability_badges

router = APIRouter(tags=["stream"])


@router.get("/channels")
def channels():
    from ingest.channels import REGISTRY
    return [observability_badges(n) for n in REGISTRY]


@router.websocket("/ws/ingest")
async def ws_ingest(ws: WebSocket):
    await ws.accept()
    dp = ws.app.state.dp
    if dp.engine is None:
        if dp.db is None:
            await ws.send_json({"ack": False, "reason": "no_database"})
            await ws.close()
            return
        dp.reset_engine(mode="live")
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            ack = dp.engine.ingest_frame(
                msg["name"], float(msg["t0"]), msg["values"], msg.get("fs")
            )
            await ws.send_json(ack)
    except WebSocketDisconnect:
        return


@router.websocket("/ws/monitor")
async def ws_monitor(ws: WebSocket):
    await ws.accept()
    dp = ws.app.state.dp
    q: asyncio.Queue = asyncio.Queue(maxsize=4096)
    dp.subscribers.append(q)
    try:
        while True:
            msg = await q.get()
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        if q in dp.subscribers:
            dp.subscribers.remove(q)


@router.post("/replay")
async def replay_episode(
    request: Request, class_name: str = "WHIRL_BACKWARD", seed: int = 1042
):
    """Synchronous replay helper for tests / SIMULATE stage — streams to /ws/monitor."""
    import asyncio

    from replay.stream_player import feed_episode
    from synth import bit_bounce, normal, stick_slip, whirl

    dp = request.app.state.dp
    if dp.db is None:
        return {"ok": False, "reason": "no_database"}

    def _run():
        engine = dp.reset_engine(mode="replay")
        if class_name == "WHIRL_BACKWARD":
            ep = whirl.generate(n_blades=5, severity=2, profile="const", seed=seed)
        elif class_name == "BIT_BOUNCE":
            ep = bit_bounce.generate(severity=2, profile="const", seed=seed)
        elif class_name == "STICK_SLIP":
            ep = stick_slip.generate(
                length_m=3000, rpm_set=120, ts_ratio=1.6, j_b=200
            )
        else:
            ep = normal.generate(variant="quiet", seed=seed)
        feed_episode(engine, ep)
        return {
            "ok": True,
            "duration_s": ep.duration_s,
            "detections": engine.detections(),
            "n_messages": len(engine.messages),
            "n_twin": len(engine.twin_log()),
        }

    return await asyncio.to_thread(_run)
