"""Çekirdek oyun mantığı testleri. Çalıştır: pytest -q"""
import random

import pytest

from app import melds, scoring
from app.melds import MeldError, is_valid_meld, validate_meld
from app.tiles import (
    ALL_COLORS,
    Color,
    Tile,
    build_deck,
    is_wild,
    okey_number_for,
    shuffled_deck,
)

# yardımcılar --------------------------------------------------------------
_counter = [10_000]


def mk(color, number, fake=False):
    _counter[0] += 1
    return Tile(tid=_counter[0], color=color, number=number, is_fake_joker=fake)


def fake():
    return mk(None, None, fake=True)


OKC, OKN = Color.KIRMIZI, 6  # test boyunca okey = kırmızı 6


def wild():
    return mk(Color.KIRMIZI, 6)  # gerçek okey taşı -> joker


# deste --------------------------------------------------------------------
def test_deck_has_106_tiles():
    deck = build_deck()
    assert len(deck) == 106
    fakes = [t for t in deck if t.is_fake_joker]
    assert len(fakes) == 2
    numbered = [t for t in deck if not t.is_fake_joker]
    assert len(numbered) == 104


def test_deck_two_of_each():
    deck = build_deck()
    from collections import Counter

    c = Counter((t.color, t.number) for t in deck if not t.is_fake_joker)
    assert all(v == 2 for v in c.values())
    assert len(c) == 52  # 13 * 4


def test_unique_tids():
    deck = build_deck()
    assert len({t.tid for t in deck}) == 106


def test_okey_number_wraps():
    assert okey_number_for(mk(Color.SARI, 5)) == 6
    assert okey_number_for(mk(Color.SARI, 13)) == 1


def test_wild_detection():
    assert is_wild(mk(Color.KIRMIZI, 6), OKC, OKN)
    assert not is_wild(mk(Color.KIRMIZI, 7), OKC, OKN)
    assert not is_wild(fake(), OKC, OKN)  # sahte okey joker DEĞİL


# per (set) ----------------------------------------------------------------
def test_valid_set_three():
    tiles = [mk(Color.SARI, 7), mk(Color.MAVI, 7), mk(Color.SIYAH, 7)]
    assert validate_meld(tiles, OKC, OKN) == 21


def test_valid_set_four():
    tiles = [mk(c, 9) for c in ALL_COLORS]
    assert validate_meld(tiles, OKC, OKN) == 36


def test_set_same_color_invalid():
    tiles = [mk(Color.SARI, 7), mk(Color.SARI, 7), mk(Color.MAVI, 7)]
    assert not is_valid_meld(tiles, OKC, OKN)


def test_set_with_wild():
    # sarı7 + mavi7 + joker -> geçerli per, puan 21
    tiles = [mk(Color.SARI, 7), mk(Color.MAVI, 7), wild()]
    assert validate_meld(tiles, OKC, OKN) == 21


def test_set_with_fake_joker_as_okey_tile():
    # okey = kırmızı6; sahte okey kırmızı6 yerine geçer.
    # 6'lık per: sarı6 + mavi6 + sahteokey(=kırmızı6) -> geçerli
    tiles = [mk(Color.SARI, 6), mk(Color.MAVI, 6), fake()]
    assert validate_meld(tiles, OKC, OKN) == 18


def test_set_two_wilds_invalid():
    tiles = [mk(Color.SARI, 7), wild(), wild()]
    assert not is_valid_meld(tiles, OKC, OKN)


# seri (run) ---------------------------------------------------------------
def test_valid_run():
    tiles = [mk(Color.SARI, 4), mk(Color.SARI, 5), mk(Color.SARI, 6)]
    assert validate_meld(tiles, OKC, OKN) == 15


def test_run_different_color_invalid():
    tiles = [mk(Color.SARI, 4), mk(Color.MAVI, 5), mk(Color.SARI, 6)]
    assert not is_valid_meld(tiles, OKC, OKN)


