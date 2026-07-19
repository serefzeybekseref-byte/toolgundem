# -*- coding: utf-8 -*-
"""
Thumbnail'i olmayan (genelde Product Hunt pipeline'i disinda elle eklenen
bilinen araclar - GitHub Copilot, Cursor, Claude Code vb.) urunler icin
website adresinden otomatik logo cekip thumbnail alanini doldurur.

Google Favicon servisini kullanir (ucretsiz, key gerektirmez): google.com/s2/favicons
NOT: Clearbit Logo API 8 Aralik 2025'te tamamen kapandi (HubSpot devralmasi sonrasi),
onu kullanan her yerde kirik gorsel donerdi - bu yuzden Google'in kendi favicon
servisi tercih edildi (kucuk ama guvenilir ve stabil).

Kullanim: python backfill_thumbnails.py
"""
import re
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


def domain_from_url(url: str) -> str | None:
    if not url:
        return None
    try:
        netloc = urlparse(url).netloc or urlparse("https://" + url).netloc
        netloc = netloc.replace("www.", "")
        return netloc or None
    except Exception:
        return None


def main():
    from db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, slug, website FROM products WHERE (thumbnail IS NULL OR thumbnail = '') AND website IS NOT NULL AND website != ''"
    ).fetchall()

    updated = 0
    for r in rows:
        r = dict(r)
        domain = domain_from_url(r["website"])
        if not domain:
            continue
        logo_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
        conn.execute("UPDATE products SET thumbnail = ? WHERE id = ?", (logo_url, r["id"]))
        updated += 1

    conn.commit()
    conn.close()
    print(f"Tamamlandi. {updated} urune Google favicon URL'i atandi.")


if __name__ == "__main__":
    main()
