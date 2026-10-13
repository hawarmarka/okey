"""Okey 101 oyun durum makinesi.

Otoriter: tüm taşlar burada tutulur. Oyuncular yalnızca niyet gönderir
(çek / at / aç / işle / bitir); doğrulamayı bu modül yapar.

Akış:
  WAITING -> (start) -> PLAYING -> FINISHED
Sıra (turn) içinde iki faz:
  DRAW  : destenin üstünden ya da sağdaki oyuncunun attığından taş çek
  ACTION: (opsiyonel aç / işle) + zorunlu at. Atınca sıra sola geçer.
Bitiş: oyuncu açmışsa ve çektikten sonra son taşını atarak elini boşaltırsa kazanır.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from . import scoring
from .melds import MeldError, OPEN_THRESHOLD, validate_meld
from .tiles import (
    Color,
    Tile,
    is_wild,
    okey_number_for,
    shuffled_deck,
)

NUM_PLAYERS = 4
START_TILES = 14  # başlayan 15 alır (bir fazla), sonra atar


class Phase(str, Enum):
    WAITING = "waiting"
    DRAW = "draw"
    ACTION = "action"
    FINISHED = "finished"


class GameError(Exception):
    """Oyuncunun geçersiz hamlesi (kullanıcıya gösterilir)."""


@dataclass
class TableMeld:
    """Masaya açılmış bir grup (herkese açık)."""
    meld_id: int
    owner: str
    tiles: List[Tile]


@dataclass
class Player:
    pid: str
    name: str
    is_bot: bool = False
    connected: bool = True
    hand: List[Tile] = field(default_factory=list)
    opened: bool = False
    score: int = 0  # toplam (eller arası birikir)


class Game:
    def __init__(self, room_id: str, seed: Optional[int] = None):
        self.room_id = room_id
        self.rng = random.Random(seed)
        self.players: List[Player] = []
        self.phase: Phase = Phase.WAITING
        self.draw_pile: List[Tile] = []
        self.discards: Dict[str, List[Tile]] = {}  # oyuncu -> attıkları (üstteki = son)
        self.table: List[TableMeld] = []
        self._meld_seq = 0
        self.indicator: Optional[Tile] = None
        self.okey_color: Optional[Color] = None
        self.okey_number: Optional[int] = None
        self.turn_index: int = 0
        self.winner: Optional[str] = None
        self.last_delta: Dict[str, int] = {}
        self.hand_number: int = 0
        self.must_discard_only: bool = False  # başlayan ilk turda sadece atar
        self.log: List[str] = []

    def _log(self, msg: str) -> None:
        self.log.append(msg)
        if len(self.log) > 60:
            self.log = self.log[-60:]

    # --- lobi -------------------------------------------------------------
    def add_player(self, pid: str, name: str, is_bot: bool = False) -> Player:
        if self.phase != Phase.WAITING:
            raise GameError("Oyun başladı, katılınamaz")
        if len(self.players) >= NUM_PLAYERS:
            raise GameError("Oda dolu")
        if any(p.pid == pid for p in self.players):
            raise GameError("Zaten odadasın")
        p = Player(pid=pid, name=name, is_bot=is_bot)
        self.players.append(p)
        return p

    def player(self, pid: str) -> Player:
        for p in self.players:
            if p.pid == pid:
                return p
        raise GameError("Oyuncu bulunamadı")

    @property
    def current(self) -> Player:
        return self.players[self.turn_index]

    def _next_meld_id(self) -> int:
        self._meld_seq += 1
        return self._meld_seq

    def _validate(self, tiles: List[Tile]) -> int:
        """validate_meld sarmalayıcısı: MeldError -> GameError (kullanıcıya dönük)."""
        try:
            return validate_meld(tiles, self.okey_color, self.okey_number)
        except MeldError as e:
            raise GameError(str(e))

    # --- el başlat --------------------------------------------------------
    def start_hand(self) -> None:
        if len(self.players) != NUM_PLAYERS:
            raise GameError("4 oyuncu gerekli")
        self.hand_number += 1
        self.phase = Phase.ACTION
        self.table = []
        self._meld_seq = 0
        self.winner = None
        self.last_delta = {}
        deck = shuffled_deck(self.rng)

        # gösterge: sahte okey OLMAYAN bir taş olmalı
        idx = next(i for i, t in enumerate(deck) if not t.is_fake_joker)
        self.indicator = deck.pop(idx)
        self.okey_color = self.indicator.color
        self.okey_number = okey_number_for(self.indicator)

        for p in self.players:
            p.hand = []
            p.opened = False
            self.discards[p.pid] = []

        # dağıtım: başlayan 15, diğerleri 14
        starter = self.rng.randrange(NUM_PLAYERS)
        self.turn_index = starter
        for i, p in enumerate(self.players):
            count = START_TILES + 1 if i == starter else START_TILES
            for _ in range(count):
                p.hand.append(deck.pop())
            self._sort_hand(p)

        self.draw_pile = deck
        # başlayan fazladan taşla başlar -> önce atmalı
        self.phase = Phase.ACTION
        self.must_discard_only = True
        self._log(
            f"El {self.hand_number} başladı. Gösterge: {self._tile_name(self.indicator)} · "
            f"Okey: {self.okey_color.value} {self.okey_number}. "
            f"Başlayan: {self.current.name}"
        )

    @staticmethod
    def _tile_name(t: Tile) -> str:
        if t is None:
            return "?"
        if t.is_fake_joker:
            return "sahte okey"
        return f"{t.color.value} {t.number}"

    def _sort_hand(self, p: Player) -> None:
        def key(t: Tile):
            if t.is_fake_joker:
                return (9, 0, t.tid)
            order = {Color.SARI: 0, Color.MAVI: 1, Color.SIYAH: 2, Color.KIRMIZI: 3}
            return (order[t.color], t.number, t.tid)
        p.hand.sort(key=key)

    # --- yardımcılar ------------------------------------------------------
    def _take_from_hand(self, p: Player, tids: List[int]) -> List[Tile]:
        taken: List[Tile] = []
        hand_by_id = {t.tid: t for t in p.hand}
        for tid in tids:
            if tid not in hand_by_id:
                raise GameError(f"Taş elinde değil: {tid}")
            taken.append(hand_by_id[tid])
        for t in taken:
            p.hand.remove(t)
        return taken

    def _require_turn(self, pid: str, phase: Phase) -> Player:
        if self.phase == Phase.FINISHED:
            raise GameError("El bitti")
        if self.current.pid != pid:
            raise GameError("Sıra sende değil")
        if self.phase != phase:
            raise GameError(f"Şu an yapılamaz (faz: {self.phase.value})")
        return self.current

    def _prev_index(self) -> int:
        return (self.turn_index - 1) % NUM_PLAYERS

    # --- hamleler ---------------------------------------------------------
    def draw_from_pile(self, pid: str) -> Tile:
        p = self._require_turn(pid, Phase.DRAW)
        if not self.draw_pile:
            # deste bitti -> berabere/el biter
            self._end_hand_no_winner()
            raise GameError("Deste bitti, el sonuçlandı")
        tile = self.draw_pile.pop()
        p.hand.append(tile)
        self._sort_hand(p)
        self.phase = Phase.ACTION
        return tile

    def draw_from_discard(self, pid: str) -> Tile:
        p = self._require_turn(pid, Phase.DRAW)
        prev = self.players[self._prev_index()]
        pile = self.discards.get(prev.pid, [])
        if not pile:
            raise GameError("Alınacak atılmış taş yok")
        tile = pile.pop()
        p.hand.append(tile)
        self._sort_hand(p)
        self.phase = Phase.ACTION
        return tile

    def open_melds(self, pid: str, groups: List[List[int]]) -> None:
        """İlk açılış: her grup geçerli olmalı ve toplam >= OPEN_THRESHOLD."""
        p = self._require_turn(pid, Phase.ACTION)
        if p.opened:
            raise GameError("Zaten açıldın; işleme (process) kullan")
        if not groups:
            raise GameError("Açılacak grup yok")

        total_tiles = sum(len(g) for g in groups)
        if total_tiles >= len(p.hand):
            # atacak taş kalmalı; tüm eli birden açarak (atmadan) bitilemez
            raise GameError("Elindeki tüm taşları açamazsın, atacak bir taş kalmalı")

        # tüm taşları doğrula (henüz elden çıkarmadan)
        seen = set()
        melds_tiles: List[List[Tile]] = []
        total = 0
        for g in groups:
            for tid in g:
                if tid in seen:
                    raise GameError("Aynı taş iki grupta olamaz")
                seen.add(tid)
            tiles = [self._tile_in_hand(p, tid) for tid in g]
            total += self._validate(tiles)
            melds_tiles.append(tiles)

        if total < OPEN_THRESHOLD:
            raise GameError(f"Açmak için en az {OPEN_THRESHOLD} puan gerekli (şu an {total})")

        # uygula
        for tiles in melds_tiles:
            self._take_from_hand(p, [t.tid for t in tiles])
            self.table.append(TableMeld(self._next_meld_id(), p.pid, list(tiles)))
        p.opened = True
        self._log(f"{p.name} açıldı ({total} puan)")

    def _tile_in_hand(self, p: Player, tid: int) -> Tile:
        for t in p.hand:
            if t.tid == tid:
                return t
        raise GameError(f"Taş elinde değil: {tid}")

    def process(self, pid: str, meld_id: int, tids: List[int]) -> None:
        """İşleme: açıldıktan sonra masadaki bir gruba elinden taş ekle."""
        p = self._require_turn(pid, Phase.ACTION)
        if not p.opened:
            raise GameError("Önce açılmalısın")
        target = next((m for m in self.table if m.meld_id == meld_id), None)
        if target is None:
            raise GameError("Grup bulunamadı")
        add_tiles = [self._tile_in_hand(p, tid) for tid in tids]
        if len(p.hand) - len(add_tiles) < 1:
            # son taşını işleyemezsin; eli bitirmek için atman gerekir
            raise GameError("Son taşını işleyemezsin, atarak bitirmelisin")
        candidate = target.tiles + add_tiles
        # yeni hali geçerli meld olmalı
        self._validate(candidate)
        self._take_from_hand(p, tids)
        target.tiles = candidate

    def discard(self, pid: str, tid: int) -> Tile:
        p = self._require_turn(pid, Phase.ACTION)
        tile = self._tile_in_hand(p, tid)
        p.hand.remove(tile)
        self.discards[p.pid].append(tile)
        self.must_discard_only = False
        self._log(f"{p.name} attı: {self._tile_name(tile)}")

        # bitiş kontrolü: açmış ve eli boşaldıysa kazandı
        if p.opened and len(p.hand) == 0:
            self._finish(p, finished_with_okey=is_wild(tile, self.okey_color, self.okey_number))
            return tile

        self._advance_turn()
        return tile

    def _advance_turn(self) -> None:
        self.turn_index = (self.turn_index + 1) % NUM_PLAYERS
        self.phase = Phase.DRAW

    # --- el sonu ----------------------------------------------------------
    def _finish(self, winner: Player, finished_with_okey: bool) -> None:
        self.winner = winner.pid
        self.phase = Phase.FINISHED
        extra = " (okey atarak, çifte!)" if finished_with_okey else ""
        self._log(f"🏆 {winner.name} eli bitirdi{extra}")
        deltas = scoring.score_hand(
            player_ids=[p.pid for p in self.players],
            winner_id=winner.pid,
            hands={p.pid: p.hand for p in self.players},
            opened={p.pid: p.opened for p in self.players},
            okey_color=self.okey_color,
            okey_number=self.okey_number,
            finished_with_okey=finished_with_okey,
        )
        self.last_delta = deltas
        for p in self.players:
            p.score += deltas.get(p.pid, 0)

    def _end_hand_no_winner(self) -> None:
        """Deste bitti; kazanan yok, açmışların eli cezalanır."""
        self.winner = None
        self.phase = Phase.FINISHED
        self._log("Deste bitti — el berabere sonuçlandı")
        deltas = {}
        for p in self.players:
            if p.opened:
                deltas[p.pid] = scoring.hand_penalty(p.hand, self.okey_color, self.okey_number)
            else:
                deltas[p.pid] = scoring.NOT_OPENED_PENALTY
        self.last_delta = deltas
        for p in self.players:
            p.score += deltas[p.pid]

    # --- görünüm (client'a) ----------------------------------------------
    def public_state(self) -> dict:
        return {
            "room_id": self.room_id,
            "phase": self.phase.value,
            "hand_number": self.hand_number,
            "turn": self.players[self.turn_index].pid if self.players else None,
            "indicator": self.indicator.to_dict() if self.indicator else None,
            "okey": {"color": self.okey_color.value, "number": self.okey_number}
            if self.okey_color else None,
            "draw_count": len(self.draw_pile),
            "must_discard_only": self.must_discard_only,
            "winner": self.winner,
            "last_delta": self.last_delta,
            "log": self.log[-20:],
            "table": [
                {"meld_id": m.meld_id, "owner": m.owner,
                 "tiles": [t.to_dict() for t in m.tiles]}
                for m in self.table
            ],
            "discards": {
                pid: [t.to_dict() for t in pile[-1:]]  # sadece üstteki görünür
                for pid, pile in self.discards.items()
            },
            "players": [
                {"pid": p.pid, "name": p.name, "is_bot": p.is_bot,
                 "connected": p.connected, "opened": p.opened,
                 "score": p.score, "hand_count": len(p.hand)}
                for p in self.players
            ],
        }

    def private_state(self, pid: str) -> dict:
        """public_state + o oyuncunun kendi eli."""
        state = self.public_state()
        p = self.player(pid)
        state["you"] = {
            "pid": p.pid,
            "hand": [t.to_dict() for t in p.hand],
            "opened": p.opened,
        }
        return state
