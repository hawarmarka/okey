"""Per (set) ve seri (run) doğrulama + puanlama.

Tanımlar:
- Seri (run): aynı renk, ardışık sayılar, 3+ taş. Örn: sarı 4-5-6.
  1 hem baş (1-2-3) hem son (12-13-1) olabilir.
- Per (set): aynı sayı, farklı renkler, 3 veya 4 taş. Örn: mavi7 siyah7 kırmızı7.

Jokerler:
- Gerçek okey (wild): meld içinde eksik taşın yerine geçer.
- Sahte okey: okey taşını (okey renk+sayı) temsil eden normal bir taş gibi davranır.

Kurallar (yapılandırılabilir sabitler aşağıda):
- Bir meld'de en fazla MAX_WILDS_PER_MELD gerçek okey kullanılabilir.
- Açma eşiği: OPEN_THRESHOLD (varsayılan 101).
- 1 sayısının seri sonunda (12-13-1) puanı ACE_HIGH_VALUE.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .tiles import ALL_COLORS, Color, Tile, is_wild

# --- Yapılandırılabilir kurallar ---
MAX_WILDS_PER_MELD = 1      # bir grupta en fazla kaç gerçek okey
OPEN_THRESHOLD = 101        # ilk açmada gereken minimum puan
ACE_HIGH_VALUE = 14         # 1, serinin yüksek ucundaysa (12-13-1) puanı
ALLOW_ACE_HIGH_RUN = True   # 12-13-1 serisine izin ver


class MeldError(ValueError):
    """Geçersiz meld."""


def _split_wilds(tiles: List[Tile], okey_color: Color, okey_number: int):
    """Taşları (gerçek_okeyler, normal_taşlar) olarak ayırır.

    Sahte okey -> okey taşının (renk, sayı) değeriyle normal muamele görür.
    """
    wilds: List[Tile] = []
    normals: List[Tuple[Color, int, Tile]] = []  # (renk, sayı, taş)
    for t in tiles:
        if is_wild(t, okey_color, okey_number):
            wilds.append(t)
        elif t.is_fake_joker:
            normals.append((okey_color, okey_number, t))
        else:
            assert t.color is not None and t.number is not None
            normals.append((t.color, t.number, t))
    return wilds, normals


def validate_set(tiles: List[Tile], okey_color: Color, okey_number: int) -> int:
    """Per doğrular; geçerliyse puanını döner, değilse MeldError atar."""
    if not (3 <= len(tiles) <= 4):
        raise MeldError("Per 3 veya 4 taş olmalı")
    wilds, normals = _split_wilds(tiles, okey_color, okey_number)
    if len(wilds) > MAX_WILDS_PER_MELD:
        raise MeldError("Bir perde en fazla bir okey kullanılabilir")
    if not normals:
        raise MeldError("Per salt jokerlerden oluşamaz")

    numbers = {n for _, n, _ in normals}
    if len(numbers) != 1:
        raise MeldError("Perdeki taşlar aynı sayıda olmalı")
    number = next(iter(numbers))

    colors = [c for c, _, _ in normals]
    if len(colors) != len(set(colors)):
        raise MeldError("Perde renkler farklı olmalı")
    # jokerler + normal taşlar toplamı renk sayısını (4) aşamaz -> zaten len<=4 garantili
    # puan: her taş `number` değerinde (joker dahil)
    return number * len(tiles)


def _run_points(start: int, length: int) -> int:
    """start..start+length-1 serisinin puanı. 14 -> 1 olarak sayılır değeri 1 değil 14."""
    total = 0
    for v in range(start, start + length):
        total += v  # yüksek 1 burada 14 olarak gelir (start=... hesapta)
    return total


def validate_run(tiles: List[Tile], okey_color: Color, okey_number: int) -> int:
    """Seri doğrular; geçerliyse puanını döner, değilse MeldError atar."""
    if len(tiles) < 3:
        raise MeldError("Seri en az 3 taş olmalı")
    wilds, normals = _split_wilds(tiles, okey_color, okey_number)
    if len(wilds) > MAX_WILDS_PER_MELD:
        raise MeldError("Bir seride en fazla bir okey kullanılabilir")
    if not normals:
        raise MeldError("Seri salt jokerlerden oluşamaz")

    colors = {c for c, _, _ in normals}
    if len(colors) != 1:
        raise MeldError("Serideki taşlar aynı renk olmalı")

    n_wild = len(wilds)
    length = len(tiles)

    # Olası sayı yorumları: 1 düşük (1) ve (izinliyse) yüksek (14).
    def try_arrangement(values: List[int]) -> bool:
        if len(set(values)) != len(values):
            return False  # seride tekrar olamaz
        lo, hi = min(values), max(values)
        span = hi - lo + 1
        # pencere uzunluğu, toplam taş sayısına eşit olmalı; boşlukları jokerler doldurur
        if span > length:
            return False
        # pencereyi length uzunluğuna kadar kaydırabiliriz (jokerler uçlara da gidebilir)
        needed_gaps = length - len(values)  # joker ile doldurulacak toplam yer
        if needed_gaps != n_wild:
            return False
        # length uzunluğunda, tüm `values`i içeren bir pencere var mı?
        for window_start in range(hi - length + 1, lo + 1):
            window_end = window_start + length - 1
            if window_start < 1:
                continue
            if all(window_start <= v <= window_end for v in values):
                return True
        return False

    base = [n for _, n, _ in normals]

    candidates: List[List[int]] = [base]
    if ALLOW_ACE_HIGH_RUN and 1 in base:
        high = [ACE_HIGH_VALUE if v == 1 else v for v in base]
        candidates.append(high)

    for values in candidates:
        if max(values) <= 13 or ACE_HIGH_VALUE in values:
            if try_arrangement(values):
                return _best_run_points(values, length, n_wild)

    raise MeldError("Taşlar geçerli bir seri oluşturmuyor")


def _best_run_points(values: List[int], length: int, n_wild: int) -> int:
    """Doğrulanmış serinin puanı: pencereyi sabitleyip tüm pozisyonları toplar."""
    lo, hi = min(values), max(values)
    # geçerli bir pencere seç (ilk bulunan); jokerler o penceredeki boş değerleri alır
    for window_start in range(hi - length + 1, lo + 1):
        window_end = window_start + length - 1
        if window_start < 1:
            continue
        if all(window_start <= v <= window_end for v in values):
            return sum(range(window_start, window_end + 1))
    return sum(values)  # teorik olarak buraya gelinmez


def validate_meld(tiles: List[Tile], okey_color: Color, okey_number: int) -> int:
    """Taş grubunu per ya da seri olarak doğrular; puanı döner."""
    errors = []
    for fn in (validate_set, validate_run):
        try:
            return fn(tiles, okey_color, okey_number)
        except MeldError as e:
            errors.append(str(e))
    raise MeldError("Geçersiz grup: " + " / ".join(errors))


def is_valid_meld(tiles: List[Tile], okey_color: Color, okey_number: int) -> bool:
    try:
        validate_meld(tiles, okey_color, okey_number)
        return True
    except MeldError:
        return False


def melds_total_points(
    melds: List[List[Tile]], okey_color: Color, okey_number: int
) -> int:
    """Birden çok grubun toplam puanı. Herhangi biri geçersizse MeldError."""
    return sum(validate_meld(m, okey_color, okey_number) for m in melds)
