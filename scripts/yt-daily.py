#!/usr/bin/env python3
"""Toolkuy YouTube daily stats -> Discord.

Zero-LLM: dijalankan oleh system crontab, bukan oleh agent.
Sumber data publik (tanpa API key):
  - RSS feed kanal  : views per video
  - halaman kanal   : subscriber + jumlah video
Token Discord dibaca dari ~/.opencrabs/keys.toml saat runtime, tidak pernah di-print.

Exit code selalu 0 kalau sudah berhasil mengirim pesan (termasuk PARTIAL),
supaya cron tidak mengirim email error tiap pagi.
"""
import json
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

CHANNEL_ID = "UCsLiavPrL8IgWd6SeD4Uidg"
HANDLE = "toolkuycom"
DISCORD_CHANNEL = os.environ.get("DISCORD_CHANNEL_ID") or "1555442032355577877"  # #🏠-toolkuy
HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, ".opencrabs", "projects", "yt-brand")
STATS_DIR = os.environ.get("YT_STATS_DIR") or os.path.join(BASE, "stats")
LOG_DIR = os.environ.get("YT_LOG_DIR") or os.path.join(BASE, "logs")
LAST = os.path.join(STATS_DIR, "last.json")
LOG = os.path.join(LOG_DIR, "yt-daily.log")
WIB = timezone(timedelta(hours=7))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
DRY = "--dry-run" in sys.argv


def now_wib():
    return datetime.now(WIB)


def log(msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    line = f"[{now_wib():%Y-%m-%d %H:%M:%S} WIB] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def fetch(url, tries=3):
    """GET dengan retry + backoff. Raise kalau semua percobaan gagal."""
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=25) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - transient apa pun di-retry
            last_err = exc
            log(f"fetch attempt {attempt}/{tries} gagal: {type(exc).__name__}: {exc}")
            if attempt < tries:
                time.sleep(5 * attempt)
    raise RuntimeError(f"fetch gagal setelah {tries} percobaan: {last_err}")


def parse_count(text):
    """'1,2 rb pelanggan' / '1.2K subscribers' -> int. None kalau tak terbaca."""
    m = re.search(r"([\d.,]+)\s*([KMkm]|rb|jt|jt\.)?", text)
    if not m:
        return None
    suffix = (m.group(2) or "").lower()
    if suffix:
        # "1.2K" / "1,2 rb" -> koma dianggap desimal
        raw = m.group(1).replace(",", ".")
    else:
        # "1,234" / "1.234" -> pemisah ribuan dibuang
        raw = m.group(1).replace(",", "").replace(".", "")
    try:
        val = float(raw)
    except ValueError:
        return None
    mult = {"k": 1e3, "rb": 1e3, "m": 1e6, "jt": 1e6}.get(suffix, 1)
    return int(round(val * mult))


def parse_rss(xml):
    items = []
    for block in re.findall(r"<entry>.*?</entry>", xml, re.S):
        vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", block)
        title = re.search(r"<title>([^<]+)</title>", block)
        pub = re.search(r"<published>([^<]+)</published>", block)
        views = re.search(r'views="(\d+)"', block)
        if not vid:
            continue
        items.append({
            "id": vid.group(1),
            "title": (title.group(1).strip() if title else "(tanpa judul)"),
            "published": pub.group(1) if pub else "",
            "views": int(views.group(1)) if views else 0,
        })
    return items


def parse_channel(html):
    subs = None
    vids = None
    m = re.search(r'"content":"([^"]*?(?:subscriber|pelanggan)[^"]*)"', html, re.I)
    if m:
        subs = parse_count(m.group(1))
    if subs is None:
        if re.search(r"(No subscribers|Tidak ada pelanggan|Belum ada pelanggan)", html, re.I):
            subs = 0
    m = re.search(r'"content":"([\d.,]+)\s*videos?"', html, re.I)
    if m:
        vids = parse_count(m.group(1))
    return subs, vids


def fmt_delta(cur, prev, unit=""):
    if prev is None:
        return "baru"
    d = cur - prev
    if d > 0:
        return f"+{d}{unit}"
    if d < 0:
        return f"{d}{unit}"
    return f"0{unit}"


