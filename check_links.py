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
from dotenv import load_dotenv
load_dotenv()
from db import get_all_products_for_link_check, mark_link_checked, init_db

init_db()  # broken_reason gibi yeni kolonlarin var oldugundan emin olur

TIMEOUT = 8
SLEEP_BETWEEN = 0.5  # hedef sitelere yuklenmemek icin
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}


def check_url(url: str):
    """
    URL erisilebilir mi? Donen: (is_up: bool, reason: str)
    reason bos string ise calisiyor demektir; degilse kirik nedeni:
    '404', 'ssl_error', 'dns_error', 'timeout', 'connection_error', 'diger'
    Gecici ag/DNS hatalarina karsi 1 kez daha dener (false positive azaltmak icin).
    """
    if not url:
        return False, "url_yok"

    last_reason = "diger"
    for attempt in range(2):
        try:
            resp = requests.head(url, timeout=TIMEOUT, allow_redirects=True, headers=HEADERS)
            if resp.status_code >= 400:
                # Bazi siteler HEAD'i desteklemiyor veya bot engeli koyuyor, GET ile tekrar dene
                resp = requests.get(url, timeout=TIMEOUT, allow_redirects=True, headers=HEADERS)
            # 403/999/429 gibi kodlar cogunlukla bot-engelleme (Cloudflare vb.), gercek kirik degil.
            if resp.status_code in (403, 999, 429):
                return True, ""
            if resp.status_code < 400:
                return True, ""
            return False, str(resp.status_code)
        except requests.exceptions.SSLError:
            last_reason = "ssl_error"
        except requests.exceptions.ConnectionError as e:
            # DNS cozulemedi mi (NXDOMAIN, "Name or service not known" vb.) yoksa baska
            # bir baglanti hatasi mi oldugunu ayirt etmeye calisir - raporlama netligi icin.
            msg = str(e).lower()
            if "name or service not known" in msg or "getaddrinfo failed" in msg or "nodename nor servname" in msg:
                last_reason = "dns_error"
            else:
                last_reason = "connection_error"
        except requests.exceptions.Timeout:
            last_reason = "timeout"
        except requests.RequestException:
            last_reason = "diger"

        if attempt == 0:
            time.sleep(2)  # gecici hata olabilir, kisa bekleyip tekrar dene
            continue
    return False, last_reason


def run(limit=None):
    products = get_all_products_for_link_check()
    if limit:
        products = products[:limit]

    broken, ok, recovered = 0, 0, 0
    reason_counts = {}
    for p in products:
        website = p.get("website") or p.get("ph_url")
        was_broken = bool(p.get("is_broken"))
        is_up, reason = check_url(website)
        mark_link_checked(p["id"], is_broken=not is_up, reason=reason)
        if is_up:
            ok += 1
            if was_broken:
                recovered += 1
                print(f"  [DUZELDI] {p['title_tr']} -> {website}")
        else:
            broken += 1
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            print(f"  [KIRIK: {reason}] {p['title_tr']} -> {website}")
        time.sleep(SLEEP_BETWEEN)

    print(f"\nTamamlandi. Calisan: {ok}, Kirik: {broken}, Duzelen: {recovered}, Toplam: {len(products)}")
    if reason_counts:
        print("Kirik nedenleri dagilimi:", reason_counts)


if __name__ == "__main__":
    lim = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        lim = int(sys.argv[idx + 1])
    run(limit=lim)