def test_run_with_wild_middle():
    # sarı 4 - joker - sarı 6  => 4,5,6 serisi, puan 15
    tiles = [mk(Color.SARI, 4), wild(), mk(Color.SARI, 6)]
    assert validate_meld(tiles, OKC, OKN) == 15


def test_run_with_wild_end():
    # sarı 4-5 + joker  => 4,5,6 veya 3,4,5; puan 15 veya 12 — en az biri geçerli
    tiles = [mk(Color.SARI, 4), mk(Color.SARI, 5), wild()]
    pts = validate_meld(tiles, OKC, OKN)
    assert pts in (12, 15)


def test_run_low_ace():
    tiles = [mk(Color.MAVI, 1), mk(Color.MAVI, 2), mk(Color.MAVI, 3)]
    assert validate_meld(tiles, OKC, OKN) == 6


def test_run_high_ace():
    # 11-12-13-1 -> yüksek 1 = 14 ; puan 11+12+13+14 = 50
    tiles = [mk(Color.MAVI, 11), mk(Color.MAVI, 12), mk(Color.MAVI, 13), mk(Color.MAVI, 1)]
    assert validate_meld(tiles, OKC, OKN) == 50


def test_run_duplicate_number_invalid():
    tiles = [mk(Color.SARI, 4), mk(Color.SARI, 4), mk(Color.SARI, 5)]
    assert not is_valid_meld(tiles, OKC, OKN)


def test_long_run():
    tiles = [mk(Color.SIYAH, n) for n in range(5, 11)]  # 5..10
    assert validate_meld(tiles, OKC, OKN) == sum(range(5, 11))


# açma eşiği ---------------------------------------------------------------
def test_open_threshold_total():
    m1 = [mk(c, 13) for c in ALL_COLORS]           # 52
    m2 = [mk(Color.SARI, 10), mk(Color.SARI, 11), mk(Color.SARI, 12), mk(Color.SARI, 13)]  # 46
    total = melds.melds_total_points([m1, m2], OKC, OKN)
    assert total == 98
    m3 = [mk(Color.MAVI, 1), mk(Color.MAVI, 2), mk(Color.MAVI, 3)]  # 6
    total2 = melds.melds_total_points([m1, m2, m3], OKC, OKN)
    assert total2 == 104 >= melds.OPEN_THRESHOLD


# puanlama -----------------------------------------------------------------
def test_hand_penalty():
    hand = [mk(Color.SARI, 5), mk(Color.MAVI, 10), fake()]  # 5 + 10 + 6(okey) = 21
    assert scoring.hand_penalty(hand, OKC, OKN) == 21


def test_hand_penalty_wild():
    hand = [wild(), mk(Color.SARI, 3)]  # 25 + 3
    assert scoring.hand_penalty(hand, OKC, OKN) == 28


def test_score_hand_not_opened():
    pids = ["a", "b", "c", "d"]
    hands = {p: [mk(Color.SARI, 5)] for p in pids}
    opened = {"a": True, "b": True, "c": False, "d": True}
    deltas = scoring.score_hand(
        player_ids=pids, winner_id="a", hands=hands, opened=opened,
        okey_color=OKC, okey_number=OKN,
    )
    assert deltas["a"] == 0            # kazanan
    assert deltas["c"] == 101          # açmadı -> düz ceza
    assert deltas["b"] == 5            # açtı -> elde kalan


def test_score_hand_okey_finish_doubles():
    pids = ["a", "b"]
    hands = {"a": [], "b": [mk(Color.SARI, 5)]}
    opened = {"a": True, "b": True}
    deltas = scoring.score_hand(
        player_ids=pids, winner_id="a", hands=hands, opened=opened,
        okey_color=OKC, okey_number=OKN, finished_with_okey=True,
    )
    assert deltas["b"] == 10  # 5 * 2


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
