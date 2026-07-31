"""
Affiliate Placement Engine
Amac: is_partner=1 olan (affiliate anlasmasi olan) urunlerin adinin, DIGER
urunlerin/rehberlerin/karsilastirmalarin icerigi icinde (organik olarak)
gectigi yerleri bulup CTA onerisi hazirlamak.

Ornek: ElevenLabs affiliate oldu -> "ElevenLabs" kelimesi baska hangi
rehber/karsilastirma/urun aciklamasinda geciyor -> oraya affiliate linki/CTA
eklenmesi onerilir.

Kullanim:
    python affiliate_placement_scan.py
"""
import re
from dotenv import load_dotenv
load_dotenv()
import db


def find_mentions(partner_name: str, exclude_id: int = None):
    """partner_name'in gectigi urun/rehber/karsilastirma icerigini bulur."""
    conn = db.get_connection()
    pattern = f"%{partner_name}%"

    products = conn.execute("""
        SELECT id, slug, title_tr, original_name FROM products
        WHERE (content_tr LIKE ? OR summary_tr LIKE ?) AND id != ?
    """, (pattern, pattern, exclude_id or -1)).fetchall()
    products = [dict(r) for r in products]

    guides = conn.execute("""
        SELECT id, slug, title FROM guides
        WHERE content_html LIKE ?
    """, (pattern,)).fetchall()
    guides = [dict(r) for r in guides]

    comparisons = conn.execute("""
        SELECT DISTINCT c.id, c.slug, c.title
        FROM comparisons c
        JOIN comparison_items ci ON ci.comparison_id = c.id
        WHERE ci.name LIKE ? OR c.intro LIKE ?
    """, (pattern, pattern)).fetchall()
    comparisons = [dict(r) for r in comparisons]

    conn.close()
    return products, guides, comparisons


def run():
    conn = db.get_connection()
    partners = conn.execute(
        "SELECT id, original_name, title_tr, affiliate_url FROM products WHERE is_partner = 1"
    ).fetchall()
    partners = [dict(r) for r in partners]
    conn.close()

    if not partners:
        print("Henuz is_partner=1 olarak isaretlenmis urun yok.")
        return

    print(f"{len(partners)} affiliate partner bulundu. Site genelinde taraniyor...\n")

    total_opportunities = 0
    for p in partners:
        name = p["original_name"] or p["title_tr"]
        products, guides, comparisons = find_mentions(name, exclude_id=p["id"])
        found = len(products) + len(guides) + len(comparisons)
        total_opportunities += found

        if found == 0:
            continue

        print(f"### {name} (affiliate) -> {found} yerde organik olarak geciyor")
        if products:
            print(f"  Urun sayfalari ({len(products)}):")
            for pr in products[:10]:
                print(f"    - {pr['title_tr']}  (/urun/{pr['slug']})")
            if len(products) > 10:
                print(f"    ... ve {len(products) - 10} tane daha")
        if guides:
            print(f"  Rehberler ({len(guides)}):")
            for g in guides[:10]:
                print(f"    - {g['title']}  (/rehber/{g['slug']})")
        if comparisons:
            print(f"  Karsilastirmalar ({len(comparisons)}):")
            for c in comparisons[:10]:
                print(f"    - {c['title']}  (/karsilastirma/{c['slug']})")
        print()

    print(f"TOPLAM FIRSAT: {total_opportunities} sayfada affiliate CTA eklenebilir.")


if __name__ == "__main__":
    run()
