# -*- coding: utf-8 -*-
"""
Favicon yerine, mumkun oldugunda websitenin kendi og:image / twitter:image
meta etiketinden gercek urun gorseli (screenshot/banner) ceker.
Sadece su an favicon URL'i tasiyan urunler icin calisir (google.com/s2/favicons).
Basarisiz olursa (og:image yok, site erisilemedi vb.) favicon oldugu gibi kalir.

Kullanim: python backfill_og_image.py
"""
import re
import time
import requests
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

OG_IMAGE_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']', re.I),
]


def find_og_image(website: str) -> str | None:
    try:
        resp = requests.get(website, headers=HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code != 200:
            return None
        html = resp.text[:200000]  # ilk 200kb yeterli, head genelde basta
        for pattern in OG_IMAGE_PATTERNS:
            m = pattern.search(html)
            if m:
                img_url = m.group(1).strip()
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    img_url = urljoin(resp.url, img_url)
                if img_url.startswith("http"):
                    return img_url
        return None
    except Exception:
        return None


def main():
    from db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, original_name, website, thumbnail FROM products "
        "WHERE thumbnail LIKE ? AND website IS NOT NULL AND website != ''",
        ("%google.com/s2/favicons%",)
    ).fetchall()
    rows = [dict(r) for r in rows]
    print(f"{len(rows)} urun favicon kullaniyor, og:image ile yukseltilmeye calisilacak.")

    upgraded, kept_favicon, failed = 0, 0, 0
    for i, r in enumerate(rows):
        og = find_og_image(r["website"])
        if og:
            conn.execute("UPDATE products SET thumbnail = ? WHERE id = ?", (og, r["id"]))
            upgraded += 1
            print(f"[{i}] YUKSELTILDI: {r['original_name']} -> {og[:70]}")
        else:
            kept_favicon += 1
            print(f"[{i}] favicon'da kaldi: {r['original_name']}")
        if (i + 1) % 20 == 0:
            conn.commit()
        time.sleep(0.3)

    conn.commit()
    conn.close()
    print(f"\nBitti. Yukseltilen: {upgraded}, Favicon'da kalan: {kept_favicon}")


if __name__ == "__main__":
    main()
