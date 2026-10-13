# Okey 101

Kendi sunucunda çalışan, gerçek zamanlı çok oyunculu **Okey 101**. Tek servis:
FastAPI + WebSocket arka uç, statik tek-sayfa arayüz, botlarla tek başına
oynanabilir. Otoriter sunucu mimarisi — tüm taşlar sunucuda; istemci yalnızca
kendi elini görür, bu yüzden "rakibin taşını görme / sahte açılış" gibi hileler
mümkün değil.

```
okey101/
├─ backend/
│  ├─ app/
│  │  ├─ tiles.py     # 106 taşlık deste, gösterge/okey/sahte okey
│  │  ├─ melds.py     # per & seri doğrulama, joker mantığı, puanlama
│  │  ├─ scoring.py   # el sonu ceza/puan hesabı
│  │  ├─ solver.py    # açılış & bitiş için meld çözücü (bot kullanır)
│  │  ├─ game.py      # oyun durum makinesi (otoriter çekirdek)
│  │  ├─ bot.py       # basit yapay zekâ oyuncu
│  │  ├─ rooms.py     # oda/oturum çalışma-zamanı (fastapi'siz, test edilebilir)
│  │  └─ server.py    # FastAPI + WebSocket + statik arayüz
│  ├─ tests/          # pytest: mantık + oyun + bot
│  └─ requirements.txt
├─ frontend/
│  ├─ index.html      # masa + lobi (saf HTML/CSS, build yok)
│  └─ app.js          # WebSocket istemcisi
├─ Dockerfile
└─ docker-compose.yml
```

## Hızlı başlangıç (yerel)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.server:app --reload --port 8000
```

Tarayıcıda `http://localhost:8000` → ad + oda kodu gir → **Boş yerleri bota
doldur** → **Oyunu Başlat**.

Birden çok kişiyle: herkes aynı oda kodunu girsin (örn. `salon1`). Oda sahibi
(ilk giren) botla doldurabilir ve oyunu başlatır.

Docker ile:

```bash
docker compose up --build   # http://localhost:8000
```

## Nasıl oynanır (arayüz)

- **Sıra sende, "çek" fazı:** *Desteden Çek* ya da sağındaki (senden önceki)
  oyuncunun attığını *Atılanı Al*.
- **Açılma:** elinde taşları tıkla → *Seçilenleri gruba ekle* (3+ taş) → istediğin
  kadar grup hazırla → *Aç*. Grupların toplamı **≥101** olmalı (yoksa sunucu
  reddeder).
- **İşleme:** açıldıktan sonra masadaki bir gruba tıkla, elinden taş(lar) seç →
  *Seçilenleri işle*.
- **Atma:** tek taş seç → *Seçili taşı AT*. Sıra sola geçer.
- **Bitiş:** açıldıysan ve son taşını atınca elin boşalırsa eli kazanırsın.
  (Okey atarak bitirirsen kaybedenlerin cezası iki katı.)

`OKEY` etiketli taş senin elindeki **joker**tir (her taşın yerine geçer).
`★` sahte okeydir ve okey taşını (gösterge+1) temsil eder.

## Uygulanan kurallar & ayarlanabilir sabitler

Okey 101'in bölgesel varyasyonları var. Varsayılanlar yaygın kuralları izler ve
tek yerden değiştirilebilir:

| Kural | Dosya | Sabit | Varsayılan |
|---|---|---|---|
| Açma eşiği | `app/melds.py` | `OPEN_THRESHOLD` | 101 |
| Grupta azami joker | `app/melds.py` | `MAX_WILDS_PER_MELD` | 1 |
| 12-13-1 serisine izin | `app/melds.py` | `ALLOW_ACE_HIGH_RUN` | True |
| Yüksek 1 puanı | `app/melds.py` | `ACE_HIGH_VALUE` | 14 |
| Açmadan el bitirme cezası | `app/scoring.py` | `NOT_OPENED_PENALTY` | 101 |
| Elde kalan okey cezası | `app/scoring.py` | `WILD_PENALTY` | 25 |
| Okey atarak bitiş 2x | `app/scoring.py` | `DOUBLE_ON_OKEY_FINISH` | True |