def post_discord(content):
    if DRY:
        log("DRY-RUN, pesan tidak dikirim:")
        print("-" * 60)
        print(content)
        print("-" * 60)
        return True
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        with open(os.path.join(HOME, ".opencrabs", "keys.toml"), "rb") as fh:
            token = tomllib.load(fh)["channels"]["discord"]["token"]
    payload = json.dumps({"content": content[:1990],
                          "allowed_mentions": {"parse": []}}).encode()
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL}/messages",
        data=payload, method="POST",
        headers={"Authorization": "Bot " + token,
                 "Content-Type": "application/json",
                 "User-Agent": "DiscordBot (opencrabs-yt-daily,1.0)"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        body = json.load(resp)
    log(f"discord OK, message id {body.get('id')}")
    return True


def main():
    os.makedirs(STATS_DIR, exist_ok=True)
    stamp = now_wib()
    bulan = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    header = (f"📊 **Toolkuy YouTube** — {stamp.day} {bulan[stamp.month - 1]} {stamp.year} "
              f"{stamp:%H:%M} WIB")

    try:
        rss = fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}")
    except Exception as exc:  # noqa: BLE001
        log(f"PARTIAL: {exc}")
        post_discord(
            f"{header}\n\n⚠️ PARTIAL — gagal ambil data dari YouTube setelah retry.\n"
            f"Error: `{type(exc).__name__}`\nAngka di pesan ini tidak ada, bukan nol."
        )
        return 0

    items = parse_rss(rss)

    # Halaman kanal: sebagian IP (runner CI) dilayani varian ringan tanpa
    # metadata subscriber. Coba beberapa bentuk URL, pakai yang berisi angka.
    html = ""
    subs = vid_count = None
    for variant in (
        f"https://www.youtube.com/@{HANDLE}?hl=en&gl=US",
        f"https://www.youtube.com/@{HANDLE}",
        f"https://www.youtube.com/@{HANDLE}/about?hl=en&gl=US",
    ):
        try:
            cand = fetch(variant)
        except Exception as exc:  # noqa: BLE001
            log(f"varian gagal: {variant}: {type(exc).__name__}")
            continue
        if not html:
            html = cand
        got_subs, got_vids = parse_channel(cand)
        if got_subs is not None:
            html, subs, vid_count = cand, got_subs, got_vids
            log(f"halaman kanal terbaca dari varian: {variant}")
            break
    if subs is None or vid_count is None:
        # Observability: kalau halaman kanal tidak terbaca, catat kenapa.
        # Tanpa ini, "tidak terbaca" cuma tebakan.
        log(f"DIAG subs={subs} vids={vid_count} html_len={len(html)} "
            f"consent={'consent' in html.lower()} "
            f"sub_word={bool(re.search(r'subscriber|pelanggan', html, re.I))} "
            f"video_ctx={re.findall(r'\"content\":\"([^\"]{0,24}video[^\"]{0,12})\"', html, re.I)[:3]}")
    total_views = sum(i["views"] for i in items)

    prev = None
    if os.path.exists(LAST):
        try:
            with open(LAST, encoding="utf-8") as fh:
                prev = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            log(f"snapshot lama tidak terbaca, delta dilewati: {exc}")

    prev_items = (prev or {}).get("items", {})
    prev_views = (prev or {}).get("total_views")

    lines = [header, ""]
    if subs is None:
        lines.append("👥 Subscriber: tidak terbaca")
    else:
        lines.append(f"👥 Subscriber: **{subs}** ({fmt_delta(subs, (prev or {}).get('subs'))} sejak kemarin)")
    lines.append(f"👁 Total views (video di feed): **{total_views}** "
                 f"({fmt_delta(total_views, prev_views)})")
    if vid_count is not None:
        lines.append(f"🎬 Jumlah video: **{vid_count}**")

    if items:
        lines.append("")
        lines.append("Per video:")
        for it in items[:8]:
            before = prev_items.get(it["id"], {}).get("views")
            delta = fmt_delta(it["views"], before)
            title = it["title"] if len(it["title"]) <= 70 else it["title"][:67] + "..."
            lines.append(f"• `{it['views']}` views ({delta}) — {title}")
    else:
        lines.append("")
        lines.append("Belum ada video di feed.")

    lines.append("")
    lines.append(f"<https://www.youtube.com/@{HANDLE}>")
    content = "\n".join(lines)

    snap = {
        "ts": stamp.isoformat(),
        "subs": subs,
        "videos": vid_count,
        "total_views": total_views,
        "items": {i["id"]: {"title": i["title"], "views": i["views"],
                            "published": i["published"]} for i in items},
    }
    with open(os.path.join(STATS_DIR, f"{stamp:%Y-%m-%d}.json"), "w", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=2)
    if not DRY:
        with open(LAST, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False, indent=2)
        with open(os.path.join(STATS_DIR, "stats.csv"), "a", encoding="utf-8") as fh:
            fh.write(f"{stamp:%Y-%m-%d %H:%M},{subs},{vid_count},{total_views}\n")

    log(f"subs={subs} videos={vid_count} total_views={total_views} items={len(items)}")
    post_discord(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
