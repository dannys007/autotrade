# autotrade — Binance Futures trend-following bot (Freqtrade)

Bot trading otomatis untuk Binance USDT-M Futures berbasis
[Freqtrade](https://www.freqtrade.io/), dengan strategi trend-following
(EMA cross + filter ADX/RSI) dan manajemen risiko berbasis persentase
ekuitas per trade.

## ⚠️ Disclaimer

Tidak ada strategi trading yang menjamin profit. Bot ini dirancang dengan
manajemen risiko yang disiplin (lihat di bawah), tapi kerugian tetap
mungkin terjadi, termasuk melebihi ekspektasi dalam kondisi pasar
ekstrem (flash crash, gap, masalah likuiditas exchange). Jangan gunakan
dana yang tidak sanggup kamu relakan. Selalu mulai dari dry-run →
testnet → live dengan modal kecil.

## Strategi: `TrendFollowingStrategy`

- **Timeframe:** 4h (mengurangi noise & overtrading dibanding timeframe kecil)
- **Regime tren:** kondisi berkelanjutan EMA20>EMA50, harga di atas/bawah
  EMA200, dan ADX > 25 (memastikan pasar sedang trending, bukan sideways)
- **Entry trigger** (dua jenis, keduanya harus dalam regime tren yang sama):
  1. **Fresh cross** — EMA20 baru saja cross EMA50
  2. **Pullback resume** — harga masih dalam tren yang sudah berjalan,
     RSI sempat turun ke area netral lalu naik lagi (indikasi pullback
     selesai, tren lanjut)

  Pemisahan ini sengaja dilakukan supaya satu tren yang sama bisa
  menghasilkan lebih dari satu trade (tidak cuma sekali di titik cross
  persis), karena filter ADX+RSI+EMA-cross yang harus align di candle
  yang sama menghasilkan sinyal yang sangat jarang (Freqtrade backtest
  awal: cuma ~14 trade dalam 8 bulan — sample terlalu kecil untuk
  disimpulkan apa pun secara statistik).
- **Exit:** EMA cross balik arah, trailing stop, ATR-based stoploss, atau
  ROI bertingkat berdasarkan lama posisi terbuka
- **Arah:** long & short (futures), leverage dibatasi maksimum 3x
- **Universe pair:** dinamis, top-15 pair by volume (`VolumePairList`),
  bukan 4 pair statis — supaya peluang trade lebih banyak & terdiversifikasi

## Manajemen risiko

- **Risk per trade:** default 1.5% dari total ekuitas akun, dihitung ulang
  setiap entry berdasarkan jarak stoploss (ATR) dan leverage yang dipakai
  — bukan persentase modal tetap, jadi ukuran posisi otomatis mengecil
  saat volatilitas naik.
- **Max open trades:** 3 posisi bersamaan → eksposur risiko agregat
  maksimum ~4.5% dari ekuitas dalam kondisi terburuk (semua kena stoploss).
- **Proteksi otomatis** (`protections` di strategi):
  - `CooldownPeriod` — jeda setelah setiap trade ditutup
  - `StoplossGuard` — bot berhenti trading sementara jika 3 stoploss kena
    dalam 24 candle terakhir
  - `MaxDrawdown` — bot berhenti sementara jika drawdown melebihi 10%
    dalam periode lookback
- **Leverage rendah** (≤3x) untuk membatasi risiko likuidasi.

Semua parameter ini bisa diubah di `user_data/strategies/TrendFollowingStrategy.py`
(atribut `risk_per_trade`, `max_leverage`, `adx_threshold`, dst.) dan di
`user_data/config.json` (`max_open_trades`, `pair_whitelist`, dll).

## Tahapan penggunaan (WAJIB berurutan)

### 1. Backtest

```bash
docker compose run --rm freqtrade download-data \
  --config user_data/config.json --timerange 20230101- --timeframe 4h

docker compose run --rm freqtrade backtesting \
  --config user_data/config.json --strategy TrendFollowingStrategy \
  --timerange 20230101-
```

Evaluasi hasil: win rate, profit factor, max drawdown, jumlah trade.
Jangan lanjut ke tahap berikut kalau hasil backtest tidak masuk akal.

### 2. Dry-run (paper trading, default saat ini)

`user_data/config.json` sudah diset `"dry_run": true` — bot jalan dengan
harga real-time tapi order simulasi, saldo virtual (`dry_run_wallet`).
**Tidak butuh API key sama sekali** di tahap ini.

```bash
cp .env.example .env
docker compose up -d
docker compose logs -f
```

Biarkan jalan minimal beberapa minggu untuk validasi strategi di kondisi
pasar riil sebelum lanjut ke uang sungguhan.

### 3. Binance Futures Testnet

Setelah dry-run meyakinkan, lanjut ke testnet (masih uang virtual, tapi
lewat API Binance beneran) — lihat instruksi di `.env.example`.

### 4. Live trading (modal kecil dulu)

Ubah `"dry_run": false` di `user_data/config.json`, isi `.env` dengan
API key Binance **live** yang:
- Izin **hanya** untuk trading futures (Enable Futures), **JANGAN**
  aktifkan izin withdraw
- Idealnya IP-whitelisted ke IP server tempat bot jalan

Mulai dengan modal kecil yang siap kamu relakan sebagai biaya
pembelajaran, pantau minimal beberapa minggu, baru pertimbangkan
menambah modal.

## Versi Pine Script (untuk test visual di TradingView)

File `pine/TrendFollowingStrategy.pine` berisi logika yang sama (EMA
cross + filter ADX/RSI, ATR stoploss, position sizing berbasis risk %)
untuk divalidasi visual di TradingView.

**Cara pakai (TradingView tidak bisa "install" script dari GitHub —
harus copy-paste manual ke Pine Editor):**

1. Buka [tradingview.com](https://www.tradingview.com), buka chart pair
   yang mau ditest (mis. BTCUSDT, timeframe 4h agar sesuai strategi).
2. Buka tab **Pine Editor** di panel bawah.
3. Hapus template default, copy seluruh isi `pine/TrendFollowingStrategy.pine`
   dari repo ini, paste ke editor.
4. Klik **Add to Chart**. Lalu buka tab **Strategy Tester** di panel bawah
   untuk lihat hasil backtest (win rate, profit factor, drawdown, dll).

**Penting:** versi Pine ini jalan di data spot chart TradingView dan
**tidak mensimulasikan leverage/funding rate/likuidasi futures** —
gunakan untuk cek visual timing entry/exit saja, bukan pengganti hasil
backtest Freqtrade di atas (yang mensimulasikan futures secara akurat).
Kalau ingin strategi Pine ini eksekusi otomatis ke Binance, butuh
langganan TradingView berbayar (untuk webhook alert) + bridge pihak
ketiga (mis. 3Commas/WunderTrading) — ini jalur terpisah dari bot
Freqtrade di atas, punya delay lebih tinggi dan bergantung uptime pihak
ketiga, jadi **tidak direkomendasikan** dibanding bot Freqtrade untuk
eksekusi live.

## Menjalankan

```bash
docker compose up -d        # start bot
docker compose logs -f      # lihat log real-time
docker compose down         # stop bot
```

Aktifkan notifikasi Telegram (opsional tapi disarankan) lewat variabel
`FREQTRADE__TELEGRAM__*` di `.env` agar kamu dapat notifikasi tiap kali
bot entry/exit posisi, dan bisa cek status dari HP.

## Struktur

```
user_data/
  config.json                          # konfigurasi exchange, pair, risk limits
  strategies/TrendFollowingStrategy.py # logika entry/exit & position sizing
docker-compose.yml
.env.example                           # template API key (jangan commit .env asli)
```
