# -*- coding: utf-8 -*-
"""
Kesin kirik (is_broken=1) urunler icin NIM+web aramasiyla olasi yeni/guncel bir
website URL'si arar. OTOMATIK UYGULAMAZ - sadece url_repair_suggestions tablosuna
oneri olarak ekler, admin panelden tek tikla onaylanip uygulanir.

Neden otomatik degil: bir URL'yi yanlis degistirmek, kirik link birakmaktan daha
kotu bir sonuc olabilir (kullaniciyi tamamen alakasiz/yanlis bir siteye gonderme
riski). Bu yuzden bu, projenin "kor otomasyon almayalim" prensibiyle bilerek
insan-onayli tutuluyor (bkz. karsilastirma "hangisi daha iyi" yargilari, comparison
freshness Issue-only akisi).

Kapsam: is_broken=1 olan TUM urunler (hem '404' hem 'connection_error' - ikisi de
zaten check_links.py/verify_connection_errors.py tarafindan bu noktaya kadar
elenmis, yani burada gercekten kirik olduklarina makul olcude eminiz).
"""
import re
from dotenv import load_dotenv
load_dotenv()

from db import get_connection, init_db, add_url_repair_suggestion
from nim_tools import call_nim_with_search

SUGGEST_PROMPT = """"{name}" adinda bir yazilim/AI araci var. Eski/kirik website adresi: {old_website}

web_search aracini kullanarak bu urunun GUNCEL, DOGRU calisan resmi web sitesini bul.
Sirket adres degistirmis, yeniden markalanmis (rebrand) veya baska bir sirkete
katilmis (acquisition) olabilir. Eger boyle bir gecerli, guncel URL buluyorsan onu ver.
Emin degilsen veya bulamiyorsan "YOK" yaz - kesinlikle URL uydurma.

SADECE su formatta cevap ver:
URL: (bulunan tam URL, veya YOK)
SEBEP: (tek cumle, neden bu URL'yi onerdigin)
"""


def find_new_url(name: str, old_website: str) -> dict:
    prompt = SUGGEST_PROMPT.format(name=name, old_website=old_website or "bilinmiyor")
    response = call_nim_with_search(prompt, max_tokens=200)
    url_match = re.search(r"URL:\s*(\S+)", response)
    reason_match = re.search(r"SEBEP:\s*(.+)", response)
    url = url_match.group(1).strip() if url_match else "YOK"
    reason = reason_match.group(1).strip() if reason_match else response[:200]
    return {"url": url, "reason": reason}


def _looks_like_real_url(url: str) -> bool:
    if not url or url.upper() == "YOK":
        return False
    return url.startswith("http://") or url.startswith("https://")


def _url_resolves(url: str) -> bool:
    """Onerilen URL gercekten acilyor mu (200 donuyor mu) diye HEAD ile kontrol eder."""
    import requests
    try:
        resp = requests.head(url, timeout=8, allow_redirects=True)
        if resp.status_code == 200:
            return True
        resp = requests.get(url, timeout=8, allow_redirects=True, stream=True)
        return resp.status_code == 200
    except Exception:
        return False


def run():
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, original_name, website FROM products WHERE is_broken = 1"
    ).fetchall()
    conn.close()

    print(f"{len(rows)} kirik urun icin yeni URL aranacak.\n")
    suggested, no_match, skipped = 0, 0, 0

    for r in rows:
        d = dict(r)
        print(f"[{d['original_name']}] eski: {d['website']}")
        try:
            result = find_new_url(d["original_name"], d["website"])
        except Exception as e:
            print(f"  HATA: {e}")
            skipped += 1
            continue

        new_url = result["url"]
        if not _looks_like_real_url(new_url):
            print(f"  -> Uygun yeni URL bulunamadi. ({result['reason']})")
            no_match += 1
            continue

        if new_url.rstrip("/").lower() == (d["website"] or "").rstrip("/").lower():
            print("  -> Onerilen URL eskisiyle ayni, atlaniyor.")
            no_match += 1
            continue

        if not _url_resolves(new_url):
            print(f"  -> Onerilen URL ({new_url}) gercekte acilmiyor, guvenlik icin oneri eklenmiyor.")
            no_match += 1
            continue

        add_url_repair_suggestion(d["id"], d["website"], new_url, result["reason"])
        print(f"  -> ONERI EKLENDI: {new_url} ({result['reason']})")
        suggested += 1

    print(f"\nSonuc: {suggested} yeni oneri eklendi, {no_match} icin uygun URL bulunamadi, {skipped} hata.")
    return {"suggested": suggested, "no_match": no_match, "skipped": skipped}


if __name__ == "__main__":
    run()
