# -*- coding: utf-8 -*-
"""
'Coverage Opportunity' araclarini (bir karsilastirmada/koleksiyonda gecen ama henuz
kendi urun sayfasi olmayan taninmis araclar) product_generation_queue tablosuna aktarir.
LLM KULLANMAZ - sadece veri toplar. Uretim (LLM cagrisi) ayri, kota acilinca calisacak
bir script'in isi (bkz. process_generation_queue.py - henuz yazilmadi, kota acilinca yazilacak).
"""
from dotenv import load_dotenv
load_dotenv()
import db


def run():
    conn = db.get_connection()

    # Her comparison_item + hangi karsilastirmadan geldigi (source icin)
    rows = conn.execute("""
        SELECT ci.name, c.title AS comparison_title, ci.rank
        FROM comparison_items ci
        JOIN comparisons c ON c.id = ci.comparison_id
    """).fetchall()

    all_product_names = {
        db.normalize_name(dict(r)["original_name"])
        for r in conn.execute("SELECT original_name FROM products").fetchall()
    }

    # Ayni arac ismi (normalized) icin: hangi karsilastirmalardan geldigi + en iyi rank'i topla
    candidates = {}
    for r in rows:
        r = dict(r)
        norm = db.normalize_name(r["name"])
        if norm in all_product_names:
            continue  # zaten kendi urun sayfasi var, kuyruga gerek yok
        entry = candidates.setdefault(norm, {"name": r["name"], "sources": set(), "best_rank": 99})
        entry["sources"].add(r["comparison_title"])
        entry["best_rank"] = min(entry["best_rank"], r["rank"] or 99)

    added = 0
    for norm, info in candidates.items():
        source_count = len(info["sources"])
        if source_count >= 2:
            priority = "High"
        elif info["best_rank"] <= 2:
            priority = "High"
        elif info["best_rank"] <= 3:
            priority = "Medium"
        else:
            priority = "Low"

        source_str = "|".join(sorted(info["sources"]))
        db.add_to_generation_queue(info["name"], source_str, priority, conn=conn)
        added += 1

    conn.commit()
    conn.close()

    print(f"Tarama tamamlandi: {len(candidates)} benzersiz eksik arac bulundu, kuyruga eklendi/guncellendi.")

    # Ozet: onceliklere gore dagilim
    queue = db.get_generation_queue(status=None)
    from collections import Counter
    by_priority = Counter(q["priority"] for q in queue if q["status"] == "pending")
    print(f"Kuyruk durumu (pending): High={by_priority.get('High',0)} Medium={by_priority.get('Medium',0)} Low={by_priority.get('Low',0)}")


if __name__ == "__main__":
    run()
