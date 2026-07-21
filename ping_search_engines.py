# -*- coding: utf-8 -*-
"""
Arama motorlarina yeni/guncellenen sayfalari bildirir.

Onemli not (21 Temmuz 2026 arastirmasi): Hem Google'in ("google.com/ping?sitemap=")
HEM DE Bing'in ("bing.com/ping?sitemap=") klasik sitemap ping endpoint'leri
KALICI OLARAK KALDIRILDI (Google 2023 sonunda 404 vermeye basladi; Bing ise
cok daha once, 2021'de 410 vermeye basladi - test ettigimizde dogruladik).
Bu yuzden burada KULLANILMIYOR.

Google'a gercek anlik bildirim ancak Search Console + Indexing API (OAuth
service account gerektirir) ile mumkun - bu ayri, daha buyuk bir kurulum.

Bunun yerine: IndexNow protokolu (Bing + Yandex tarafindan resmi olarak
desteklenir) ile YENI/GUNCELLENEN tekil URL'ler anlik bildirilir.

Kullanim:
    python ping_search_engines.py            -> son 24 saatteki degisiklikleri bildirir
    python ping_search_engines.py --hours 48 -> son 48 saat
"""
import sys
import argparse
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv()

from db import get_connection, init_db

INDEXNOW_KEY = "d4c153c71d2d2321087ed549ff32eb7c"
SITE_HOST = "bulurumai.com"
BASE_URL = f"https://{SITE_HOST}"
KEY_LOCATION = f"{BASE_URL}/{INDEXNOW_KEY}.txt"


def submit_indexnow(urls: list):
    """IndexNow protokolu ile tekil URL listesini gonderir (tek seferde en fazla 10.000 URL)."""
    if not urls:
        print("[IndexNow] Bildirilecek yeni/guncellenen URL yok.")
        return True
    payload = {
        "host": SITE_HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls,
    }
    try:
        resp = requests.post(
            "https://api.indexnow.org/indexnow",
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=15,
        )
        # IndexNow basarili istekte 200 veya 202 doner.
        ok = resp.status_code in (200, 202)
        print(f"[IndexNow] {len(urls)} URL gonderildi, status={resp.status_code} {'OK' if ok else ''}")
        return ok
    except Exception as e:
        print(f"[IndexNow] HATA: {e}")
        return False


def get_recent_urls(since_hours: int = 24) -> list:
    """Son X saatte olusturulan/guncellenen urun, rehber ve karsilastirma URL'lerini toplar."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    conn = get_connection()
    urls = []

    products = conn.execute(
        "SELECT slug FROM products WHERE created_at >= ? AND (is_broken IS NULL OR is_broken = 0)",
        (cutoff,)
    ).fetchall()
    urls += [f"{BASE_URL}/urun/{dict(r)['slug']}" for r in products]

    guides = conn.execute(
        "SELECT slug FROM guides WHERE updated_at >= ?", (cutoff,)
    ).fetchall()
    urls += [f"{BASE_URL}/rehber/{dict(r)['slug']}" for r in guides]

    comparisons = conn.execute(
        "SELECT slug FROM comparisons WHERE updated_at >= ?", (cutoff,)
    ).fetchall()
    urls += [f"{BASE_URL}/karsilastirma/{dict(r)['slug']}" for r in comparisons]

    conn.close()
    return urls


def run(since_hours: int = 24):
    init_db()
    print(f"=== IndexNow Bildirimi (son {since_hours} saat) ===")
    urls = get_recent_urls(since_hours)
    for u in urls:
        print(f"  -> {u}")
    submit_indexnow(urls)
    print("=== Tamamlandi ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()
    run(since_hours=args.hours)