**Seri (run):** aynı renk, ardışık sayı, 3+ taş. 1 hem baş (1-2-3) hem son
(12-13-1) olabilir.
**Per (set):** aynı sayı, farklı renk, 3–4 taş.
Her ikisinde de en fazla bir gerçek okey (joker) kullanılabilir; sahte okey, okey
taşının değeriyle normal taş gibi sayılır.

> Senin oynadığın varyant farklıysa (ör. açma 101 yerine 51, ya da farklı ceza
> puanları) yukarıdaki sabitleri değiştirmen yeterli — mantığın geri kalanı
> kuralı sabitten okur.

## WebSocket protokolü

Tek uç: `ws://<host>/ws/<oda_kodu>`. Tüm mesajlar JSON.

İstemci → Sunucu:

```jsonc
{"type":"hello","name":"Hawar","pid":"<varsa önceki pid>"}  // katıl / yeniden bağlan
{"type":"add_bots"}                                          // boş yerleri bota doldur (host)
{"type":"start"}                                             // eli başlat (host, 4 oyuncu)
{"type":"draw","source":"pile"}                              // desteden çek
{"type":"draw","source":"discard"}                           // soldakinin attığını al
{"type":"open","groups":[[tid,tid,tid],[tid,...]]}           // ilk açılış (≥101)
{"type":"process","meld_id":3,"tids":[tid]}                  // masadaki gruba ekle
{"type":"discard","tid":123}                                 // taş at
{"type":"new_hand"}                                          // el bitince yeni el (host)
```

Sunucu → İstemci:

```jsonc
{"type":"joined","pid":"...","is_host":true}
{"type":"state","state":{ ...herkese açık durum + "you":{hand:[...]} }}
{"type":"error","message":"..."}
```

`state` içinde rakip elleri yalnızca sayıyla (`hand_count`) görünür; taşlar
gizlidir. `pid` istemcide `localStorage`'da tutulur → kopan oyuncu aynı pid ile
geri bağlanır (reconnection).

## Testler

```bash
cd backend
pip install pytest
pytest -q          # tiles/melds/scoring + oyun/bot entegrasyon testleri
```

Testler 4 botla uçtan uca tam oyunlar oynatır ve her oyunda **taş korunumunu
(106)**, sıra geçişini, açma/bitiş kurallarını ve puanlamayı doğrular.

## Coolify'a deploy (okey.hawarserver.com)

1. Bu klasörü bir git deposuna koy, Coolify'da **New Resource → Application →
   Dockerfile** (kök dizin: repo kökü, Dockerfile otomatik bulunur).
2. **Port:** 8000 (uygulama `PORT` env'ini de dinler).
3. **Domain:** `https://okey.hawarserver.com` ata. Wildcard Cloudflare DNS'in
   zaten `*.hawarserver.com`'u sunucuna yönlendiriyor; Coolify'ın ürettiği Traefik
   etiketi WebSocket'i (`/ws`) olduğu gibi proxy'ler — ek ayar gerekmez.
4. Deploy. Health check: `GET /health` → `{"ok":true}`.

> WebSocket, sayfayla aynı origin'den (`wss://okey.hawarserver.com/ws/...`)
> bağlanır; HTTPS arkasında otomatik `wss` kullanılır, ek CORS/proxy ayarı yok.

## Kapsam ve sonraki adımlar

Bu sürüm **oynanabilir çekirdek**: lobi, 4 oyuncu (insan+bot karışık), tam Okey
101 kuralları, reconnection, el-eli puan birikimi. Durum bellekte tutulur (tek
instance için ideal). Doğal sonraki katmanlar:

- **Kalıcılık:** hesaplar, maç geçmişi, sıralama → PostgreSQL. Aktif oyun durumu
  için Redis (çok-instance ölçekleme + pub/sub).
- **Daha güçlü bot:** şu an greedy; olasılık/риск değerlendirmesi eklenebilir.
- **UX:** süre aşımı + otomatik atma, taş gruplarını kaydetme, ses, mobil dokunuş
  iyileştirmeleri, animasyonlar.
- **Varyantlar:** çifte okey (gösterge çifti), farklı açma eşikleri, eleme/tavan
  puanı seçenekleri — çoğu sabitlerle açılabilir.

Mimari buna hazır: `game.py` saf ve test edilebilir; `rooms.py` taşımadan
ayrıştırılmış; bir DB katmanı `rooms.py`'nin yanına eklenebilir.
