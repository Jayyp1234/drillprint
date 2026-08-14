"""Library REST surface: list / activate / episodes (A12 / §17 / §31)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from store.fingerprint_db import StateError

router = APIRouter(tags=["library"])


@router.get("/libraries")
def list_libraries(request: Request):
    dp = request.app.state.dp
    if dp.db is None:
        return []
    rows = dp.db.conn.execute(
        "SELECT version, created, notes, status, approved_by, approved_at FROM libraries"
    ).fetchall()
    return [
        {
            "version": r[0], "created": r[1], "notes": r[2],
            "status": r[3], "approved_by": r[4], "approved_at": r[5],
            "active": r[0] == dp.db.active_version(),
            **dp.db.stats(r[0]),
        }
        for r in rows
    ]


@router.post("/libraries/{version}/activate")
def activate(version: str, request: Request):
    dp = request.app.state.dp
    if dp.db is None:
        raise HTTPException(404, "no database")
    try:
        dp.db.activate(version)
    except (StateError, KeyError) as e:
        raise HTTPException(409, str(e)) from e
    dp.reset_engine()
    return {"active": version}


@router.post("/libraries/{version}/validate")
def validate(version: str, request: Request):
    dp = request.app.state.dp
    try:
        dp.db.set_status(version, "validated")
    except (StateError, KeyError) as e:
        raise HTTPException(409, str(e)) from e
    return {"version": version, "status": "validated"}


@router.post("/libraries/{version}/approve")
def approve(version: str, request: Request, approved_by: str = "operator"):
    dp = request.app.state.dp
    try:
        dp.db.set_status(version, "approved", approved_by=approved_by)
    except (StateError, KeyError) as e:
        raise HTTPException(409, str(e)) from e
    return {"version": version, "status": "approved", "approved_by": approved_by}


@router.get("/episodes")
def episodes(request: Request, class_name: str | None = None):
    dp = request.app.state.dp
    if dp.db is None:
        return []
    version = dp.db.active_version()
    if version is None:
        return []
    if class_name:
        rows = dp.db.conn.execute(
            "SELECT id, slug, class, duration_s, params_json FROM episodes "
            "WHERE library_version=? AND class=?",
            (version, class_name),
        ).fetchall()
    else:
        rows = dp.db.conn.execute(
            "SELECT id, slug, class, duration_s, params_json FROM episodes "
            "WHERE library_version=?",
            (version,),
        ).fetchall()
    return [
        {"id": r[0], "slug": r[1], "class": r[2], "duration_s": r[3], "params_json": r[4]}
        for r in rows
    ]
