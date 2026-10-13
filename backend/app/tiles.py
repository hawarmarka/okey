"""Taş modeli ve deste üretimi.

Okey 101 seti: 106 taş.
- 1..13 arası sayılar, 4 renk (SARI, MAVI, SIYAH, KIRMIZI), her biri 2'şer kopya
  => 13 * 4 * 2 = 104 sayı taşı
- 2 adet sahte okey (fake joker) => toplam 106

Gösterge (indicator) açılır. Okey = göstergenin bir fazlası, aynı renk (13 -> 1 sarar).
- Gerçek okey taşları (okey renk + okey sayı) OYUNDA JOKER olur (her taşın yerine geçer).
- Sahte okey taşları, okey taşını (okey renk + okey sayı) TEMSİL EDER; joker değildir.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class Color(str, Enum):
    SARI = "sari"      # yellow
    MAVI = "mavi"      # blue
    SIYAH = "siyah"    # black
    KIRMIZI = "kirmizi"  # red


ALL_COLORS = [Color.SARI, Color.MAVI, Color.SIYAH, Color.KIRMIZI]
MIN_NUM = 1
MAX_NUM = 13


@dataclass(frozen=True)
class Tile:
    """Tek bir taş. `tid` deste içinde benzersizdir (aynı değerli taşlar ikişer var)."""
    tid: int
    color: Optional[Color]      # sahte okeyde None
    number: Optional[int]       # sahte okeyde None
    is_fake_joker: bool = False

    def to_dict(self) -> dict:
        return {
            "tid": self.tid,
            "color": self.color.value if self.color else None,
            "number": self.number,
            "is_fake_joker": self.is_fake_joker,
        }

    def __repr__(self) -> str:  # pragma: no cover
        if self.is_fake_joker:
            return f"<FakeOkey #{self.tid}>"
        return f"<{self.color.value if self.color else '?'}{self.number} #{self.tid}>"


def build_deck() -> List[Tile]:
    """106 taşlık tam desteyi (karıştırılmamış) üretir."""
    tiles: List[Tile] = []
    tid = 0
    for _copy in range(2):
        for color in ALL_COLORS:
            for number in range(MIN_NUM, MAX_NUM + 1):
                tiles.append(Tile(tid=tid, color=color, number=number))
                tid += 1
    # 2 sahte okey
    for _ in range(2):
        tiles.append(Tile(tid=tid, color=None, number=None, is_fake_joker=True))
        tid += 1
    return tiles


def shuffled_deck(rng: Optional[random.Random] = None) -> List[Tile]:
    deck = build_deck()
    (rng or random).shuffle(deck)
    return deck


def okey_number_for(indicator: Tile) -> int:
    """Gösterge sayısının bir fazlası (13 -> 1)."""
    assert indicator.number is not None
    return indicator.number + 1 if indicator.number < MAX_NUM else MIN_NUM


def is_wild(tile: Tile, okey_color: Color, okey_number: int) -> bool:
    """Gerçek okey taşı mı? (joker — her şeyin yerine geçer)."""
    if tile.is_fake_joker:
        return False
    return tile.color == okey_color and tile.number == okey_number


def effective_value(tile: Tile, okey_color: Color, okey_number: int):
    """Sahte okeyin temsil ettiği (renk, sayı); diğerleri kendi değeri.

    Joker (gerçek okey) için None döner — değeri bağlama göre belirlenir.
    """
    if tile.is_fake_joker:
        return (okey_color, okey_number)
    if is_wild(tile, okey_color, okey_number):
        return None  # bağlama göre
    return (tile.color, tile.number)
