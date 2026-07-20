# -*- coding: utf-8 -*-
"""
Sprint: Icerik Sagligi - Script 2/2
Deterministik veri butunlugu denetimi: eksik alanlar, duplicate slug, orphan kayitlar.
LLM KULLANMAZ.
"""
from dotenv import load_dotenv
load_dotenv()
import db


def run_data_audit():
    conn = db.get_connection()
    report = {}

    total = dict(conn.execute("SELECT COUNT(*) as c FROM products").fetchone())["c"]
    report["total_products"] = total

    # Eksik alanlar
    for field in ["thumbnail", "website", "pricing_type", "summary_tr", "slug"]:
        row = conn.execute(
            f"SELECT COUNT(*) as c FROM products WHERE {field} IS NULL OR {field} = ''"
        ).fetchone()
        report[f"missing_{field}"] = dict(row)["c"]

    # Duplicate slug
    dup_rows = conn.execute("""
        SELECT slug, COUNT(*) as c FROM products GROUP BY slug HAVING COUNT(*) > 1
    """).fetchall()
    report["duplicate_slugs"] = [dict(r) for r in dup_rows]

    # Orphan comparison_items (urun silinmis ama comparison_items'ta kalmis olabilir - normalized_name eslesme oldugu icin FK yok)
    orphan_comp = conn.execute("""
        SELECT ci.id, ci.name FROM comparison_items ci
        LEFT JOIN products p ON LOWER(REPLACE(p.original_name, ' ', '')) = LOWER(REPLACE(ci.name, ' ', ''))
        WHERE p.id IS NULL
    """).fetchall()
    report["orphan_comparison_items"] = [dict(r) for r in orphan_comp]

    # Orphan collection_items (gercek FK var, product_id -> products.id, silinen urun varsa items yetim kalir)
    orphan_col = conn.execute("""
        SELECT ci.id, ci.product_id FROM collection_items ci
        LEFT JOIN products p ON p.id = ci.product_id
        WHERE p.id IS NULL
    """).fetchall()
    report["orphan_collection_items"] = [dict(r) for r in orphan_col]

    # Guides tablosundaki related_tool_slugs / related_comparison_slugs icinde artik var olmayan slug var mi
    guide_rows = conn.execute("SELECT id, slug, related_tool_slugs, related_comparison_slugs FROM guides").fetchall()
    orphan_guide_refs = []
    all_product_slugs = {dict(r)["slug"] for r in conn.execute("SELECT slug FROM products").fetchall()}
    all_comparison_slugs = {dict(r)["slug"] for r in conn.execute("SELECT slug FROM comparisons").fetchall()}
    for g in guide_rows:
        gd = dict(g)
        tool_slugs = (gd.get("related_tool_slugs") or "").split(",")
        comp_slugs = (gd.get("related_comparison_slugs") or "").split(",")
        missing_tools = [s for s in tool_slugs if s and s not in all_product_slugs]
        missing_comps = [s for s in comp_slugs if s and s not in all_comparison_slugs]
        if missing_tools or missing_comps:
            orphan_guide_refs.append({
                "guide_slug": gd["slug"], "missing_tools": missing_tools, "missing_comparisons": missing_comps
            })
    report["orphan_guide_refs"] = orphan_guide_refs

    # Kirik link sayisi (zaten bilinen, referans icin)
    broken = dict(conn.execute("SELECT COUNT(*) as c FROM products WHERE is_broken = 1").fetchone())["c"]
    report["broken_links"] = broken

    conn.close()
    return report


def print_report(report: dict, out=None):
    def p(msg):
        print(msg)
        if out is not None:
            out.write(msg + "\n")

    total = report["total_products"]
    p(f"=== VERI BUTUNLUGU RAPORU ({total} urun) ===\n")

    p("Eksik alanlar:")
    for field in ["thumbnail", "website", "pricing_type", "summary_tr", "slug"]:
        c = report[f"missing_{field}"]
        flag = "[UYARI]" if c > 0 else "[OK]"
        p(f"  {flag} {field}: {c}")

    p(f"\nDuplicate slug: {len(report['duplicate_slugs'])}")
    for d in report["duplicate_slugs"]:
        p(f"  - {d['slug']} ({d['c']} kez)")

    p(f"\nCoverage opportunity — karsilastirmada var, henuz urun sayfasi olmayan taninmis araclar: {len(report['orphan_comparison_items'])}")
    p("  (Bu bir bug degil: PH pipeline'i sadece YENI PH lansmanlarini cekiyor, Canva/Perplexity gibi")
    p("   yerlesik araclar PH'de yeni cikmadigi icin hic eklenmemis. Urun sayfasina donusturulebilir.)")
    for o in report["orphan_comparison_items"][:10]:
        p(f"  - {o['name']}")

    p(f"\nYetim collection_items (urun silinmis - GERCEK veri sorunu olabilir): {len(report['orphan_collection_items'])}")

    p(f"\nRehberlerde kirik referans: {len(report['orphan_guide_refs'])}")
    for g in report["orphan_guide_refs"]:
        p(f"  - {g['guide_slug']}: eksik_arac={g['missing_tools']} eksik_karsilastirma={g['missing_comparisons']}")

    p(f"\nKirik link (referans): {report['broken_links']}")

    # Sayisal ozet (harf notu yerine - ChatGPT onerisi: yorumlamayi insana birak)
    real_issues = (
        sum(report[f"missing_{f}"] for f in ["thumbnail", "website", "pricing_type", "summary_tr", "slug"])
        + len(report["duplicate_slugs"])
        + len(report["orphan_collection_items"])
        + len(report["orphan_guide_refs"])
    )
    p(f"\n=== OZET ===")
    p(f"Urun: {total}")
    p(f"Eksik alan (toplam): {sum(report[f'missing_{f}'] for f in ['thumbnail', 'website', 'pricing_type', 'summary_tr', 'slug'])}")
    p(f"Duplicate slug: {len(report['duplicate_slugs'])}")
    p(f"Coverage opportunity (bug degil): {len(report['orphan_comparison_items'])}")
    p(f"Yetim collection_items (gercek sorun): {len(report['orphan_collection_items'])}")
    p(f"Kirik rehber referansi: {len(report['orphan_guide_refs'])}")
    p(f"Kirik link: {report['broken_links']}")
    p(f"GERCEK VERI SORUNU SAYISI: {real_issues}")


if __name__ == "__main__":
    r = run_data_audit()
    with open("_data_audit_result.txt", "w", encoding="utf-8") as f:
        print_report(r, out=f)
