"""El sonu puanlama.

101 Okey'de düşük puan iyidir; belirli bir tavana (varsayılan) ulaşan elenir
ya da N el sonunda en düşük toplam kazanır. Her el sonunda:

- Kazanan (eli bitiren): kazanç = WINNER_DELTA (varsayılan 0; istenirse -101 bonus).
- Açmış kaybeden: elinde kalan taşların değeri kadar ceza.
- Hiç açmamış kaybeden: NOT_OPENED_PENALTY düz ceza (varsayılan 101).
- Okey atarak bitirme: kaybedenlerin cezası 2 ile çarpılır (çifte el).

Bu sabitler bölgesel varyanta göre ayarlanabilir.
"""

from __future__ import annotations

from typing import Dict, List

from .tiles import Color, Tile, is_wild

# --- Yapılandırılabilir puanlama ---
WINNER_DELTA = 0            # kazananın skoruna eklenen (negatif = bonus)
NOT_OPENED_PENALTY = 101    # hiç açmadan el biterse düz ceza
WILD_PENALTY = 25           # elde kalan gerçek okey (joker) cezası
DOUBLE_ON_OKEY_FINISH = True  # okey atarak bitince kaybedenler 2x


def hand_penalty(hand: List[Tile], okey_color: Color, okey_number: int) -> int:
    """Elde kalan taşların ceza değeri (açmış oyuncu için)."""
    total = 0
    for t in hand:
        if is_wild(t, okey_color, okey_number):
            total += WILD_PENALTY
        elif t.is_fake_joker:
            total += okey_number  # temsil ettiği okey sayısı
        else:
            assert t.number is not None
            total += t.number
    return total


def score_hand(
    *,
    player_ids: List[str],
    winner_id: str,
    hands: Dict[str, List[Tile]],
    opened: Dict[str, bool],
    okey_color: Color,
    okey_number: int,
    finished_with_okey: bool = False,
) -> Dict[str, int]:
    """Her oyuncu için bu elde skora eklenecek delta'yı döner."""
    deltas: Dict[str, int] = {}
    multiplier = 2 if (finished_with_okey and DOUBLE_ON_OKEY_FINISH) else 1
    for pid in player_ids:
        if pid == winner_id:
            deltas[pid] = WINNER_DELTA
        elif not opened.get(pid, False):
            deltas[pid] = NOT_OPENED_PENALTY * multiplier
        else:
            deltas[pid] = hand_penalty(hands[pid], okey_color, okey_number) * multiplier
    return deltas
