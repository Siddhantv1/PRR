from collections.abc import Awaitable, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend import db
from backend.db.models import RunStatus


router = APIRouter()
active_connections: dict[str, list[WebSocket]] = {}


@router.websocket("/ws/runs/{run_id}")
async def run_websocket(websocket: WebSocket, run_id: str):
    await websocket.accept()
    active_connections.setdefault(run_id, []).append(websocket)

    run = await db.get_run(run_id)
    if run and run.status == RunStatus.COMPLETED and run.result:
        await websocket.send_json({"type": "run_complete", **run.result})
    elif run and run.status == RunStatus.FAILED:
        await websocket.send_json({"type": "run_error", "error": run.error})

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _remove_connection(run_id, websocket)


def get_broadcast_fn(run_id: str) -> Callable[[dict], Awaitable[None]]:
    async def broadcast(event: dict):
        dead = []
        for websocket in active_connections.get(run_id, []):
            try:
                await websocket.send_json(event)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            _remove_connection(run_id, websocket)

    return broadcast


def _remove_connection(run_id: str, websocket: WebSocket) -> None:
    try:
        active_connections[run_id].remove(websocket)
        if not active_connections[run_id]:
            del active_connections[run_id]
    except (KeyError, ValueError):
        pass
