import json
from dotenv import load_dotenv
load_dotenv()
import db

assert db.USE_POSTGRES, "DATABASE_URL tanimli degil, .env kontrol et"

with open("migration_dump.json", "r", encoding="utf-8") as f:
    data = json.load(f)

products = data["products"]
comparisons = data["comparisons"]
collections = data["collections"]

# --- products ---
old_to_new_product_id = {}
inserted, skipped = 0, 0
for p in products:
    conn = db.get_connection()
    existing = conn.execute("SELECT id FROM products WHERE ph_id = ?", (p["ph_id"],)).fetchone()
    if existing:
        old_to_new_product_id[p["id"]] = dict(existing)["id"]
        conn.close()
        skipped += 1
        continue
    conn.execute("""
        INSERT INTO products
        (ph_id, slug, original_name, title_tr, summary_tr, content_tr, tags,
         ph_url, website, thumbnail, votes, topics, created_at, normalized_name,
         why_use_it, key_features, platforms, pricing_type, affiliate_url,
         is_partner, last_checked_at, is_broken)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        p["ph_id"], p["slug"], p["original_name"], p["title_tr"], p["summary_tr"],
        p["content_tr"], p["tags"], p["ph_url"], p["website"], p["thumbnail"],
        p["votes"], p["topics"], p["created_at"], p.get("normalized_name"),
        p.get("why_use_it"), p.get("key_features"), p.get("platforms"),
        p.get("pricing_type"), p.get("affiliate_url"), p.get("is_partner", 0),
        p.get("last_checked_at"), p.get("is_broken", 0),
    ))
    new_id = conn.execute("SELECT id FROM products WHERE ph_id = ?", (p["ph_id"],)).fetchone()
    old_to_new_product_id[p["id"]] = dict(new_id)["id"]
    conn.commit()
    conn.close()
    inserted += 1

print(f"Urunler: {inserted} eklendi, {skipped} zaten vardi (atlandi)")

# --- comparisons + comparison_items ---
comp_inserted = 0
for c in comparisons:
    conn = db.get_connection()
    existing = conn.execute("SELECT id FROM comparisons WHERE slug = ?", (c["slug"],)).fetchone()
    if existing:
        comp_id = dict(existing)["id"]
        existing_items = conn.execute(
            "SELECT COUNT(*) as cnt FROM comparison_items WHERE comparison_id = ?", (comp_id,)
        ).fetchone()
        if dict(existing_items)["cnt"] > 0:
            conn.close()
            continue
    conn.close()
    items = [
        {
            "rank": it["rank"], "name": it["name"], "score": it["score"],
            "pricing": it.get("pricing", ""), "best_for": it.get("best_for", ""),
            "pros": it["pros"] if isinstance(it["pros"], list) else (it["pros"].split("|") if it.get("pros") else []),
            "cons": it["cons"] if isinstance(it["cons"], list) else (it["cons"].split("|") if it.get("cons") else []),
            "website": it.get("website", ""),
        }
        for it in c.get("tools", [])
    ]
    conn.close()
    db.save_comparison(c["slug"], c["title"], c.get("intro", ""), items)
    comp_inserted += 1

print(f"Karsilastirmalar: {comp_inserted} eklendi")

# --- collections + collection_items ---
col_inserted = 0
for col in collections:
    conn = db.get_connection()
    existing = conn.execute("SELECT id FROM collections WHERE slug = ?", (col["slug"],)).fetchone()
    if existing:
        new_col_id = dict(existing)["id"]
        # Koleksiyon zaten var ama items eksik olabilir (onceki eksik migrasyon).
        existing_items = conn.execute(
            "SELECT COUNT(*) as cnt FROM collection_items WHERE collection_id = ?", (new_col_id,)
        ).fetchone()
        if dict(existing_items)["cnt"] > 0:
            conn.close()
            continue
    else:
        cur = conn.execute(
            "INSERT INTO collections (slug, title, description, cover_image, created_at) VALUES (?, ?, ?, ?, ?)",
            (col["slug"], col["title"], col.get("description", ""), col.get("cover_image"), col.get("created_at"))
        )
        new_col_id = cur.lastrowid
        conn.commit()
    for idx, item in enumerate(col.get("items", [])):
        old_pid = item["id"]  # products.* SELECT * ile geldigi icin bu product id'sidir
        new_pid = old_to_new_product_id.get(old_pid)
        if not new_pid:
            continue
        conn.execute(
            "INSERT INTO collection_items (collection_id, product_id, order_num, reason) VALUES (?, ?, ?, ?)",
            (new_col_id, new_pid, idx, item.get("reason", ""))
        )
    conn.commit()
    conn.close()
    col_inserted += 1

print(f"Koleksiyonlar: {col_inserted} eklendi")
print("MIGRASYON TAMAMLANDI")
