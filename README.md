# toolkuy-stats

Statistik harian kanal YouTube **[@toolkuycom](https://www.youtube.com/@toolkuycom)**, dikirim otomatis ke Discord setiap pagi.

Jalan di GitHub Actions, bukan di laptop: laptop mati pun laporan tetap masuk.

| Item | Nilai |
|---|---|
| Jadwal | `0 0 * * *` UTC = **07:00 WIB** |
| Script | `scripts/yt-daily.py` (Python stdlib, zero dependency) |
| Tujuan | Discord `#🏠-toolkuy` |
| Secret | `DISCORD_BOT_TOKEN` |
| State | `stats/` (di-commit tiap hari, dipakai hitung delta) |

## Data yang diambil

Semua dari endpoint publik, tanpa API key:

- **RSS feed kanal** (`youtube.com/feeds/videos.xml`) untuk views per video
- **Halaman kanal** (`youtube.com/@toolkuycom`) untuk subscriber dan jumlah video

## Batas data

Yang **tidak** ada di sini, karena butuh YouTube Data API / Analytics API + OAuth:

- total views lifetime kanal (angka di laporan = jumlah views video yang ada di feed, maksimal 15 terbaru)
- watch time, rata-rata durasi tonton, retensi
- sumber traffic, jam tayang penonton
- subscriber gain/loss harian (yang dilaporkan cuma selisih stok)

## Menjalankan manual

```bash
DISCORD_BOT_TOKEN=... python3 scripts/yt-daily.py --dry-run   # cetak saja
```

Atau lewat tab Actions → *YouTube daily stats* → **Run workflow**.

## Catatan operasional

- Repo ini **publik** karena Actions di repo privat kena blokir billing. Isi repo tidak berisi rahasia; token Discord disimpan sebagai secret.
- Commit harian di `stats/` adalah heartbeat repo. Kalau repo diam 60 hari, GitHub mematikan jadwalnya otomatis.
- Kalau YouTube sedang error, script tetap mengirim pesan **PARTIAL** yang menyatakan angka tidak tersedia, bukan nol.
