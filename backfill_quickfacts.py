"""
Var olan urunlerde bos kalan why_use_it/key_features/platforms/pricing_type
alanlarini kademeli olarak doldurur (Groq kotasini zorlamamak icin gunde
kucuk bir grup - varsayilan 20).

Kullanim:
    python backfill_quickfacts.py          # 20 urun
    python backfill_quickfacts.py 30       # 30 urun
"""
import sys
import time
from db import init_db, get_products_missing_quickfacts, update_product_quickfacts
from generate_content import generate_quickfacts


def run(limit: int = 20):
    init_db()
    products = get_products_missing_quickfacts(limit=limit)
    print(f"{len(products)} urun icin eksik alanlar dolduruluyor...")

    ok, failed = 0, 0
    for p in products:
        print(f"  [isleniyor] {p['original_name']}...")
        try:
            facts = generate_quickfacts(p)
            key_features = facts.get("key_features", [])
            key_features_str = ",".join(key_features) if isinstance(key_features, list) else key_features
            update_product_quickfacts(
                p["id"],
                facts.get("why_use_it", ""),
                key_features_str,
                facts.get("platforms", ""),
                facts.get("pricing_type", ""),
            )
            print(f"    -> tamamlandi")
            ok += 1
            time.sleep(1)  # Groq rate limitine takilmamak icin
        except Exception as e:
            print(f"    !! HATA: {p['original_name']}: {e}")
            failed += 1

    print(f"\nTamamlandi. {ok} basarili, {failed} hatali.")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    run(limit)
