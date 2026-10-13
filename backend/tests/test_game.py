"""Oyun durum makinesi + bot entegrasyon testleri. pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import bot
from app.game import Game, GameError, Phase
from app.tiles import Color


def _new_game(seed=1):
    g = Game("test", seed=seed)
    for i in range(4):
        g.add_player(f"p{i}", f"Oyuncu{i}", is_bot=True)
    return g


def test_lobby_limits():
    g = _new_game()
    try:
        g.add_player("x", "fazladan")
        assert False, "5. oyuncu kabul edilmemeli"
    except GameError:
        pass


def test_start_deals_correctly():
    g = _new_game()
    g.start_hand()
    counts = sorted(len(p.hand) for p in g.players)
    assert counts == [14, 14, 14, 15]  # başlayan 15, diğerleri 14
    assert g.indicator is not None and not g.indicator.is_fake_joker
    assert g.okey_number == (g.indicator.number + 1 if g.indicator.number < 13 else 1)
    # toplam taş korunumu
    total = len(g.draw_pile) + 1 + sum(len(p.hand) for p in g.players)
    assert total == 106


def test_tile_conservation_full_game():
    g = _new_game(seed=7)
    g.start_hand()
    turns = 0
    while g.phase != Phase.FINISHED and turns < 3000:
        try:
            bot.take_turn(g, g.current.pid)
        except GameError:
            if g.phase == Phase.FINISHED:
                break
            raise
        turns += 1
    assert g.phase == Phase.FINISHED
    total = len(g.draw_pile) + (1 if g.indicator else 0)
    total += sum(len(p.hand) for p in g.players)
    total += sum(len(m.tiles) for m in g.table)
    total += sum(len(pile) for pile in g.discards.values())
    assert total == 106


def test_cannot_play_out_of_turn():
    g = _new_game()
    g.start_hand()
    not_current = next(p for p in g.players if p.pid != g.current.pid)
    try:
        g.discard(not_current.pid, not_current.hand[0].tid)
        assert False
    except GameError:
        pass


def test_winner_gets_recorded_and_scored():
    # birçok tohum dene, kazananla biten bir oyun bul ve skorları kontrol et
    for seed in range(50):
        g = _new_game(seed=seed)
        g.start_hand()
        turns = 0
        while g.phase != Phase.FINISHED and turns < 3000:
            try:
                bot.take_turn(g, g.current.pid)
            except GameError:
                if g.phase == Phase.FINISHED:
                    break
                raise
            turns += 1
        if g.winner:
            assert g.last_delta[g.winner] == 0  # kazanan ceza almaz
            winner = g.player(g.winner)
            assert len(winner.hand) == 0
            assert winner.opened
            return
    assert False, "50 tohumda kazananla biten oyun bulunamadı"


if __name__ == "__main__":  # pragma: no cover
    for name in [n for n in dir() if n.startswith("test_")]:
        globals()[name]()
        print("ok", name)
