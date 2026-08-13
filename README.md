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
- **Entry:** EMA20 cross EMA50 searah tren utama (EMA200), dikonfirmasi
  ADX > 25 (memastikan pasar sedang trending, bukan sideways) dan filter
  RSI (menghindari entry di kondisi jenuh beli/jual)
- **Exit:** EMA cross balik arah, trailing stop, ATR-based stoploss, atau
  ROI bertingkat berdasarkan lama posisi terbuka
- **Arah:** long & short (futures), leverage dibatasi maksimum 3x

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
