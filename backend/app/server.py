"""FastAPI + WebSocket katmanı (ince). Mantık app/rooms.py içinde.

Çalıştır:  uvicorn app.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .rooms import get_room, handle_action, handle_hello

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="Okey 101")


@app.get("/health")
async def health():
    from .rooms import rooms
    return {"ok": True, "rooms": len(rooms)}


@app.websocket("/ws/{room_id}")
async def ws_endpoint(ws: WebSocket, room_id: str):
    await ws.accept()
    room = get_room(room_id)
    pid = None
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "hello":
                pid = await handle_hello(room, ws, msg)
                continue
            if pid is None:
                await ws.send_json({"type": "error", "message": "Önce 'hello' gönder"})
                continue
            await handle_action(room, ws, pid, msg)
    except WebSocketDisconnect:
        if pid and pid in room.sockets:
            room.sockets.pop(pid, None)
            p = next((x for x in room.game.players if x.pid == pid), None)
            if p:
                p.connected = False
            await room.broadcast()


# statik arayüz (en sona monte edilir ki /ws ve /health gölgelenmesin)
if FRONTEND_DIR.exists():
    @app.get("/")
    async def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
