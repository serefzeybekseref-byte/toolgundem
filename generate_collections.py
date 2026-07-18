"""
Urun sayisi arttikca otomatik "koleksiyon" (toolkit) uretir.
Var olan gercek urun verisine dayanir - AI sadece elindeki title_tr/summary_tr
bilgisini yapilandirilmis bir koleksiyona donusturur, yeni bilgi uydurmaz.
db.py'nin Postgres/SQLite soyutlamasini ve Groq->NVIDIA->Gemini fallback
zincirini kullanir (auto_generate_comparisons.py ile ayni desen).
"""
import json
import os
import time
from dotenv import load_dotenv
load_dotenv()
from db import init_db, get_connection, slugify, save_collection, get_all_collections
from generate_content import _generate_with_fallback
from quality_gate import check_collection

init_db()

MAX_SOURCE_PRODUCTS = 60
MIN_ITEMS_PER_COLLECTION = 4


def get_candidate_products(limit=MAX_SOURCE_PRODUCTS):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, original_name, title_tr, summary_tr, topics FROM products "
        "WHERE summary_tr IS NOT NULL ORDER BY votes DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def existing_collection_slugs():
    return {c["slug"] for c in get_all_collections()}


def build_collections_via_ai(products: list) -> list:
    product_text = ""
    for p in products:
        product_text += f"- ID: {p['id']} | İsim: {p['original_name']} | Özet: {p.get('summary_tr', '')}\n"

    prompt = f"""Sen BulurumAI için çalışan kıdemli bir teknoloji editörüsün.
Aşağıdaki gerçek AI araçlarını kullanarak 3 adet "Hazır Araç Paketi / Koleksiyon" oluştur
(örnek: "Youtuber'lar İçin Başlangıç Paketi", "Girişimciler İçin Temel Araç Seti").
YENİ ÜRÜN UYDURMA - sadece aşağıdaki listeden seç.

Araçlar:
{product_text}

Kurallar:
- Her koleksiyonda 4-6 arası araç olsun, sadece listedeki ID'leri kullan.
- title: kısa, çekici, SEO'ya uygun (60 karakteri geçmesin).
- description: koleksiyonun ne işe yaradığını 1 cümlede özetle.
- Her araç için reason: neden bu koleksiyonda olduğunu 1 cümlede açıkla.
- Sadece Türkçe yaz.

Yalnızca şu JSON formatında cevap ver:
{{"collections": [
  {{"title": "...", "description": "...", "items": [
    {{"product_id": 123, "reason": "..."}}
  ]}}
]}}
"""
    groq_extra = {"temperature": 0.3, "response_format": {"type": "json_object"}}
    result = _generate_with_fallback(prompt, groq_extra)
    return result.get("collections", [])


def run():
    existing = existing_collection_slugs()
    products = get_candidate_products()
    if not products:
        print("Uygun urun bulunamadi.")
        return

    print(f"{len(products)} urunle koleksiyon uretiliyor...")
    try:
        collections = build_collections_via_ai(products)
    except Exception as e:
        print(f"AI cagrisi basarisiz: {e}")
        return

    by_id = {p["id"]: p for p in products}
    created, skipped, rejected = 0, 0, 0
    rejection_report = []
    for col in collections:
        title = col.get("title", "").strip()
        if not title:
            continue
        slug = slugify(title)
        if slug in existing:
            print(f"[atlandi] '{title}' zaten var.")
            skipped += 1
            continue

        items = [
            {"product_id": it["product_id"], "reason": it.get("reason", "")}
            for it in col.get("items", [])
            if "product_id" in it
        ]
        if len(items) < MIN_ITEMS_PER_COLLECTION:
            print(f"[atlandi] '{title}': yeterli urun yok ({len(items)})")
            continue

        description = col.get("description", "")
        ok, problems = check_collection(title, description, items, source_products_by_id=by_id)
        if not ok:
            print(f"  !! KALITE KAPISI REDDETTI '{title}' ({len(problems)} sorun):")
            for pr in problems:
                print(f"     - {pr}")
            rejected += 1
            rejection_report.append({"title": title, "problems": problems})
            continue

        save_collection(slug, title, description, items)
        print(f"  -> kaydedildi: /koleksiyon/{slug} ({len(items)} urun)")
        created += 1
        time.sleep(1.5)

    print(f"\nBitti. Olusturulan: {created}, Atlanan: {skipped}, Kalite kapisinda reddedilen: {rejected}")

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"rejected_count={rejected}\n")
            if rejection_report:
                report_lines = []
                for r in rejection_report:
                    report_lines.append(f"### {r['title']}")
                    for pr in r["problems"]:
                        report_lines.append(f"- {pr}")
                f.write("rejection_report<<EOF\n")
                f.write("\n".join(report_lines) + "\n")
                f.write("EOF\n")


if __name__ == "__main__":
    run()
