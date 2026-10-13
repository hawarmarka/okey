"""Basit bot oyuncu.

Strateji (greedy):
- DRAW: Sağdaki oyuncunun attığı taş elimi tamamlıyorsa onu al, yoksa desteden çek.
- ACTION:
    1. Açılmadıysam ve >=101 açılış varsa aç.
    2. Açıldıysam ve tüm elim (bir atış hariç) gruplanabiliyorsa -> işle ve bitir.
    3. Açıldıysam işlenebilecek taşları masaya ekle.
    4. En işe yaramaz taşı at (jokerleri son çıkar).
Bot kuralları ihlal eden bir hamle denemez; her hamle game.py ile doğrulanır.
"""

from __future__ import annotations

from typing import List, Optional

from . import solver
from .game import Game, GameError, Phase
from .melds import OPEN_THRESHOLD
from .tiles import Color, Tile, is_wild


def _tile_usefulness(hand: List[Tile], tile: Tile, okc: Color, okn: int) -> int:
    """Taşın elde ne kadar işe yaradığı — düşük = atmaya aday."""
    if is_wild(tile, okc, okn) or tile.is_fake_joker:
        return 100  # joker/sahte okey asla ilk atılmaz
    score = 0
    for other in hand:
        if other.tid == tile.tid or other.is_fake_joker:
            continue
        if other.color == tile.color and other.number is not None and tile.number is not None:
            if abs(other.number - tile.number) <= 2:  # seri yakınlığı
                score += 2
        if other.number == tile.number and other.color != tile.color:  # per
            score += 3
    return score


def take_turn(game: Game, pid: str) -> List[dict]:
    """Botun tüm sırasını oynatır. Yapılan hamlelerin özetini döner."""
    actions: List[dict] = []
    p = game.player(pid)
    okc, okn = game.okey_color, game.okey_number

    # --- DRAW fazı ---
    if game.phase == Phase.DRAW:
        took = False
        prev_idx = (game.turn_index - 1) % len(game.players)
        prev = game.players[prev_idx]
        disc = game.discards.get(prev.pid, [])
        if disc:
            top = disc[-1]
            # bu taşı alırsam açılış/kapanış şansım artıyor mu? kabaca: bir meld'e giriyor mu
            trial = p.hand + [top]
            cands = solver.generate_candidates(trial, okc, okn)
            if any(top.tid in c["tids"] for c in cands):
                try:
                    game.draw_from_discard(pid)
                    actions.append({"action": "draw_discard", "tile": top.to_dict()})
                    took = True
                except GameError:
                    pass
        if not took:
            game.draw_from_pile(pid)
            actions.append({"action": "draw_pile"})

    if game.phase != Phase.ACTION or game.current.pid != pid:
        return actions

    # --- ACTION fazı ---
    # 1. bitiş denemesi (açık ya da değil; bir taş atıp kalanı tümüyle gruplama)
    _try_finish(game, pid, actions)
    if game.phase == Phase.FINISHED:
        return actions

    # 2. açılma (kısmi — atacak taş bırakır)
    if not p.opened:
        opening = solver.find_opening(p.hand, okc, okn, OPEN_THRESHOLD)
        if opening:
            groups = [[t.tid for t in g] for g in opening]
            try:
                game.open_melds(pid, groups)
                actions.append({"action": "open", "groups": groups})
            except GameError:
                pass

    # 3. açıldıysa tek tek işleme
    if p.opened:
        _try_process(game, pid, actions)

    # 4. atış (hâlâ bizim sıramızsa)
    if game.phase == Phase.ACTION and game.current.pid == pid and p.hand:
        worst = min(p.hand, key=lambda t: _tile_usefulness(p.hand, t, okc, okn))
        game.discard(pid, worst.tid)
        actions.append({"action": "discard", "tile": worst.to_dict()})
    return actions


def _try_finish(game: Game, pid: str, actions: List[dict]) -> None:
    """Bir taş atıp kalanı tamamen gruplayabiliyorsak: aç/işle + at + bitir.

    Açılmamışsak bu aynı zamanda ilk açılıştır; kalan gruplar toplamı >=101 olmalı.
    """
    from .melds import OPEN_THRESHOLD, melds_total_points
    p = game.player(pid)
    okc, okn = game.okey_color, game.okey_number
    hand_cands = solver.generate_candidates(p.hand, okc, okn)  # tur başına tek üretim
    for discard_candidate in list(p.hand):
        rest = [t for t in p.hand if t.tid != discard_candidate.tid]
        if len(rest) < 3:
            continue
        cover = solver.find_full_cover(rest, okc, okn, cands=hand_cands)
        if cover is None:
            continue
        groups = [[t.tid for t in g] for g in cover]
        try:
            if p.opened:
                _open_extra(game, pid, groups)
            else:
                # ilk açılış: eşik tutmazsa bu taşla bitiş geçersiz, başka taş dene
                if melds_total_points(cover, okc, okn) < OPEN_THRESHOLD:
                    continue
                game.open_melds(pid, groups)
            game.discard(pid, discard_candidate.tid)
            actions.append({"action": "finish", "discard": discard_candidate.to_dict()})
            return
        except GameError:
            continue


def _open_extra(game: Game, pid: str, groups: List[List[int]]) -> None:
    """Açılmış oyuncunun ek grupları masaya koyması (eşik aranmaz)."""
    from .game import TableMeld
    p = game.player(pid)
    melds_tiles = []
    seen = set()
    for g in groups:
        for tid in g:
            if tid in seen:
                raise GameError("çift taş")
            seen.add(tid)
        tiles = [game._tile_in_hand(p, tid) for tid in g]
        game._validate(tiles)
        melds_tiles.append(tiles)
    for tiles in melds_tiles:
        game._take_from_hand(p, [t.tid for t in tiles])
        game.table.append(TableMeld(game._next_meld_id(), p.pid, list(tiles)))


def _try_process(game: Game, pid: str, actions: List[dict]) -> None:
    p = game.player(pid)
    okc, okn = game.okey_color, game.okey_number
    changed = True
    while changed and p.hand:
        changed = False
        for tile in list(p.hand):
            for m in list(game.table):
                try:
                    game.process(pid, m.meld_id, [tile.tid])
                    actions.append({"action": "process", "meld_id": m.meld_id,
                                    "tile": tile.to_dict()})
                    changed = True
                    break
                except GameError:
                    continue
            if changed:
                break
