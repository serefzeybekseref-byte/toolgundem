import json
import os
os.environ.pop("DATABASE_URL", None)
import db

products = db.get_all_products()
comparisons = db.get_all_comparisons()
collections = db.get_all_collections()
# get_all_collections() urunleri (items) icermez, o yuzden her koleksiyonun
# detayini get_collection_by_slug ile ayrica cekip items'i ekliyoruz.
for col in collections:
    full = db.get_collection_by_slug(col["slug"])
    col["items"] = full["items"] if full else []

with open("migration_dump.json", "w", encoding="utf-8") as f:
    json.dump({
        "products": products,
        "comparisons": comparisons,
        "collections": collections,
    }, f, ensure_ascii=False)

print(f"Dump tamam: {len(products)} urun, {len(comparisons)} karsilastirma, {len(collections)} koleksiyon")
