"""Oda/oturum çalışma-zamanı mantığı — fastapi'den bağımsız (test edilebilir).

Bir `ws` nesnesinin yalnızca `async send_json(dict)` metoduna ihtiyaç duyar;
bu sayede hem gerçek WebSocket hem de testteki sahte soketle çalışır.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Dict, Optional

from .bot import take_turn as bot_take_turn
from .game import Game, GameError, Phase

BOT_DELAY = 0.8  # bot hamleleri arası gecikme (saniye)


class Room:
    def __init__(self, room_id: str):
        self.game = Game(room_id)
        self.sockets: Dict[str, object] = {}   # pid -> ws
        self.host: Optional[str] = None
        self.lock = asyncio.Lock()

    async def broadcast(self) -> None:
        dead = []
        for pid, ws in list(self.sockets.items()):
            try:
                await ws.send_json({"type": "state", "state": self.game.private_state(pid)})
            except Exception:
                dead.append(pid)
        for pid in dead:
            self.sockets.pop(pid, None)


rooms: Dict[str, Room] = {}


def get_room(room_id: str) -> Room:
    if room_id not in rooms:
        rooms[room_id] = Room(room_id)
    return rooms[room_id]


async def run_bots(room: Room, delay: float = BOT_DELAY) -> None:
    game = room.game
    guard = 0
    while game.phase in (Phase.DRAW, Phase.ACTION) and game.current.is_bot and guard < 300:
        guard += 1
        if delay:
            await asyncio.sleep(delay)
        try:
            bot_take_turn(game, game.current.pid)
        except GameError:
            pass
        await room.broadcast()


async def maybe_run_bots(room: Room, background: bool = True) -> None:
    g = room.game
    if g.phase in (Phase.DRAW, Phase.ACTION) and g.players and g.current.is_bot:
        if background:
            asyncio.create_task(run_bots(room))
        else:
            await run_bots(room, delay=0)  # testte senkron


async def handle_hello(room: Room, ws, msg: dict) -> Optional[str]:
    name = (msg.get("name") or "Oyuncu").strip()[:20]
    pid = msg.get("pid")
    game = room.game
    existing = next((p for p in game.players if p.pid == pid), None) if pid else None

    if existing:
        existing.connected = True
        if name:
            existing.name = name
    else:
        pid = uuid.uuid4().hex[:12]
        try:
            game.add_player(pid, name)
        except GameError as e:
            await ws.send_json({"type": "error", "message": str(e)})
            return None
        if room.host is None:
            room.host = pid

    room.sockets[pid] = ws
    await ws.send_json({"type": "joined", "pid": pid, "is_host": room.host == pid})
    await room.broadcast()
    return pid


async def handle_action(room: Room, ws, pid: str, msg: dict, *, bots_background: bool = True) -> None:
    game = room.game
    mtype = msg.get("type")
    async with room.lock:
        try:
            if mtype == "add_bots":
                if room.host != pid:
                    raise GameError("Sadece oda sahibi bot ekleyebilir")
                n = 0
                while len(game.players) < 4:
                    game.add_player(f"bot-{uuid.uuid4().hex[:6]}", f"Bot {len(game.players)}", is_bot=True)
                    n += 1
                game._log(f"{n} bot eklendi")

            elif mtype == "start":
                if room.host != pid:
                    raise GameError("Sadece oda sahibi başlatabilir")
                game.start_hand()

            elif mtype == "new_hand":
                if room.host != pid:
                    raise GameError("Sadece oda sahibi yeni el başlatabilir")
                if game.phase != Phase.FINISHED:
                    raise GameError("El bitmeden yeni el başlatılamaz")
                game.start_hand()

            elif mtype == "draw":
                if msg.get("source") == "discard":
                    game.draw_from_discard(pid)
                else:
                    game.draw_from_pile(pid)

            elif mtype == "open":
                game.open_melds(pid, msg.get("groups", []))

            elif mtype == "process":
                game.process(pid, msg["meld_id"], msg.get("tids", []))

            elif mtype == "discard":
                game.discard(pid, msg["tid"])

            else:
                raise GameError(f"Bilinmeyen mesaj: {mtype}")

        except GameError as e:
            await ws.send_json({"type": "error", "message": str(e)})
            return
        except Exception as e:  # beklenmeyen -> nazik hata
            await ws.send_json({"type": "error", "message": f"Geçersiz istek: {e}"})
            return

    await room.broadcast()
    await maybe_run_bots(room, background=bots_background)
