"""
AŞAMA 8: Veritabanindaki urunlerin website linklerini periyodik olarak kontrol eder.
Kirik/olu linkleri (404, timeout, DNS hatasi vb.) isaretler.
GitHub Actions ile haftalik calistirilmasi onerilir (bkz. .github/workflows/check-links.yml).

Kullanim:
    python check_links.py            -> tum urunleri kontrol eder
    python check_links.py --limit 20 -> ilk 20 urunle sinirlar (test icin)
"""
import sys
import time
import requests
from db import get_all_products, mark_link_checked

TIMEOUT = 8
SLEEP_BETWEEN = 0.5  # hedef sitelere yuklenmemek icin
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}


def check_url(url: str) -> bool:
    """URL erisilebilir mi? True = calisiyor, False = kirik/erisilemiyor.
    Gecici ag/DNS hatalarina karsi 1 kez daha dener (false positive azaltmak icin)."""
    if not url:
        return False
    for attempt in range(2):
        try:
            resp = requests.head(url, timeout=TIMEOUT, allow_redirects=True, headers=HEADERS)
            if resp.status_code >= 400:
                # Bazi siteler HEAD'i desteklemiyor veya bot engeli koyuyor, GET ile tekrar dene
                resp = requests.get(url, timeout=TIMEOUT, allow_redirects=True, headers=HEADERS)
            # 403/999/429 gibi kodlar cogunlukla bot-engelleme (Cloudflare vb.), gercek kirik degil.
            if resp.status_code in (403, 999, 429):
                return True
            return resp.status_code < 400
        except requests.RequestException:
            if attempt == 0:
                time.sleep(2)  # gecici hata olabilir, kisa bekleyip tekrar dene
                continue
            return False
    return False


def run(limit=None):
    products = get_all_products()
    if limit:
        products = products[:limit]

    broken, ok = 0, 0
    for p in products:
        website = p.get("website") or p.get("ph_url")
        is_up = check_url(website)
        mark_link_checked(p["id"], is_broken=not is_up)
        if is_up:
            ok += 1
        else:
            broken += 1
            print(f"  [KIRIK] {p['title_tr']} -> {website}")
        time.sleep(SLEEP_BETWEEN)

    print(f"\nTamamlandi. Calisan: {ok}, Kirik: {broken}, Toplam: {len(products)}")


if __name__ == "__main__":
    lim = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        lim = int(sys.argv[idx + 1])
    run(limit=lim)
