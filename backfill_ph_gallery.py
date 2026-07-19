# -*- coding: utf-8 -*-
"""
Elle eklenen (manual-) urunler icin gercek Product Hunt sayfasini bulup
gercek galeri (media) gorsellerini ceker. Runway-tarzi yanlis eslesmeyi
onlemek icin PH'nin dondurdugu website alani, bizim kayitli website'imizle
(domain bazinda) KARSILASTIRILIR - eslesmezse aday reddedilir.
"""
import os
import re
import time
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv()

from db import get_connection, slugify

TOKEN = os.getenv("PRODUCTHUNT_TOKEN")
API_URL = "https://api.producthunt.com/v2/api/graphql"

# PH'de ayni isimle FARKLI, alakasiz urunlerin de var oldugu bilinen durumlar
# (ornek: "Runway" hem video AI hem de alakasiz bir ise-alim araci olarak
# ayri ayri listelenmis). Bu isimler icin otomatik eslestirme YAPILMAZ,
# mevcut dogru (elle dogrulanmis) veri korunur.
KNOWN_AMBIGUOUS_NAMES = {"runway"}

QUERY = """
query($slug: String) {
  post(slug: $slug) {
    name
    website
    thumbnail { url }
    media { url type }
  }
}
"""


def domain_of(url: str) -> str:
    if not url:
        return ""
    try:
        d = urlparse(url if "://" in url else "https://" + url).netloc
        return d.lower().replace("www.", "")
    except Exception:
        return ""


def slug_candidates(name: str) -> list:
    """Bir urun adindan olasi PH slug adaylarini uretir (siralamaya gore denenir).
    Rate limit tasarrufu icin sadece en olasi 1-2 aday denenir."""
    cands = []
    base = slugify(name)
    cands.append(base)
    # Parantez icini ayirip ana ismi kullan: "Canva AI (Magic Studio)" -> "canva-ai"
    paren_match = re.search(r"^(.*?)\s*\([^)]+\)\s*$", name)
    if paren_match:
        cands.append(slugify(paren_match.group(1)))
    # "X by Y" -> "X"
    by_match = re.search(r"^(.*?)\s+by\s+", name, re.I)
    if by_match:
        cands.append(slugify(by_match.group(1)))
    seen = set()
    result = []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result[:2]  # rate limit icin en fazla 2 aday


def try_match(name: str, our_website: str):
    """
    Aday slug'lari sirayla dener. PH'nin 'website' alani kendi tracking
    linkini dondurdugu icin (gercek domain degil) domain karsilastirmasi
    GUVENILMEZ - onun yerine PH'nin dondurdugu urun ADI bizim kayitli
    isimle TAM (buyuk/kucuk harf duyarsiz) eslesiyor mu kontrol edilir.
    Bu, Runway-tarzi ayni-isim-farkli-urun riskini tamamen ortadan
    kaldirmaz (ayni isimli iki farkli urun varsa ikisi de "eslesir"),
    ama slug'in kendisi zaten urunun tam adindan uretildigi icin risk
    dusuktur. Sonuc listesi ayrica manuel/gozle kontrol icin loglanir.
    """
    our_name_norm = name.strip().lower()
    headers = {"Authorization": f"Bearer {TOKEN}"}

    for slug in slug_candidates(name):
        try:
            resp = requests.post(API_URL, json={"query": QUERY, "variables": {"slug": slug}}, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue
        if data.get("errors"):
            err = data["errors"][0].get("error", "")
            if err == "rate_limit_reached":
                print("!! RATE LIMIT - script durduruluyor, birazdan tekrar calistirin.")
                raise SystemExit(1)
            continue
        post = (data.get("data") or {}).get("post")
        if not post:
            continue
        ph_name_norm = (post.get("name") or "").strip().lower()
        if ph_name_norm != our_name_norm:
            continue  # isim tam eslesmiyor -> farkli urun olabilir, ATLA
        images = [m["url"] for m in (post.get("media") or []) if m.get("type") == "image"]
        if not images:
            continue
        return {
            "thumbnail": (post.get("thumbnail") or {}).get("url"),
            "media": images[:4],
            "matched_slug": slug,
        }
    return None



def run():
    conn = get_connection()
    # Sadece hala gercek PH galerisine sahip OLMAYAN (birden fazla farkli
    # gorseli olmayan) urunler tekrar denenir - zaten eslesenleri atlar.
    rows = conn.execute("""
        SELECT id, original_name, website, thumbnail, gallery FROM products
        WHERE ph_id LIKE ?
        AND (gallery IS NULL OR gallery NOT LIKE ?)
    """, ("manual-%", "%,%")).fetchall()
    rows = [dict(r) for r in rows]
    conn.close()
    print(f"{len(rows)} urun (henuz gercek PH galerisi olmayan) tekrar denenecek.")

    matched, no_match, skipped_ambiguous = 0, 0, 0
    for i, r in enumerate(rows):
        if r["original_name"].strip().lower() in KNOWN_AMBIGUOUS_NAMES:
            skipped_ambiguous += 1
            print(f"[{i}] BILINEN CAKISMA - ATLANDI (guvenlik): {r['original_name']}")
            continue
        result = try_match(r["original_name"], r["website"])
        if result:
            conn = get_connection()
            gallery_str = ",".join(result["media"])
            # Thumbnail sadece su an favicon ise PH'nin gercek thumbnail'iyle yukseltilir
            new_thumb = r["thumbnail"]
            if result["thumbnail"] and (not new_thumb or "google.com/s2/favicons" in new_thumb):
                new_thumb = result["thumbnail"]
            conn.execute(
                "UPDATE products SET gallery = ?, thumbnail = ? WHERE id = ?",
                (gallery_str, new_thumb, r["id"])
            )
            conn.commit()
            conn.close()
            matched += 1
            print(f"[{i}] ESLESTI: {r['original_name']} (slug={result['matched_slug']}) -> {len(result['media'])} gorsel")
        else:
            no_match += 1
            print(f"[{i}] eslesme yok: {r['original_name']}")
        time.sleep(2.0)

    print(f"\nBitti. Eslesen: {matched}, Eslesmeyen: {no_match}, Bilinen cakisma (atlandi): {skipped_ambiguous}")


if __name__ == "__main__":
    run()
