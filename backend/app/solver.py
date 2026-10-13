"""Meld çözücü: bir elden geçerli grupları bulur.

- find_full_cover: tüm taşları geçerli gruplara bölebilir mi? (bitiş için)
- find_opening: toplam >= eşik olan, ayrık gruplardan açılış bul (açma için)

Aday üretimi kaba kuvvet değil: seriler aynı renk havuzundan, perler aynı sayı
havuzundan türetilir (jokerler her havuza eklenir). validate_meld son süzgeç olarak
her adayı yine de doğrular.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Optional

from .melds import MeldError, validate_meld
from .tiles import Color, Tile, is_wild


def _effective_color(t: Tile, okc: Color, okn: int) -> Optional[Color]:
    if t.is_fake_joker:
        return okc
    return t.color


def _effective_number(t: Tile, okc: Color, okn: int) -> Optional[int]:
    if t.is_fake_joker:
        return okn
    return t.number


def generate_candidates(tiles: List[Tile], okc: Color, okn: int) -> List[Dict]:
    wilds = [t for t in tiles if is_wild(t, okc, okn)]
    by_color: Dict[Color, List[Tile]] = defaultdict(list)
    by_number: Dict[int, List[Tile]] = defaultdict(list)
    for t in tiles:
        if is_wild(t, okc, okn):
            continue
        c = _effective_color(t, okc, okn)
        n = _effective_number(t, okc, okn)
        if c is not None:
            by_color[c].append(t)
        if n is not None:
            by_number[n].append(t)

    seen = set()
    cands: List[Dict] = []

    def add(combo):
        tids = frozenset(t.tid for t in combo)
        if tids in seen:
            return
        try:
            pts = validate_meld(list(combo), okc, okn)
        except MeldError:
            return
        seen.add(tids)
        cands.append({"tids": tids, "points": pts, "tiles": list(combo)})

    # perler: aynı sayı havuzu + jokerler, boy 3-4
    for n, pool in by_number.items():
        full = pool + wilds
        for size in (3, 4):
            if size > len(full):
                break
            for combo in combinations(full, size):
                add(combo)

    # seriler: aynı renk havuzu + jokerler, boy 3-5
    for c, pool in by_color.items():
        full = pool + wilds
        for size in (3, 4, 5):
            if size > len(full):
                break
            for combo in combinations(full, size):
                add(combo)

    cands.sort(key=lambda c: -c["points"])
    return cands


def find_full_cover(
    tiles: List[Tile], okc: Color, okn: int, cands: Optional[List[Dict]] = None
) -> Optional[List[List[Tile]]]:
    """Tüm taşları ayrık geçerli gruplara böl. Bulamazsa None."""
    if not tiles:
        return []
    if len(tiles) < 3:
        return None
    if cands is None:
        cands = generate_candidates(tiles, okc, okn)
    wanted = frozenset(t.tid for t in tiles)
    # yalnızca bu taş kümesinin altındaki adaylar
    cands = [c for c in cands if c["tids"] <= wanted]

    covering: Dict[int, List[Dict]] = {tid: [] for tid in wanted}
    for c in cands:
        for tid in c["tids"]:
            covering[tid].append(c)

    result: List[List[Tile]] = []

    def backtrack(remaining: frozenset) -> bool:
        if not remaining:
            return True
        target = min(remaining, key=lambda tid: len(covering[tid]))
        if not covering[target]:
            return False
        for c in covering[target]:
            if c["tids"] <= remaining:
                result.append(c["tiles"])
                if backtrack(remaining - c["tids"]):
                    return True
                result.pop()
        return False

    return result if backtrack(wanted) else None


def find_opening(
    tiles: List[Tile], okc: Color, okn: int, threshold: int
) -> Optional[List[List[Tile]]]:
    """Ayrık gruplardan, toplamı >= threshold olan ilk açılışı bul."""
    cands = generate_candidates(tiles, okc, okn)
    best: Dict = {"groups": None}

    def dfs(idx: int, used: frozenset, chosen: List[Dict], total: int):
        if best["groups"] is not None:
            return
        if total >= threshold:
            best["groups"] = [c["tiles"] for c in chosen]
            return
        for i in range(idx, len(cands)):
            c = cands[i]
            if c["tids"] & used:
                continue
            chosen.append(c)
            dfs(i + 1, used | c["tids"], chosen, total + c["points"])
            chosen.pop()
            if best["groups"] is not None:
                return

    dfs(0, frozenset(), [], 0)
    return best["groups"]
