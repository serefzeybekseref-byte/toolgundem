"""
Internal Link Architect - Backfill: Rehber -> Karsilastirma baglantilari
Amac: Bir rehberin bahsettigi araclarla (related_tool_slugs) ortak arac
paylasan karsilastirma sayfalarini bulup related_comparison_slugs alanina
otomatik ekler. Sadece bir karsilastirmadan direkt turetilen 7 rehberde
bu alan doluydu; digerlerinde bos kaliyordu.

Eslestirme mantigi:
  - Rehberin urun slug'larindan urun adlarini (title_tr/original_name) al
  - Her karsilastirmanin comparison_items.name listesiyle karsilastir
  - En az 1 ortak arac varsa, o karsilastirma rehbere onerilir
  - Zaten iliskili olanlar (comparison_slug'dan direkt turetilenler) korunur

Kullanim:
    python backfill_guide_comparison_links.py            -> uygular
    python backfill_guide_comparison_links.py --dry-run   -> sadece gosterir
"""
import sys
import re
from dotenv import load_dotenv
load_dotenv()
import db


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def run(dry_run=False):
    conn = db.get_connection()

    guides = conn.execute("SELECT id, slug, title, related_tool_slugs, related_comparison_slugs FROM guides").fetchall()
    guides = [dict(g) for g in guides]

    comparisons = conn.execute("SELECT id, slug, title FROM comparisons").fetchall()
    comparisons = [dict(c) for c in comparisons]

    # Her karsilastirma icin normalize edilmis arac adi seti hazirla
    comp_tool_sets = {}
    for c in comparisons:
        items = conn.execute("SELECT name FROM comparison_items WHERE comparison_id = ?", (c["id"],)).fetchall()
        comp_tool_sets[c["slug"]] = {normalize(dict(i)["name"]) for i in items}

    updated = 0
    for g in guides:
        tool_slugs = [s.strip() for s in (g["related_tool_slugs"] or "").split(",") if s.strip()]
        if not tool_slugs:
            continue

        # Rehberin bahsettigi urunlerin adlarini al
        guide_tool_names = set()
        for slug in tool_slugs:
            row = conn.execute("SELECT title_tr, original_name FROM products WHERE slug = ?", (slug,)).fetchone()
            if row:
                row = dict(row)
                guide_tool_names.add(normalize(row.get("original_name")))
                guide_tool_names.add(normalize(row.get("title_tr")))
        guide_tool_names.discard("")

        if not guide_tool_names:
            continue

        # Ortak arac paylasan karsilastirmalari bul
        existing = set(s.strip() for s in (g["related_comparison_slugs"] or "").split(",") if s.strip())
        matches = list(existing)
        for comp_slug, comp_names in comp_tool_sets.items():
            if comp_slug in existing:
                continue
            overlap = guide_tool_names & comp_names
            if len(overlap) >= 1:
                matches.append(comp_slug)

        if len(matches) > len(existing):
            new_value = ",".join(matches)
            print(f"[{'ONERI' if dry_run else 'GUNCELLENDI'}] {g['title']}: {existing or '(bos)'} -> {matches}")
            if not dry_run:
                conn.execute("UPDATE guides SET related_comparison_slugs = ? WHERE id = ?", (new_value, g["id"]))
                conn.commit()
            updated += 1

    conn.close()
    print(f"\n{'Onerilecek' if dry_run else 'Guncellenen'} rehber sayisi: {updated} / {len(guides)}")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
