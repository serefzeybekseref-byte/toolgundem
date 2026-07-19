"""
Mevcut comparison_items kayitlarindaki best_for_type alanini
classify_best_for() ile doldurur (enum'a gecis oncesi eklenmis kayitlar icin).

Kullanim: python backfill_best_for_type.py
"""
from dotenv import load_dotenv
load_dotenv()
from db_target import print_db_target, guard_postgres
print_db_target()
guard_postgres()
from db import init_db, get_connection, classify_best_for

if __name__ == "__main__":
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT id, rank, best_for FROM comparison_items").fetchall()
    updated = 0
    for r in rows:
        row = dict(r)
        bft = classify_best_for(row.get("best_for") or "", row.get("rank") == 1)
        conn.execute("UPDATE comparison_items SET best_for_type = ? WHERE id = ?", (bft, row["id"]))
        updated += 1
    conn.commit()
    conn.close()
    print(f"Tamamlandi. {updated} comparison_item guncellendi.")
